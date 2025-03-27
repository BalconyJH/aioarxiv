import asyncio
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Optional
from typing_extensions import overload
from zoneinfo import ZoneInfo

from aiohttp import ClientResponse

from aioarxiv.config import ArxivConfig, default_config
from aioarxiv.exception import HTTPException, QueryBuildError
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
from aioarxiv.utils.arxiv_parser import ArxivParser
from aioarxiv.utils.log import ConfigManager
from aioarxiv.utils.session import SessionManager

from .downloader import ArxivDownloader, DownloadTracker


class ArxivClient:
    def __init__(
        self,
        config: Optional[ArxivConfig] = None,
        session_manager: Optional[SessionManager] = None,
        *,
        enable_downloader: bool = False,
        download_dir: Optional[Path] = None,
    ) -> None:
        """Initialize ArxivClient with optional configuration.

        Args:
            config (Optional[ArxivConfig]): Custom configuration for the client.
            session_manager (Optional[SessionManager]): Custom session manager.
            enable_downloader (bool): Whether to enable the paper downloader.
            download_dir (Optional[Path]): Directory path for downloading papers.
        """
        self._config = config or default_config
        self._session_manager = session_manager or SessionManager(config=self._config)
        self.download_dir = download_dir
        self._enable_downloader = enable_downloader
        self._downloader: Optional[ArxivDownloader] = None
        ConfigManager.set_config(config=self._config)
        logger.info(f"ArxivClient initialized with config: {self._config.model_dump()}")
        average_interval = (
            self._config.rate_limit_period / self._config.rate_limit_calls
        )
        if self._config.rate_limit_period > 0 and average_interval < 3.0:
            logger.warning(
                f"Configuration for rate limit calls and period ({average_interval}/s) may cause rate limiting due to "
                f"arXiv API policy which limits to 1 request every 3 seconds. "
                "Please refer to the (arXiv API documentation)[https://info.arxiv.org/help/api/tou.html] "
                "for more details."
            )

    @property
    def downloader(self) -> Optional[ArxivDownloader]:
        """Get the downloader instance if enabled."""
        if not self._enable_downloader:
            logger.debug("Downloader is disabled")
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
        """Build search result metadata with updated information.

        Args:
            searchresult (SearchResult): Search result object.
            page (int): Page number of the search result.
            batch_size (int): Number of papers fetched in the batch.
            papers (list[Paper]): List of papers fetched in the batch.

        Returns:
            SearchResult: Search result object with updated metadata.
        """
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
        query: Optional[str] = None,
        start: Optional[int] = None,
        id_list: Optional[list[str]] = None,
        max_results: Optional[int] = None,
        sort_by: Optional[SortCriterion] = None,
        sort_order: Optional[SortOrder] = None,
    ) -> tuple[SearchResult, bool]:
        """
        Prepare the initial search request and fetch the first page of results.

        Args:
            query (Optional[str]): The search query string.
            start (Optional[int]): Index of first result to retrieve.
            id_list (Optional[list[str]]): List of arXiv IDs to retrieve.
            max_results (Optional[int]): Maximum number of results to return.
            sort_by (Optional[SortCriterion]): Criterion to sort results by.
            sort_order (Optional[SortOrder]): Order of sorting.

        Returns:
            tuple[SearchResult, bool]: Tuple containing search result and flag
            indicating whether more results need to be fetched.
        """
        is_id_query = bool(id_list)
        page_size = min(self._config.page_size, max_results or self._config.page_size)

        params = SearchParams(
            query=None if is_id_query else query,
            id_list=id_list if is_id_query else None,
            start=start,
            max_results=page_size,
            sort_by=None if is_id_query else sort_by,
            sort_order=None if is_id_query else sort_order,
        )

        response = await self._fetch_page(params)

        result = ArxivParser(await response.text(), response).build_search_result(
            params
        )

        logger.debug(f"Fetched page 1 with {len(result.papers)} papers")

        result = self._build_search_result_metadata(
            searchresult=result,
            page=1,
            batch_size=page_size,
            papers=result.papers,
        )

        needs_more = (
            not is_id_query
            and max_results is not None
            and max_results > len(result.papers)
            and result.total_result > len(result.papers)
        )

        return result, needs_more

    async def _fetch_and_update_result(
        self, params: SearchParams, page: int
    ) -> SearchResult:
        """Fetch a single page of search results and update metadata.

        Args:
            params (SearchParams): Search parameters for the API request.
            page (int): Page number of the search result.

        Returns:
            SearchResult: Search result with updated metadata.
        """
        response = await self._fetch_page(params)
        result = ArxivParser(await response.text(), response).build_search_result(
            params
        )
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
    ) -> list[asyncio.Task[SearchResult]]:
        """Create a list of tasks to fetch multiple pages of search results.

        Args:
            query (str): The search query string.
            page_params (list[PageParam]): List of page parameters for batch requests.
            sort_by (Optional[SortCriterion]): Criterion to sort results by.
            sort_order (Optional[SortOrder]): Order of sorting.

        Returns:
            list[asyncio.Task[SearchResult]]: List of tasks to fetch search results.
        """
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

    @overload
    async def search(
        self,
        query: str,
        id_list: None = ...,
        max_results: Optional[int] = ...,
        sort_by: Optional[SortCriterion] = ...,
        sort_order: Optional[SortOrder] = ...,
        start: Optional[int] = ...,
    ) -> SearchResult: ...

    @overload
    async def search(
        self,
        query: None = ...,
        id_list: list[str] = ...,
        max_results: Optional[int] = ...,
        sort_by: Optional[SortCriterion] = ...,
        sort_order: Optional[SortOrder] = ...,
        start: Optional[int] = ...,
    ) -> SearchResult: ...

    async def search(
        self,
        query: Optional[str] = None,
        id_list: Optional[list[str]] = None,
        max_results: Optional[int] = None,
        sort_by: Optional[SortCriterion] = None,
        sort_order: Optional[SortOrder] = None,
        start: Optional[int] = None,
    ) -> SearchResult:
        """
        Search arXiv papers via either a keyword query or arXiv ID list.

        Args:
            query (Optional[str]): Keyword-based query string.
            id_list (Optional[list[str]]): List of arXiv IDs to retrieve.
            max_results (Optional[int]): Max results for query search.
            sort_by (Optional[SortCriterion]): Sorting criterion for query search.
            sort_order (Optional[SortOrder]): Sorting order for query search.
            start (Optional[int]): Start index.

        Returns:
            SearchResult: Search results object.
        """
        try:
            if query:
                return await self._search_by_query(
                    query=query,
                    max_results=max_results,
                    sort_by=sort_by,
                    sort_order=sort_order,
                    start=start,
                )
            if id_list:
                return await self._search_by_ids(
                    id_list=id_list,
                    start=start,
                )
            raise QueryBuildError(
                "Search query build failed",
            )
        except Exception as e:
            logger.error(f"Search operation failed: {e!s}", exc_info=True)
            raise

    async def _search_by_query(
        self,
        query: str,
        max_results: Optional[int] = None,
        sort_by: Optional[SortCriterion] = None,
        sort_order: Optional[SortOrder] = None,
        start: Optional[int] = None,
    ) -> SearchResult:
        first_page_result, should_fetch_more = await self._prepare_initial_search(
            query=query,
            start=start,
            max_results=max_results,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        if not should_fetch_more:
            return first_page_result

        papers_received = len(first_page_result.papers)
        remaining_papers = min(
            (max_results - papers_received)
            if max_results
            else first_page_result.total_result,
            first_page_result.total_result - papers_received,
        )

        if remaining_papers <= 0:
            return first_page_result

        page_params = self._generate_page_params(
            base_start=(start or 0) + self._config.page_size,
            remaining_papers=remaining_papers,
            page_size=self._config.page_size,
        )

        logger.debug(f"Fetching {len(page_params)} additional pages")

        additional_results = await self._fetch_batch_results(
            query=query,
            page_params=page_params,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return self.aggregate_search_results([first_page_result, *additional_results])

    async def _search_by_ids(
        self,
        id_list: list[str],
        start: Optional[int] = None,
    ) -> SearchResult:
        result, _ = await self._prepare_initial_search(
            id_list=id_list,
            start=start,
        )
        return result

    async def _fetch_page(self, params: SearchParams) -> ClientResponse:
        """Fetch a single page of results from arXiv API.

        Args:
            params (SearchParams): Search parameters for the API request.

        Returns:
            ClientResponse: HTTP response from the arXiv API.

        Raises:
            HTTPException: If the API request returns a non-200 status code.
        """
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
        """
        Generate page parameters for batch requests.

        Args:
            base_start (int): Starting index for the first page.
            remaining_papers (int): Number of papers remaining to fetch.
            page_size (int): Number of papers to fetch per page.

        Returns:
            list[PageParam]: List of page parameters for batch requests.
        """
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
        """
        Fetch multiple pages of results from arXiv API.

        Args:
            query (str): The search query string.
            page_params (list[PageParam]): List of page parameters for batch requests.
            sort_by (Optional[SortCriterion]): Criterion to sort results by.
            sort_order (Optional[SortOrder]): Order of sorting.

        Returns:
            list[SearchResult]: List of search results from batch requests.
        """
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

    def _build_query_params(self, search_params: SearchParams) -> dict[str, str]:
        """
        Build query parameters for arXiv API request.

        Args:
            search_params (SearchParams): Search parameters for the API request.

        Returns:
            dict: Query parameters for the API request.

        Raises:
            QueryBuildError: If there's an error building the search query.
        """
        query_params = self.__base_params(search_params)
        self.__add_optional_params(query_params, search_params)
        return query_params

    @staticmethod
    def __base_params(params: SearchParams) -> dict[str, str]:
        """Create base query parameters."""
        query_params: dict[str, str] = {"start": str(params.start or 0)}
        if params.query is not None:
            query_params["search_query"] = params.query
        return query_params

    @staticmethod
    def __add_optional_params(query: dict[str, str], params: SearchParams) -> None:
        """Add optional parameters to query dict in-place."""
        if params.max_results is not None:
            query["max_results"] = str(params.max_results)

        if params.id_list:
            query["id_list"] = ",".join(params.id_list)

        if params.sort_by is not None:
            query["sortBy"] = params.sort_by.value

        if params.sort_order is not None:
            query["sortOrder"] = params.sort_order.value

    async def download_paper(
        self,
        paper: Paper,
        filename: Optional[str] = None,
    ) -> Optional[None]:
        """Download a single paper from arXiv.

        Args:
            paper (Paper): Paper object containing download information.
            filename (Optional[str], optional): Custom filename for the downloaded
                paper. Defaults to None.

        Returns:
            Optional[None]: None if downloader is disabled.

        Raises:
            PaperDownloadException: If paper download fails.
        """
        if downloader := self.downloader:
            await downloader.download_paper(paper, filename)
        return None

    async def download_search_result(
        self,
        search_result: SearchResult,
    ) -> Optional[DownloadTracker]:
        """Download all papers from a search result.

        Args:
            search_result (SearchResult): Search result containing papers to download.

        Returns:
            Optional[DownloadTracker]: Download tracker if downloader is enabled,
                None otherwise.
        """
        if downloader := self.downloader:
            return await downloader.batch_download(search_result)
        return None

    @staticmethod
    def _merge_paper_lists(
        papers_lists: list[list[Paper]], *, keep_latest: bool = True
    ) -> list[Paper]:
        """
        Merge multiple lists of papers into a single list.

        Args:
            papers_lists (list[list[Paper]]): List of lists of papers to merge.
            keep_latest (bool): Whether to keep the latest version of each paper.

        Returns:
            list[Paper]: List of unique papers.

        Raises:
            ValueError: If papers_lists is empty.
        """
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
        """Aggregate multiple search results into a single result.

        Args:
            results (list[SearchResult]): List of search results to aggregate.

        Returns:
            SearchResult: Combined search result with merged papers and metadata.

        Raises:
            ValueError: If results list is empty.
        """
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
            f"papers in {aggregated_result.metadata.duration_seconds} seconds"
        )

        return aggregated_result

    async def close(self) -> None:
        """Close the client and cleanup resources."""
        await self._session_manager.close()

    async def __aenter__(self) -> "ArxivClient":
        """Enter the async context manager.

        Returns:
            ArxivClient: The client instance.
        """
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Exit the async context manager and cleanup resources.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.
        """
        await self.close()
