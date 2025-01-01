# tests/test_client.py
from datetime import datetime
import pathlib
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from aiohttp import ClientResponse
from pydantic import AnyUrl, HttpUrl
import pytest
from yarl import URL

from aioarxiv.client.arxiv_client import ArxivClient
from aioarxiv.config import ArxivConfig, default_config
from aioarxiv.models import (
    Author,
    BasicInfo,
    Category,
    Metadata,
    Paper,
    PrimaryCategory,
    SearchParams,
    SearchResult,
    SortCriterion,
    SortOrder,
)

SAMPLE_XML_PATH = pathlib.Path(__file__).parent.parent / "data" / "sample.xml"


@pytest.fixture
def mock_session_manager(mocker):
    """创建模拟的会话管理器"""
    manager = mocker.Mock()
    manager.request = mocker.AsyncMock()
    manager.close = mocker.AsyncMock()
    return manager


@pytest.fixture
def mock_response(mocker, mock_feed_response):
    """创建模拟的 HTTP 响应"""
    response = mocker.Mock(spec=ClientResponse)
    response.status = 200
    response.text = mocker.AsyncMock(return_value=mock_feed_response)
    response.url = "http://export.arxiv.org/api/query"
    return response


@pytest.fixture
def mock_datetime(mocker):
    """固定时间为 2025-01-01 00:02:00 UTC"""
    fixed_dt = datetime(2025, 1, 1, 0, 2, 0, tzinfo=ZoneInfo("UTC"))
    datetime_mock = mocker.patch("aioarxiv.models.datetime")
    datetime_mock.now.return_value = fixed_dt
    return fixed_dt


@pytest.fixture
def client(mock_session_manager):
    """创建测试客户端"""
    return ArxivClient(session_manager=mock_session_manager)


@pytest.fixture
def sample_author():
    """创建示例作者"""
    return Author(name="BalconyJH", affiliation="Test University")


@pytest.fixture
def sample_category():
    """创建示例分类"""
    return Category(
        primary=PrimaryCategory(
            term="cs.AI",
            scheme=AnyUrl("http://arxiv.org/schemas/atom"),
            label="Artificial Intelligence",
        ),
        secondary=["cs.LG", "stat.ML"],
    )


@pytest.fixture
def sample_basic_info(sample_author, sample_category, mock_datetime):
    """创建示例基础信息"""
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
def sample_paper(sample_basic_info):
    """创建示例论文"""
    return Paper(
        info=sample_basic_info,
        doi="10.1234/test.123",
        journal_ref="Test Journal Vol.1",
        pdf_url=HttpUrl("http://arxiv.org/pdf/2312.12345"),
        comment="Test comment",
    )


@pytest.fixture
def sample_metadata(mock_datetime):
    """创建示例元数据"""
    return Metadata(
        start_time=mock_datetime,
        missing_results=0,
        pagesize=10,
        source=URL("http://export.arxiv.org/api/query"),
        end_time=None,
    )


@pytest.fixture
def sample_search_result(sample_paper, sample_metadata):
    """创建示例搜索结果"""
    return SearchResult(
        papers=[sample_paper],
        total_result=1,
        page=1,
        has_next=False,
        query_params=SearchParams(query="test query"),  # pyright: ignore [reportCallIssue]
        metadata=sample_metadata,
    )


@pytest.fixture
def mock_feed_response():
    """创建模拟的 XML feed 响应"""
    return SAMPLE_XML_PATH.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_client_initialization():
    """测试客户端初始化"""
    client = ArxivClient()
    assert client._config == default_config
    assert client._enable_downloader is False
    assert client.download_dir is None

    custom_config = ArxivConfig(page_size=50)
    download_dir = Path("./downloads")
    client = ArxivClient(
        config=custom_config, enable_downloader=True, download_dir=download_dir
    )
    assert client._config == custom_config
    assert client._enable_downloader is True
    assert client.download_dir == download_dir


@pytest.mark.asyncio
async def test_build_search_metadata(client, sample_search_result, sample_paper):
    """测试搜索元数据构建"""
    # 创建一个新的元数据对象，确保 source 是 URL 类型
    metadata = Metadata(
        start_time=datetime.now(tz=ZoneInfo(default_config.timezone)),
        end_time=datetime.now(tz=ZoneInfo(default_config.timezone)),
        missing_results=0,
        pagesize=10,
        source=URL("http://export.arxiv.org/api/query"),
    )

    # 更新 search_result 的元数据
    search_result = sample_search_result.model_copy(update={"metadata": metadata})

    updated_result = client._build_search_metadata(
        search_result, page=1, batch_size=10, papers=[sample_paper]
    )

    assert len(updated_result.papers) == 1
    assert updated_result.page == 1
    assert updated_result.has_next is False
    assert updated_result.metadata.pagesize == client._config.page_size
    assert isinstance(updated_result.metadata.source, URL)


@pytest.mark.asyncio
async def test_metadata_duration_calculation(mock_datetime):
    """测试元数据持续时间计算"""
    start_time = mock_datetime
    end_time = datetime(2025, 1, 1, 0, 2, 1, tzinfo=ZoneInfo("UTC"))

    metadata = Metadata(
        start_time=start_time,
        end_time=end_time,
        missing_results=0,
        pagesize=10,
        source=URL("http://test.com"),
    )

    assert metadata.duration_seconds == 1.000
    assert metadata.duration_ms == 1000.000


@pytest.mark.asyncio
async def test_search_with_params(client, mock_response, mock_session_manager):
    """测试带参数的搜索"""
    mock_session_manager.request.return_value = mock_response

    params = {
        "query": "neural networks",
        "max_results": 5,
        "sort_by": SortCriterion.SUBMITTED,
        "sort_order": SortOrder.ASCENDING,
    }

    results = []
    async for result in client.search(**params):
        results.append(result)

    assert len(results) == 5
    result = results[0]

    assert result.total_result == 218712
    assert result.page == 1
    assert len(result.papers) == 1

    paper = result.papers[0]
    assert paper.info.id == "0102536v1"
    assert (
        paper.info.title
        == "Impact of Electron-Electron Cusp on Configuration Interaction Energies"
    )

    authors = paper.info.authors
    assert len(authors) == 5
    assert authors[0].name == "David Prendergast"
    assert authors[0].affiliation == "Department of Physics"
    assert authors[1].name == "M. Nolan"
    assert authors[1].affiliation == "NMRC, University College, Cork, Ireland"

    assert paper.doi == "10.1063/1.1383585"
    assert paper.journal_ref == "J. Chem. Phys. 115, 1626 (2001)"
    assert "11 pages, 6 figures, 3 tables" in paper.comment
    assert paper.info.categories.primary.term == "cond-mat.str-el"

    call_args = mock_session_manager.request.call_args
    assert call_args is not None
    _, kwargs = call_args

    query_params = kwargs["params"]
    assert query_params["search_query"] == "neural networks"
    assert query_params["max_results"] == default_config.page_size
    assert query_params["sortBy"] == SortCriterion.SUBMITTED.value
    assert query_params["sortOrder"] == SortOrder.ASCENDING.value


def test_search_result_computed_fields(sample_search_result):
    """测试搜索结果的计算字段"""
    assert sample_search_result.papers_count == 1
    assert isinstance(sample_search_result.id, UUID)


@pytest.mark.asyncio
async def test_client_context_manager(client):
    """测试客户端上下文管理器"""
    async with client as c:
        assert isinstance(c, ArxivClient)

    client._session_manager.close.assert_awaited_once()
