from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import ClientResponse
from pydantic import AnyUrl, HttpUrl
import pytest
from pytest_mock import MockerFixture
from yarl import URL

from aioarxiv.client.arxiv_client import ArxivClient
from aioarxiv.client.downloader import ArxivDownloader
from aioarxiv.config import ArxivConfig
from aioarxiv.models import (
    Author,
    BasicInfo,
    Category,
    Metadata,
    Paper,
    PrimaryCategory,
    SearchParams,
    SearchResult,
)
from aioarxiv.utils.session import SessionManager

SAMPLE_XML_PATH = Path(__file__).parent.parent / "data" / "sample.xml"


@pytest.fixture
def sample_author() -> Author:
    """
    Create a sample author for testing

    Returns:
        Author: A sample author with name and affiliation
    """
    return Author(name="BalconyJH", affiliation="Test University")


@pytest.fixture
def sample_category() -> Category:
    """
    Create a sample category for testing

    Returns:
        Category: A sample category with primary and secondary classifications
    """
    return Category(
        primary=PrimaryCategory(
            term="cs.AI",
            scheme=AnyUrl("http://arxiv.org/schemas/atom"),
            label="Artificial Intelligence",
        ),
        secondary=["cs.LG", "stat.ML"],
    )


@pytest.fixture
def sample_basic_info(
    sample_author: Author, sample_category: Category, mock_datetime: datetime
) -> BasicInfo:
    """
    Create sample basic information for a paper

    Args:
        sample_author: The sample author fixture
        sample_category: The sample category fixture
        mock_datetime: The mocked datetime fixture

    Returns:
        BasicInfo: Basic information for a test paper
    """
    return BasicInfo(
        id="2312.12345",
        title="Test Paper Title",
        summary="Test paper summary",
        authors=[sample_author],
        categories=sample_category,
        published=mock_datetime,
        updated=mock_datetime,
    )


@pytest.fixture
def sample_paper(sample_basic_info: BasicInfo) -> Paper:
    """
    Create a sample paper for testing

    Args:
        sample_basic_info: The sample basic information fixture

    Returns:
        Paper: A complete paper object with all fields
    """
    return Paper(
        info=sample_basic_info,
        doi="10.1234/test.123",
        journal_ref="Test Journal Vol.1",
        pdf_url=HttpUrl("http://test.pdf"),
        comment="Test comment",
    )


@pytest.fixture
def sample_metadata(mock_datetime: datetime) -> Metadata:
    """
    Create sample metadata for testing

    Args:
        mock_datetime: The mocked datetime fixture

    Returns:
        Metadata: Metadata object with test values
    """
    return Metadata(
        start_time=mock_datetime,
        missing_results=0,
        pagesize=10,
        source=URL("http://export.arxiv.org/api/query"),
        end_time=None,
    )


@pytest.fixture
def sample_search_result(
    sample_paper: Paper, sample_metadata: Metadata
) -> SearchResult:
    """
    Create a sample search result for testing

    Args:
        sample_paper: Sample paper fixture
        sample_metadata: Sample metadata fixture

    Returns:
        SearchResult: Sample search result with test data
    """
    return SearchResult(
        papers=[sample_paper],
        total_result=1,
        page=1,
        has_next=False,
        query_params=SearchParams(
            query="test query", id_list=None, sort_by=None, sort_order=None
        ),
        metadata=sample_metadata,
    )


@pytest.fixture
def sample_arxiv_feed() -> str:
    """
    Load sample arXiv XML feed content from file

    Returns:
        str: Content of the sample XML feed file
    """
    return SAMPLE_XML_PATH.read_text(encoding="utf-8")


@pytest.fixture
def mock_session_manager(mocker: MockerFixture) -> Any:
    """
    Create a mocked session manager for testing

    Args:
        mocker: pytest mocker fixture

    Returns:
        Any: Mocked session manager with async methods
    """
    manager = mocker.Mock()
    manager.request = mocker.AsyncMock()
    manager.close = mocker.AsyncMock()
    return manager


@pytest.fixture
def mock_response(mocker: MockerFixture, sample_arxiv_feed: str) -> Any:
    """
    Create a mocked HTTP response for testing

    Args:
        mocker: pytest mocker fixture
        sample_arxiv_feed: Sample arXiv feed XML content

    Returns:
        Any: Mocked response object with status and content
    """
    response = mocker.Mock(spec=ClientResponse)
    response.status = 200
    response.text = mocker.AsyncMock(return_value=sample_arxiv_feed)
    response.url = "http://export.arxiv.org/api/query"
    return response


@pytest.fixture
def mock_datetime(mocker: MockerFixture) -> datetime:
    """
    Mock datetime.now() and return a fixed time (2025-01-02 13:37:50 UTC)

    Args:
        mocker: pytest mocker fixture

    Returns:
        datetime: Fixed datetime object for testing
    """
    fixed_dt = datetime(2025, 1, 2, 13, 37, 50, tzinfo=ZoneInfo("UTC"))
    datetime_mock = mocker.patch("datetime.datetime")
    datetime_mock.now.return_value = fixed_dt
    datetime_mock.now.side_effect = (
        lambda tz=None: fixed_dt.astimezone(tz) if tz else fixed_dt
    )
    return fixed_dt


@pytest.fixture
def mock_arxiv_client(mock_session_manager: Any) -> ArxivClient:
    """
    Create an ArXiv client instance for testing

    Args:
        mock_session_manager: Mocked session manager

    Returns:
        ArxivClient: Configured ArXiv client for testing
    """
    return ArxivClient(session_manager=mock_session_manager)


@pytest.fixture
def mock_downloader(
    download_dir: Path,
    mock_config: ArxivConfig,
    mocker: MockerFixture,
) -> ArxivDownloader:
    """
    Create an ArXiv downloader instance for testing

    Args:
        download_dir: Directory for downloads
        mock_config: ArXiv configuration
        mocker: pytest mocker fixture

    Returns:
        ArxivDownloader: Configured downloader instance
    """
    session_manager = mocker.Mock(spec=SessionManager)
    session_manager.request = mocker.AsyncMock()
    return ArxivDownloader(
        session_manager=session_manager,
        download_dir=download_dir,
        config=mock_config,
    )


@pytest.fixture
def mock_config() -> ArxivConfig:
    """
    Provide default arXiv configuration

    Returns:
        ArxivConfig: Default configuration for arXiv client
    """
    return ArxivConfig()


@pytest.fixture
def download_dir(tmp_path: Path) -> Path:
    """
    Create and provide a temporary download directory

    Args:
        tmp_path: pytest temporary path fixture

    Returns:
        Path: Path to the created downloads directory
    """
    download_path = tmp_path / "downloads"
    download_path.mkdir(parents=True)
    return download_path
