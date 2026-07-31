import asyncio
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing_extensions import Self, overload
from zoneinfo import ZoneInfo

from aiohttp import ClientResponse, ServerTimeoutError

from aioarxiv.config import ArxivConfig, default_config
from aioarxiv.exception import (
    HTTPException,
    QueryBuildError,
    RateLimitException,
    TimeoutException,
)
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

MAX_TOTAL_RESULTS = 30000
"""Deep-paging cap of the arXiv API: requests with
``start + max_results > 30000`` are rejected with HTTP 400."""


class ArxivClient:
    def __init__(
        self,
        config: ArxivConfig | None = None,
        session_manager: SessionManager | None = None,
        *,
        enable_downloader: bool = False,
        download_dir: Path | None = None,
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
        self._downloader: ArxivDownloader | None = None
        ConfigManager.set_config(config=self._config)
        logger.info(f"ArxivClient initialized with config: {self._config.model_dump()}")
        if self._config.rate_limit_calls <= 0 or self._config.rate_limit_period <= 0:
            # rate_limit_calls == 0 disables rate limiting; no interval to check.
            return
        average_interval = (
            self._config.rate_limit_period / self._config.rate_limit_calls
        )
        if average_interval < 3.0:
            logger.warning(
                f"Configuration for rate limit calls and period ({average_interval}/s) may cause rate limiting due to "
                f"arXiv API policy which limits to 1 request every 3 seconds. "
                "Please refer to the (arXiv API documentation)[https://info.arxiv.org/help/api/tou.html] "
                "for more details."
            )

    @property
    def downloader(self) -> ArxivDownloader | None:
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
        papers: list[Paper],
    ) -> SearchResult:
        """Build search result metadata with updated information.

        Args:
            searchresult (SearchResult): Search result object.
            page (int): Page number of the search result.
            papers (list[Paper]): List of papers fetched in the batch.

        Returns:
            SearchResult: Search result object with updated metadata.
        """
        # More results exist beyond the absolute window this page covers.
        consumed_end = (searchresult.query_params.start or 0) + len(papers)
        has_next = searchresult.total_result > consumed_end
        metadata = searchresult.metadata.model_copy(
            update={
                "end_time": datetime.now(tz=ZoneInfo(self._config.timezone)),
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
        query: str | None = None,
        start: int | None = None,
        id_list: list[str] | None = None,
        max_results: int | None = None,
        sort_by: SortCriterion | None = None,
        sort_order: SortOrder | None = None,
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

        Note:
            ``query`` and ``id_list`` may be combined; the API then applies
            ``search_query`` as a filter within ``id_list``.
        """
        # Clamp the first request to the deep-paging window as well: with
        # max_results unset and start near the cap, a full page would end
        # past MAX_TOTAL_RESULTS and draw HTTP 400.
        page_size = min(
            self._config.page_size,
            max_results or self._config.page_size,
            MAX_TOTAL_RESULTS - (start or 0),
        )

        params = SearchParams(
            query=query,
            id_list=id_list,
            start=start,
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
            searchresult=result,
            page=1,
            papers=result.papers,
        )

        # total_result is an absolute match count, so compare it against the
        # absolute end of the fetched window, not just the papers received.
        needs_more = (
            id_list is None
            and max_results is not None
            and max_results > len(result.papers)
            and result.total_result > (start or 0) + len(result.papers)
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
            papers=result.papers,
        )

    async def _create_batch_tasks(
        self,
        query: str,
        page_params: list[PageParam],
        sort_by: SortCriterion | None = None,
        sort_order: SortOrder | None = None,
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
        id_list: list[str] | None = ...,
        max_results: int | None = ...,
        sort_by: SortCriterion | None = ...,
        sort_order: SortOrder | None = ...,
        start: int | None = ...,
    ) -> SearchResult: ...

    @overload
    async def search(
        self,
        query: None = ...,
        id_list: list[str] = ...,
        max_results: int | None = ...,
        sort_by: SortCriterion | None = ...,
        sort_order: SortOrder | None = ...,
        start: int | None = ...,
    ) -> SearchResult: ...

    async def search(
        self,
        query: str | None = None,
        id_list: list[str] | None = None,
        max_results: int | None = None,
        sort_by: SortCriterion | None = None,
        sort_order: SortOrder | None = None,
        start: int | None = None,
    ) -> SearchResult:
        """
        Search arXiv papers via a keyword query, an arXiv ID list, or both.

        When both ``query`` and ``id_list`` are given, the API applies the
        query as a filter within the ID list.

        Args:
            query (Optional[str]): Keyword-based query string.
            id_list (Optional[list[str]]): List of arXiv IDs to retrieve.
            max_results (Optional[int]): Max results for query search.
            sort_by (Optional[SortCriterion]): Sorting criterion for query search.
            sort_order (Optional[SortOrder]): Sorting order for query search.
            start (Optional[int]): Start index.

        Returns:
            SearchResult: Search results object.

        Raises:
            QueryBuildError: If neither ``query`` nor ``id_list`` is given, or
                the requested window exceeds the API's 30000-result cap.
        """
        try:
            if query is None and not id_list:
                raise QueryBuildError(
                    "Either query or id_list (or both) must be provided"
                )
            self._validate_result_window(start, max_results)
            if query is not None:
                return await self._search_by_query(
                    query=query,
                    id_list=id_list,
                    max_results=max_results,
                    sort_by=sort_by,
                    sort_order=sort_order,
                    start=start,
                )
            return await self._search_by_ids(
                id_list=id_list or [],
                max_results=max_results,
                sort_by=sort_by,
                sort_order=sort_order,
                start=start,
            )
        except Exception as e:
            logger.opt(exception=True).error(f"Search operation failed: {e!s}")
            raise

    @staticmethod
    def _validate_result_window(start: int | None, max_results: int | None) -> None:
        """Reject windows the arXiv API would refuse with HTTP 400.

        Args:
            start (Optional[int]): Requested start index.
            max_results (Optional[int]): Requested result count.

        Raises:
            QueryBuildError: If ``start`` reaches or ``start + max_results``
                exceeds 30000.
        """
        requested_end = (start or 0) + (max_results or 0)
        if (start or 0) >= MAX_TOTAL_RESULTS or requested_end > MAX_TOTAL_RESULTS:
            raise QueryBuildError(
                f"start + max_results must not exceed {MAX_TOTAL_RESULTS} "
                f"(requested window ends at {requested_end}); the arXiv API "
                "rejects deeper paging with HTTP 400. Refine the query or "
                "request a smaller window."
            )

    async def _search_by_query(
        self,
        query: str,
        id_list: list[str] | None = None,
        max_results: int | None = None,
        sort_by: SortCriterion | None = None,
        sort_order: SortOrder | None = None,
        start: int | None = None,
    ) -> SearchResult:
        first_page_result, should_fetch_more = await self._prepare_initial_search(
            query=query,
            id_list=id_list,
            start=start,
            max_results=max_results,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        if not should_fetch_more:
            return first_page_result

        papers_received = len(first_page_result.papers)
        # Continue from what the first page actually consumed, not from
        # config.page_size: the first request may have been clamped or the
        # API may have returned a short page.
        consumed_end = (start or 0) + papers_received
        remaining_papers = min(
            (max_results - papers_received)
            if max_results
            else first_page_result.total_result,
            first_page_result.total_result - consumed_end,
            MAX_TOTAL_RESULTS - consumed_end,
        )

        if remaining_papers <= 0:
            return first_page_result

        page_params = self._generate_page_params(
            base_start=consumed_end,
            remaining_papers=remaining_papers,
            page_size=self._config.page_size,
        )

        logger.debug(f"Fetching {len(page_params)} additional pages")

        additional_results, missing_results = await self._fetch_batch_results(
            query=query,
            page_params=page_params,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Concurrent middle pages may legitimately come back short; count the
        # aggregate shortfall against the requested window instead of
        # pretending completeness.
        fetched_additional = sum(len(result.papers) for result in additional_results)
        shortfall = remaining_papers - fetched_additional - missing_results
        if shortfall > 0:
            missing_results += shortfall

        aggregated = self.aggregate_search_results(
            [first_page_result, *additional_results]
        )
        if missing_results:
            aggregated = aggregated.model_copy(
                update={
                    "metadata": aggregated.metadata.model_copy(
                        update={
                            "missing_results": aggregated.metadata.missing_results
                            + missing_results,
                        }
                    ),
                }
            )
        return aggregated

    async def _search_by_ids(
        self,
        id_list: list[str],
        max_results: int | None = None,
        sort_by: SortCriterion | None = None,
        sort_order: SortOrder | None = None,
        start: int | None = None,
    ) -> SearchResult:
        result, _ = await self._prepare_initial_search(
            id_list=id_list,
            max_results=max_results,
            sort_by=sort_by,
            sort_order=sort_order,
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
            RateLimitException: If the API responds with HTTP 429.
            HTTPException: If the API request returns another non-200 status.
            TimeoutException: If the request times out.
        """
        query_params = self._build_query_params(params)
        try:
            response = await self._session_manager.request(
                "GET", str(self._config.base_url), params=query_params
            )
        except (asyncio.TimeoutError, ServerTimeoutError) as e:
            raise TimeoutException(
                timeout=self._config.timeout,
                proxy=self._config.proxy,
                link=str(self._config.base_url),
            ) from e

        if response.status == 200:
            return response

        # Return the connection to the pool before raising; status and
        # headers stay readable after release.
        response.release()
        if response.status == 429:
            raise RateLimitException(
                retry_after=self._parse_retry_after(response.headers.get("Retry-After"))
            )
        if response.status == 400:
            raise HTTPException(
                400,
                "arXiv API rejected the request (HTTP 400); this typically "
                f"means start + max_results exceeded {MAX_TOTAL_RESULTS} or "
                "the query is malformed.",
            )
        raise HTTPException(response.status)

    @staticmethod
    def _parse_retry_after(header_value: str | None) -> int | None:
        """Parse a ``Retry-After`` header value in seconds form.

        Args:
            header_value (Optional[str]): Raw header value, if present.

        Returns:
            Optional[int]: Seconds to wait, or None if absent or in the
            HTTP-date form.
        """
        if header_value is None:
            return None
        try:
            return int(header_value)
        except ValueError:
            return None

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
        sort_by: SortCriterion | None,
        sort_order: SortOrder | None,
    ) -> tuple[list[SearchResult], int]:
        """
        Fetch multiple pages of results from arXiv API.

        Args:
            query (str): The search query string.
            page_params (list[PageParam]): List of page parameters for batch requests.
            sort_by (Optional[SortCriterion]): Criterion to sort results by.
            sort_order (Optional[SortOrder]): Order of sorting.

        Returns:
            tuple[list[SearchResult], int]: Successful page results and the
            number of papers lost to failed pages.
        """
        tasks = await self._create_batch_tasks(query, page_params, sort_by, sort_order)

        if not tasks:
            return [], 0

        responses = await asyncio.gather(*tasks, return_exceptions=True)
        valid_results: list[SearchResult] = []
        missing_results = 0

        for param, response in zip(page_params, responses, strict=True):
            if isinstance(response, SearchResult):
                valid_results.append(response)
            else:
                missing_results += param.end - param.start
                logger.opt(exception=response).error(f"Batch task failed: {response!s}")

        return valid_results, missing_results

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
        filename: str | None = None,
    ) -> Path | None:
        """Download a single paper from arXiv.

        Args:
            paper (Paper): Paper object containing download information.
            filename (Optional[str], optional): Custom filename for the downloaded
                paper. Defaults to None.

        Returns:
            Optional[Path]: Path of the downloaded file, or None if the
            downloader is disabled.

        Raises:
            PaperDownloadException: If paper download fails.
        """
        if downloader := self.downloader:
            return await downloader.download_paper(paper, filename)
        return None

    async def download_search_result(
        self,
        search_result: SearchResult,
    ) -> DownloadTracker | None:
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

    async def __aenter__(self) -> Self:
        """Enter the async context manager.

        Returns:
            Self: The client instance.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager and cleanup resources.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.
        """
        await self.close()
