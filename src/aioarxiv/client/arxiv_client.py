import asyncio
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Optional
from zoneinfo import ZoneInfo

from aiohttp import ClientResponse

from aioarxiv.config import ArxivConfig, default_config
from aioarxiv.exception import HTTPException, QueryBuildError, QueryContext
from aioarxiv.models import (
    PageParam,
    Paper,
    SearchParams,
    SearchResult,
    SortCriterion,
    SortOrder,
)
from aioarxiv.utils import logger
from aioarxiv.utils.log import set_config
from aioarxiv.utils.parser import ArxivParser
from aioarxiv.utils.session import SessionManager

from .downloader import ArxivDownloader, DownloadTracker


class ArxivClient:
    def __init__(
        self,
        config: Optional[ArxivConfig] = None,
        session_manager: Optional[SessionManager] = None,
        enable_downloader: bool = False,
        download_dir: Optional[Path] = None,
    ) -> None:
        self._config = config or default_config
        self._session_manager = session_manager or SessionManager(config=self._config)
        self.download_dir = download_dir
        self._enable_downloader = enable_downloader
        self._downloader: Optional[ArxivDownloader] = None
        set_config(self._config)
        logger.info(f"ArxivClient initialized with config: {self._config.model_dump()}")

    @property
    def downloader(self) -> Optional[ArxivDownloader]:
        """懒加载下载器"""
        if not self._enable_downloader:
            logger.debug("下载器未启用")
            return None
        if self._downloader is None:
            self._downloader = ArxivDownloader(
                self._session_manager,
                self.download_dir,
                self._config,
            )
        return self._downloader

    def _build_search_result_metadata(
        self,
        searchresult: SearchResult,
        page: int,
        batch_size: int,
        papers: list[Paper],
    ) -> SearchResult:
        has_next = searchresult.total_result > (page * batch_size)
        metadata = searchresult.metadata.model_copy(
            update={
                "end_time": datetime.now(tz=ZoneInfo(default_config.timezone)),
                "pagesize": self._config.page_size,
            },
        )
        return searchresult.model_copy(
            update={
                "papers": papers,
                "page": page,
                "has_next": has_next,
                "metadata": metadata,
            },
        )

    async def _prepare_initial_search(
        self,
        query: str,
        start: Optional[int],
        id_list: Optional[list[str]],
        max_results: Optional[int],
        sort_by: Optional[SortCriterion],
        sort_order: Optional[SortOrder],
    ) -> tuple[SearchResult, bool]:
        """准备初始搜索"""
        page_size = min(self._config.page_size, max_results or self._config.page_size)

        params = SearchParams(
            query=query,
            start=start,
            id_list=id_list,
            max_results=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        response = await self._fetch_page(params)
        result = ArxivParser(await response.text(), response).build_search_result(
            params
        )
        logger.debug(f"Fetched page 1 with {len(result.papers)} papers")
        result = self._build_search_result_metadata(
            searchresult=result, page=1, batch_size=page_size, papers=result.papers
        )

        needs_more = (
            max_results is not None
            and max_results > len(result.papers)
            and result.total_result > len(result.papers)
        )

        return result, needs_more

    async def _fetch_and_update_result(
        self, params: SearchParams, page: int
    ) -> SearchResult:
        """获取并更新搜索结果"""
        response = await self._fetch_page(params)
        result = ArxivParser(await response.text(), response).build_search_result(
            params
        )
        logger.debug(f"Fetched page {page} with {len(result.papers)} papers")
        return self._build_search_result_metadata(
            searchresult=result,
            page=page,
            batch_size=self._config.page_size,
            papers=result.papers,
        )

    async def _create_batch_tasks(
        self,
        query: str,
        page_params: list[PageParam],
        sort_by: Optional[SortCriterion] = None,
        sort_order: Optional[SortOrder] = None,
    ) -> list[asyncio.Task]:
        """创建批量任务"""
        return [
            asyncio.create_task(
                self._fetch_and_update_result(
                    SearchParams(
                        query=query,
                        start=param.start,
                        max_results=param.end - param.start,
                        sort_by=sort_by,
                        sort_order=sort_order,
                        id_list=None,
                    ),
                    page=i + 2,
                )
            )
            for i, param in enumerate(page_params)
        ]

    async def search(
        self,
        query: str,
        id_list: Optional[list[str]] = None,
        max_results: Optional[int] = None,
        sort_by: Optional[SortCriterion] = None,
        sort_order: Optional[SortOrder] = None,
        start: Optional[int] = None,
    ) -> list[SearchResult]:
        result, needs_more = await self._prepare_initial_search(
            query,
            start,
            id_list,
            max_results,
            sort_by,
            sort_order,
        )

        if not needs_more:
            return [result]

        remaining = min(
            max_results - len(result.papers) if max_results else result.total_result,
            result.total_result - len(result.papers),
        )

        base_start = (start or 0) + self._config.page_size
        page_size = self._config.page_size
        total_pages = (remaining + page_size - 1) // page_size

        page_params = []
        for page in range(total_pages):
            page_start = base_start + page * page_size
            page_end = min(page_start + page_size, base_start + remaining)
            if page_end > page_start:
                page_params.append(PageParam(start=page_start, end=page_end))

        logger.debug(f"Page params list: {page_params}")

        tasks = await self._create_batch_tasks(query, page_params, sort_by, sort_order)

        try:
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            valid_results = [result]

            for r in responses:
                if isinstance(r, SearchResult):
                    valid_results.append(r)
                elif isinstance(r, Exception):
                    logger.error(f"Task failed: {r}")

            return valid_results

        except Exception as e:
            logger.error(f"Batch search failed: {e}")
            raise

    async def _fetch_page(self, params: SearchParams) -> ClientResponse:
        """获取单页结果"""
        query_params = self._build_query_params(params)
        response = await self._session_manager.request(
            "GET", str(self._config.base_url), params=query_params
        )

        if response.status != 200:
            raise HTTPException(response.status)

        return response

    def _build_query_params(self, params: SearchParams) -> dict:
        """
        构建查询参数

        Args:
            params: 搜索参数模型

        Returns:
            dict: 查询参数

        Raises:
            QueryBuildError: 如果构建查询参数失败
        """
        try:
            query_params = {
                "search_query": params.query,
                "start": params.start or 0,
                "max_results": params.max_results,
            }

            if params.id_list:
                query_params["id_list"] = ",".join(params.id_list)

            if params.sort_by:
                query_params["sortBy"] = params.sort_by.value

            if params.sort_order:
                query_params["sortOrder"] = params.sort_order.value

            return query_params

        except Exception as e:
            raise QueryBuildError(
                message="构建查询参数失败",
                context=QueryContext(
                    params={
                        "page_size": self._config.page_size,
                        "max_results": params.max_results,
                        "start": params.start,
                        "id_list": params.id_list,
                    },
                    field_name="query_params",
                ),
                original_error=e,
            ) from e

    async def parse_response(self, response: ClientResponse) -> list[Paper]:
        """
        解析API响应

        Args:
            response: 响应对象

        Returns:
            解析后的论文列表和总结果数

        Raises:
            ParserException: 如果解析失败
        """
        text = await response.text()
        return ArxivParser(text, response).parse_feed()

    async def download_paper(
        self,
        paper: Paper,
        filename: Optional[str] = None,
    ) -> Optional[None]:
        """
        下载论文

        Args:
            paper: 论文对象
            filename: 文件名

        Returns:
            None if downloader is disabled

        Raises:
            PaperDownloadException: 如果下载失败
        """
        if downloader := self.downloader:
            await downloader.download_paper(paper, filename)
        return None

    async def download_search_result(
        self,
        search_result: SearchResult,
    ) -> Optional[DownloadTracker]:
        """
        下载搜索结果中的所有论文

        Args:
            search_result: 搜索结果

        Returns:
            DownloadTracker if enabled, None if disabled

        Raises:
            PaperDownloadException: 如果下载失败
        """
        if downloader := self.downloader:
            return await downloader.batch_download(search_result)
        return None

    async def close(self) -> None:
        """关闭客户端"""
        await self._session_manager.close()

    async def __aenter__(self) -> "ArxivClient":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.close()
