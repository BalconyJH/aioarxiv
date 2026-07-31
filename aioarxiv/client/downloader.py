import asyncio
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import aiofiles
from platformdirs import user_documents_path
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    stop_after_attempt,
    wait_exponential,
)

from aioarxiv.config import ArxivConfig, default_config
from aioarxiv.exception import PaperDownloadException
from aioarxiv.models import Paper, SearchResult
from aioarxiv.utils import format_datetime, sanitize_title
from aioarxiv.utils.log import ConfigManager, logger
from aioarxiv.utils.session import SessionManager


class DownloadTracker:
    """A tracker that manages and monitors batch download progress for research papers.

    This class maintains the state of a batch download operation, including success,
    failure counts, and timing information. It provides methods to update progress
    and access statistics about the download operation.

    Args:
        total (int): The total number of papers to be downloaded in this batch.
        tz (Optional[ZoneInfo]): Timezone for the tracker's timestamps. Falls back
            to the active configuration's timezone when omitted.

    Usage:
        ```python
        # Create a tracker for downloading 10 papers
        tracker = DownloadTracker(total=10)

        # Update progress as downloads complete
        tracker.add_completed()

        # Record failed downloads with error information
        try:
            await download_paper(paper)
        except Exception as e:
            tracker.add_failed(paper, e)

        # Check progress
        progress = tracker.progress  # returns percentage complete
        failed_papers = tracker.failed_papers  # get list of failed downloads
        ```
    """

    def __init__(self, total: int, tz: ZoneInfo | None = None) -> None:
        self.total: int = total
        self.completed: int = 0
        self.failed: int = 0
        tz = tz or ZoneInfo(ConfigManager.get_config().timezone)
        self.start_time: datetime = datetime.now(tz)
        self.end_time: datetime | None = None
        self._failed_papers: list[tuple[Paper, Exception]] = []

    def add_failed(self, paper: Paper, error: Exception) -> None:
        """Records a paper that failed to download.

        Args:
            paper (Paper): The paper object that failed to download.
            error (Exception): The exception that occurred during download.
        """
        self.failed += 1
        self._failed_papers.append((paper, error))

    def add_completed(self) -> None:
        """Records a successfully completed paper download."""
        self.completed += 1

    @property
    def progress(self) -> float:
        """The current download progress as a percentage.

        Returns:
            float: The percentage of papers processed (completed + failed).
            0.0 when the batch is empty.
        """
        if self.total == 0:
            return 0.0
        return (self.completed + self.failed) / self.total * 100

    @property
    def failed_papers(self) -> list[tuple[Paper, Exception]]:
        """List of papers that failed to download with their corresponding errors.

        Returns:
            list[tuple[Paper, Exception]]: A list of tuples containing the failed
                paper objects and their associated error exceptions.
        """
        return self._failed_papers


