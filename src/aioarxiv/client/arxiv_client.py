from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Optional
from zoneinfo import ZoneInfo

from aiohttp import ClientResponse

from aioarxiv.config import ArxivConfig, default_config
from aioarxiv.exception import HTTPException, QueryBuildError, QueryContext
from aioarxiv.models import Paper, SearchParams, SearchResult, SortCriterion, SortOrder
from aioarxiv.utils import calculate_page_size, logger
from aioarxiv.utils.parser import ArxivParser, RootParser
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
        logger.debug(
            f"ArxivClient initialized with config: {self._config.model_dump()}"
        )

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

    def _build_search_metadata(
        self,
        searchresult: SearchResult,
        page: int,
        batch_size: int,
        papers: list[Paper],
    ) -> SearchResult:
        """更新搜索结果元数据"""
        has_next = searchresult.total_result > (page * batch_size)
        return searchresult.model_copy(
            update={
                "papers": papers,
                "page": page,
                "has_next": has_next,
                "metadata": searchresult.metadata.model_copy(
                    update={
                        "end_time": datetime.now(tz=ZoneInfo(default_config.timezone)),
                        "pagesize": self._config.page_size,
                        "source": "arxiv",
                    },
                ),
            },
        )

    @staticmethod
    def _should_continue(
        total_yielded: int,
        max_results: Optional[int],
        total_result: int,
        page: int,
        batch_size: int,
    ) -> bool:
        """检查是否继续获取下一页"""
        if max_results and total_yielded >= max_results:
            return False
        return total_result > page * batch_size

    async def search(
        self,
        query: str,
        id_list: Optional[list[str]] = None,
        max_results: Optional[int] = None,
        sort_by: Optional[SortCriterion] = None,
        sort_order: Optional[SortOrder] = None,
    ) -> AsyncGenerator[SearchResult, None]:
        """执行arxiv搜索并返回结构化结果"""
        params = SearchParams(
            query=query,
            id_list=id_list,
            max_results=max_results,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        total_yielded = 0
        page = 1

        while True:
            batch_size = calculate_page_size(
                self._config.page_size,
                params.start,
                params.max_results,
            )
            params.start = (page - 1) * batch_size

            response = await self._fetch_page(params)
            searchresult = RootParser(
                await response.text(), response.url
            ).build_search_result(
                query_params=params,
            )
            papers = await self.parse_response(response)

            if not papers:
                break

            result = self._build_search_metadata(searchresult, page, batch_size, papers)
            await self.download_search_result(result)
            yield result

            total_yielded += len(papers)
            if not self._should_continue(
                total_yielded,
                max_results,
                searchresult.total_result,
                page,
                batch_size,
            ):
                break

            page += 1

    async def _fetch_page(self, params: SearchParams) -> ClientResponse:
        """
        获取单页结果

        Args:
            params: 搜索参数

        Returns:
            响应对象

        Raises:
            QueryBuildError: 如果构建查询参数失败
        """
        query_params = self._build_query_params(params)
        response = await self._session_manager.request(
            "GET", str(self._config.base_url), params=query_params
        )

        if response.status != 200:
            logger.error(f"搜索请求失败, HTTP状态码: {response.status}")
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
            page_size = calculate_page_size(
                self._config.page_size,
                params.start,
                params.max_results,
            )

            query_params = {
                "search_query": params.query,
                "start": params.start,
                "max_results": page_size,
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
