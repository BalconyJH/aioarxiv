from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from yarl import URL

from aioarxiv.client.arxiv_client import ArxivClient
from aioarxiv.exception import QueryBuildError
from aioarxiv.models import (
    Metadata,
    SearchResult,
    SortCriterion,
    SortOrder,
)


@pytest.mark.asyncio
async def test_client_initialization(mock_config):
    """测试客户端初始化"""
    client = ArxivClient()
    assert client._config == mock_config
    assert client._enable_downloader is False
    assert client.download_dir is None

    custom_config = mock_config.model_copy(update={"page_size": 10})
    download_dir = Path("./downloads")
    client = ArxivClient(
        config=custom_config, enable_downloader=True, download_dir=download_dir
    )
    assert client._config == custom_config
    assert client._enable_downloader is True
    assert client.download_dir == download_dir


@pytest.mark.asyncio
async def test_build_search_metadata(
    mock_arxiv_client, sample_search_result, sample_paper, mock_config
):
    """测试搜索元数据构建"""
    # 创建一个新的元数据对象，确保 source 是 URL 类型
    metadata = Metadata(
        start_time=datetime.now(tz=ZoneInfo(mock_config.timezone)),
        end_time=datetime.now(tz=ZoneInfo(mock_config.timezone)),
        missing_results=0,
        pagesize=10,
        source=URL("http://export.arxiv.org/api/query"),
    )

    # 更新 search_result 的元数据
    search_result = sample_search_result.model_copy(update={"metadata": metadata})

    updated_result = mock_arxiv_client._build_search_result_metadata(
        search_result, page=1, batch_size=10, papers=[sample_paper]
    )

    assert len(updated_result.papers) == 1
    assert updated_result.page == 1
    assert updated_result.has_next is False
    assert updated_result.metadata.pagesize == mock_arxiv_client._config.page_size
    assert isinstance(updated_result.metadata.source, URL)


@pytest.mark.asyncio
async def test_metadata_duration_calculation(mock_datetime):
    """测试元数据持续时间计算"""
    start_time = mock_datetime
    end_time = mock_datetime + timedelta(seconds=1)

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
async def test_search_with_query(mock_arxiv_client, mocker, sample_search_result):
    """Test search with query string"""
    search_by_query = mocker.patch.object(
        mock_arxiv_client, "_search_by_query", return_value=sample_search_result
    )

    result = await mock_arxiv_client.search(
        query="physics",
        max_results=10,
        sort_by=SortCriterion.SUBMITTED,
        sort_order=SortOrder.ASCENDING,
        start=0,
    )

    assert isinstance(result, SearchResult)
    assert search_by_query.call_args.kwargs == {
        "query": "physics",
        "max_results": 10,
        "sort_by": SortCriterion.SUBMITTED,
        "sort_order": SortOrder.ASCENDING,
        "start": 0,
    }


@pytest.mark.asyncio
async def test_search_with_id_list(mock_arxiv_client, mocker, sample_search_result):
    """Test search with arXiv ID list"""
    search_by_ids = mocker.patch.object(
        mock_arxiv_client, "_search_by_ids", return_value=sample_search_result
    )
    id_list = ["2101.00123", "2101.00124"]

    result = await mock_arxiv_client.search(id_list=id_list, start=0)

    assert isinstance(result, SearchResult)
    assert search_by_ids.call_args.kwargs == {"id_list": id_list, "start": 0}


@pytest.mark.asyncio
async def test_search_no_parameters(mock_arxiv_client):
    """Test search with no parameters raises ValueError"""
    with pytest.raises(ValueError, match="必须提供 query 或 id_list 中的一个"):
        await mock_arxiv_client.search()


@pytest.mark.asyncio
async def test_search_both_query_and_id_list(mock_arxiv_client):
    """Test search with both query and id_list raises ValueError"""
    with pytest.raises(ValueError, match="query 和 id_list 不能同时使用"):
        await mock_arxiv_client.search(query="physics", id_list=["2101.00123"])


@pytest.mark.asyncio
async def test_search_error_handling(mock_arxiv_client, mocker):
    """Test search error handling"""
    mock_arxiv_client._search_by_query = mocker.patch.object(
        mock_arxiv_client,
        "_search_by_query",
        side_effect=QueryBuildError("Search query build failed"),
    )

    with pytest.raises(QueryBuildError):
        await mock_arxiv_client.search(query="physics")


def test_search_result_computed_fields(sample_search_result):
    """测试搜索结果的计算字段"""
    assert sample_search_result.papers_count == 1
    assert isinstance(sample_search_result.id, UUID)


@pytest.mark.asyncio
async def test_client_context_manager(mock_arxiv_client):
    """测试客户端上下文管理器"""
    async with mock_arxiv_client as c:
        assert isinstance(c, ArxivClient)

    mock_arxiv_client._session_manager.close.assert_awaited_once()
