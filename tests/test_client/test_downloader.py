from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from typing_extensions import Self

import pytest
from pytest_mock import MockerFixture

from aioarxiv.client.downloader import ArxivDownloader, DownloadTracker
from aioarxiv.config import ArxivConfig
from aioarxiv.exception import PaperDownloadException
from aioarxiv.models import Paper


class MockResponse:
    """Mock HTTP response supporting the async context manager protocol."""

    def __init__(self, status: int = 200, content: bytes = b"mock_pdf_content") -> None:
        """
        Initialize the mock response.

        Args:
            status: HTTP status code.
            content: Response body.
        """
        self.status = status
        self._content = content
        self.released = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        self.released = True

    @property
    def content(self) -> Any:
        """
        Mock streaming response content.

        Returns:
            Any: Async chunk generator.
        """
        outer_content = self._content

        class MockStreamReader:
            @staticmethod
            async def iter_chunked(size: int) -> AsyncGenerator[bytes, None]:  # noqa: ARG004
                yield outer_content

        return MockStreamReader()


@pytest.fixture
def fast_retry_config(mock_config: ArxivConfig) -> ArxivConfig:
    """Config with minimal retry waits to keep tests fast."""
    return mock_config.model_copy(update={"max_retries": 2, "min_wait": 0.01})


@pytest.mark.asyncio
async def test_single_download(
    mock_downloader: ArxivDownloader,
    sample_paper: Paper,
    mocker: MockerFixture,
) -> None:
    mock_content = b"mock_pdf_content"
    mock_response = MockResponse(status=200, content=mock_content)
    request_mock = mocker.patch.object(
        mock_downloader.session_manager, "request", new_callable=mocker.AsyncMock
    )
    request_mock.return_value = mock_response

    filename = "test_paper.pdf"
    result_path = await mock_downloader.download_paper(sample_paper, filename)

    expected_path = mock_downloader.download_dir / filename
    assert result_path == expected_path
    assert expected_path.exists(), "Downloaded file should exist"

    content = expected_path.read_bytes()
    assert content == mock_content, "File content should match mock content"

    assert mock_response.released, "Response should be released after download"
    request_mock.assert_called_once_with("GET", str(sample_paper.pdf_url))


@pytest.mark.asyncio
async def test_retry_exhaustion_records_failure(
    download_dir: Path,
    fast_retry_config: ArxivConfig,
    sample_paper: Paper,
    mocker: MockerFixture,
) -> None:
    """Exhausted retries must surface as a failure, not a silent success."""
    session_manager = mocker.Mock()
    session_manager.request = mocker.AsyncMock(side_effect=RuntimeError("boom"))
    downloader = ArxivDownloader(
        session_manager=session_manager,
        download_dir=download_dir,
        config=fast_retry_config,
    )
    mocker.patch("asyncio.sleep", new=mocker.AsyncMock())

    tracker = DownloadTracker(total=1)
    await downloader._download_with_context(sample_paper, tracker)

    assert tracker.failed == 1
    assert tracker.completed == 0
    assert len(tracker.failed_papers) == 1
    failed_paper, error = tracker.failed_papers[0]
    assert failed_paper is sample_paper
    assert isinstance(error, PaperDownloadException)
    assert session_manager.request.call_count == fast_retry_config.max_retries


@pytest.mark.asyncio
async def test_failed_download_keeps_existing_file(
    download_dir: Path,
    fast_retry_config: ArxivConfig,
    sample_paper: Paper,
    mocker: MockerFixture,
) -> None:
    """A failed download must not delete a pre-existing final file."""
    config = fast_retry_config.model_copy(update={"max_retries": 1})
    session_manager = mocker.Mock()
    session_manager.request = mocker.AsyncMock(
        return_value=MockResponse(status=503, content=b"")
    )
    downloader = ArxivDownloader(
        session_manager=session_manager,
        download_dir=download_dir,
        config=config,
    )

    filename = "existing_paper.pdf"
    existing = download_dir / filename
    existing.write_bytes(b"previous content")

    with pytest.raises(PaperDownloadException):
        await downloader.download_paper(sample_paper, filename)

    assert existing.exists()
    assert existing.read_bytes() == b"previous content"
    assert not existing.with_suffix(".tmp").exists()


@pytest.mark.asyncio
async def test_batch_download_records_missing_pdf_url(
    mock_downloader: ArxivDownloader,
    sample_paper: Paper,
    sample_search_result: Any,
) -> None:
    """Papers without a PDF URL are recorded as failed, not downloaded."""
    paper = sample_paper.model_copy(update={"pdf_url": None})
    search_result = sample_search_result.model_copy(update={"papers": [paper]})

    tracker = await mock_downloader.batch_download(search_result)

    assert tracker.total == 1
    assert tracker.failed == 1
    assert tracker.completed == 0


def test_tracker_progress_guards_zero_total() -> None:
    tracker = DownloadTracker(total=0)
    assert tracker.progress == 0.0

    tracker = DownloadTracker(total=2)
    tracker.add_completed()
    assert tracker.progress == 50.0