class ArxivDownloader:
    """A concurrent downloader for arXiv research papers.

    This class manages the asynchronous download of arXiv papers, handling concurrent
    requests, file management, and error recovery. It supports batch downloads with
    automatic retry mechanisms and progress tracking.

    Args:
        session_manager (Optional[SessionManager]): Custom session manager for requests.
        download_dir (Optional[Path]): Custom directory for downloaded papers.
        config (Optional[ArxivConfig]): Configuration for the downloader.

    Usage:
        ```python
        # Create a downloader with default settings
        downloader = ArxivDownloader()

        # Download a single paper
        await downloader.download_paper(paper)

        # Batch download papers from search results
        search_result = await arxiv.search("quantum computing")
        tracker = await downloader.batch_download(search_result)

        # Check download statistics
        print(f"Downloaded: {tracker.completed}")
        print(f"Failed: {tracker.failed}")
        ```
    """

    def __init__(
        self,
        session_manager: SessionManager | None = None,
        download_dir: Path | None = None,
        config: ArxivConfig | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._download_dir = download_dir
        self._config = config or default_config
        self._semaphore = asyncio.Semaphore(self._config.max_concurrent_requests)

    @property
    def session_manager(self) -> SessionManager:
        """The session manager used for HTTP requests.

        Returns:
            SessionManager: The current session manager instance, creating a new one
                if none exists.
        """
        if self._session_manager is None:
            self._session_manager = SessionManager()
        return self._session_manager

    @property
    def download_dir(self) -> Path:
        """The directory where downloaded papers are saved.

        Returns:
            Path: The path to the download directory, creating it if it doesn't exist.
        """
        if self._download_dir is None:
            self._download_dir = user_documents_path() / "aioarxiv"
        self._download_dir.mkdir(parents=True, exist_ok=True)
        return self._download_dir

    @staticmethod
    def file_name(paper: Paper) -> str:
        """Generates a sanitized filename for a paper.

        Args:
            paper (Paper): The paper object to generate a filename for.

        Returns:
            str: A sanitized filename including the paper title and update date.
        """
        file_name = f"{paper.info.title} {format_datetime(paper.info.updated)}"
        return f"{sanitize_title(file_name)}.pdf"

    def _prepare_paths(
        self, paper: Paper, filename: str | None = None
    ) -> tuple[Path, Path]:
        """Prepare file paths for downloading a paper.

        Args:
            paper (Paper): The paper object to download.
            filename (Optional[str]): Custom filename for the downloaded paper.

        Returns:
            tuple[Path, Path]: The final file path and temporary file path.
        """
        name = filename or self.file_name(paper)
        file_path = self.download_dir / name
        # Unique per attempt so concurrent downloads that resolve to the same
        # final name never write through a shared temp file. The dot prefix
        # keeps it hidden; staying in the same directory keeps replace atomic.
        temp_path = file_path.with_name(f".{file_path.name}.{uuid4().hex}.tmp")
        return file_path, temp_path

    async def _download_to_temp(self, url: str, temp_path: Path) -> None:
        """Download a file to a temporary location.

        The response is consumed inside its context manager so the underlying
        connection is released on both success and error paths.

        Args:
            url (str): The URL to download the file from.
            temp_path (Path): The temporary file path to save the downloaded content.

        Raises:
            PaperDownloadException: If the server responds with a non-200 status.
        """
        async with self._semaphore:
            response = await self.session_manager.request("GET", url)
            async with response:
                if response.status != 200:
                    raise PaperDownloadException(f"HTTP status {response.status}")

                async with aiofiles.open(temp_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)

    @staticmethod
    def _log_retry(retry_state: RetryCallState) -> None:
        """Log a failed download attempt before the retry sleep.

        Args:
            retry_state (RetryCallState): Current tenacity retry state.
        """
        outcome = retry_state.outcome
        error = outcome.exception() if outcome is not None else None
        logger.warning(
            f"Download attempt {retry_state.attempt_number} failed: {error!s}; retrying"
        )

    async def download_paper(self, paper: Paper, filename: str | None = None) -> Path:
        """Download a single paper with retries.

        Retries up to ``config.max_retries`` attempts with exponential backoff
        starting at ``config.min_wait`` seconds; the final failure propagates.

        Args:
            paper (Paper): Paper instance to be downloaded.
            filename (Optional[str]): Custom filename for the downloaded paper.

        Returns:
            Path: Path of the downloaded file.

        Raises:
            PaperDownloadException: If the download fails after all retries.
        """
        retryer = AsyncRetrying(
            stop=stop_after_attempt(max(1, self._config.max_retries)),
            wait=wait_exponential(multiplier=1, min=self._config.min_wait),
            before_sleep=self._log_retry,
            reraise=True,
        )
        return await retryer(self._download_once, paper, filename)

    async def _download_once(self, paper: Paper, filename: str | None) -> Path:
        """Perform a single download attempt.

        On failure only the temporary file is removed; a pre-existing final
        file is never touched.

        Args:
            paper (Paper): Paper instance to be downloaded.
            filename (Optional[str]): Custom filename for the downloaded paper.

        Returns:
            Path: Path of the downloaded file.

        Raises:
            PaperDownloadException: If the download attempt fails.
        """
        file_path, temp_path = self._prepare_paths(paper, filename)
        logger.info(f"Starting paper download: {paper.pdf_url}")

        try:
            await self._download_to_temp(str(paper.pdf_url), temp_path)
            temp_path.replace(file_path)
        except Exception as e:
            logger.error(f"Download failed: {e}")
            temp_path.unlink(missing_ok=True)
            raise PaperDownloadException(f"Download failed: {e}") from e

        logger.info(f"Download completed: {file_path}")
        file_size = file_path.stat().st_size
        logger.debug(f"File size: {file_size / 1024:.1f} KB")
        return file_path

    async def _download_with_context(
        self, paper: Paper, context: DownloadTracker
    ) -> None:
        """Download a paper and record the outcome on the tracker.

        Args:
            paper (Paper): Paper instance to be downloaded.
            context (DownloadTracker): Download tracking context.
        """
        try:
            await self.download_paper(paper)
            context.add_completed()
        except Exception as e:
            context.add_failed(paper, e)
            logger.error(
                f"Failed to download paper {paper.info.id}: {e!s}",
                extra={"paper_id": paper.info.id},
            )

    async def batch_download(
        self,
        search_result: SearchResult,
    ) -> DownloadTracker:
        """Batch download papers from a search result.

        Args:
            search_result (SearchResult): The search result object to download papers.

        Returns:
            DownloadTracker: The download context with progress and statistics.
        """
        context = DownloadTracker(
            len(search_result.papers), tz=ZoneInfo(self._config.timezone)
        )
        tasks = []

        for paper in search_result.papers:
            if paper.pdf_url:
                tasks.append(
                    asyncio.create_task(self._download_with_context(paper, context))
                )
            else:
                context.add_failed(paper, ValueError("No PDF URL available"))

        await asyncio.gather(*tasks)
        context.end_time = datetime.now(ZoneInfo(self._config.timezone))
        return context
