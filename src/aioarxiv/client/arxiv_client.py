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
    Metadata,
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
    ) -> SearchResult:
        try:
            # Get initial search results
            first_page_result, should_fetch_more = await self._prepare_initial_search(
                query=query,
                start=start,
                id_list=id_list,
                max_results=max_results,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            if not should_fetch_more:
                return first_page_result

            # Calculate pagination parameters
            papers_received = len(first_page_result.papers)
            remaining_papers = min(
                (max_results - papers_received)
                if max_results
                else first_page_result.total_result,
                first_page_result.total_result - papers_received,
            )

            if remaining_papers <= 0:
                return first_page_result

            # Prepare batch requests parameters
            page_params = self._generate_page_params(
                base_start=(start or 0) + self._config.page_size,
                remaining_papers=remaining_papers,
                page_size=self._config.page_size,
            )

            logger.debug(f"Fetching {len(page_params)} additional pages")

            # Execute batch requests
            additional_results = await self._fetch_batch_results(
                query=query,
                page_params=page_params,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            return self.aggregate_search_results(
                [first_page_result, *additional_results]
            )

        except Exception as e:
            logger.error(f"Search operation failed: {e!s}", exc_info=True)
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

    @staticmethod
    def _generate_page_params(
        base_start: int, remaining_papers: int, page_size: int
    ) -> list[PageParam]:
        total_pages = (remaining_papers + page_size - 1) // page_size
        page_params = []

        for page in range(total_pages):
            page_start = base_start + page * page_size
            page_end = min(page_start + page_size, base_start + remaining_papers)
            if page_end > page_start:
                page_params.append(PageParam(start=page_start, end=page_end))

        return page_params

    async def _fetch_batch_results(
        self,
        query: str,
        page_params: list[PageParam],
        sort_by: Optional[SortCriterion],
        sort_order: Optional[SortOrder],
    ) -> list[SearchResult]:
        tasks = await self._create_batch_tasks(query, page_params, sort_by, sort_order)

        if not tasks:
            return []

        responses = await asyncio.gather(*tasks, return_exceptions=True)
        valid_results = []

        for response in responses:
            if isinstance(response, SearchResult):
                valid_results.append(response)
            elif isinstance(response, Exception):
                logger.error(f"Batch task failed: {response!s}", exc_info=True)

        return valid_results

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

    @staticmethod
    def _merge_paper_lists(
        papers_lists: list[list[Paper]], *, keep_latest: bool = True
    ) -> list[Paper]:
        unique_papers: dict[str, Paper] = {}

        for papers in papers_lists:
            for paper in papers:
                paper_id = paper.info.id
                if paper_id not in unique_papers or (
                    keep_latest
                    and paper.info.updated > unique_papers[paper_id].info.updated
                ):
                    unique_papers[paper_id] = paper

        return list(unique_papers.values())

    def aggregate_search_results(self, results: list[SearchResult]) -> SearchResult:
        if not results:
            raise ValueError("Results list cannot be empty")

        papers_lists = [result.papers for result in results]
        merged_papers = self._merge_paper_lists(papers_lists)

        base_result = results[0]
        base_timezone = base_result.metadata.start_time.tzinfo

        aggregated_metadata = Metadata(
            start_time=min(
                result.metadata.start_time.astimezone(base_timezone)
                for result in results
            ),
            end_time=max(
                (
                    result.metadata.end_time.astimezone(base_timezone)
                    for result in results
                    if result.metadata.end_time is not None
                ),
                default=None,
            ),
            missing_results=sum(result.metadata.missing_results for result in results),
            pagesize=sum(result.metadata.pagesize for result in results),
            source=base_result.metadata.source,
        )

        aggregated_params = base_result.query_params.model_copy(
            update={
                "max_results": len(merged_papers),
                "start": min(result.query_params.start or 0 for result in results),
            }
        )

        aggregated_result = SearchResult(
            papers=merged_papers,
            total_result=max(result.total_result for result in results),
            page=max(result.page for result in results),
            has_next=any(result.has_next for result in results),
            query_params=aggregated_params,
            metadata=aggregated_metadata,
        )

        logger.debug(
            f"Aggregated {len(results)} search results with {len(merged_papers)} "
            f"unique papers."
        )

        return aggregated_result

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
