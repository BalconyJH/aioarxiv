from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from yarl import URL

from aioarxiv.client.arxiv_client import ArxivClient
from aioarxiv.models import (
    Metadata,
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


# @pytest.mark.asyncio
# async def test_search_with_params(
#     mock_arxiv_client, mock_response, mock_session_manager, mock_config
# ):
#     """测试带参数的搜索"""
#     mock_session_manager.request.return_value = mock_response
#
#     params = {
#         "query": "neural networks",
#         "max_results": 5,
#         "sort_by": SortCriterion.SUBMITTED,
#         "sort_order": SortOrder.ASCENDING,
#     }
#
#     result = await mock_arxiv_client.search(**params)
#
#     assert result.total_result == 218712
#
#     paper = result.papers[0]
#     assert paper.info.id == "0102536v1"
#     assert (
#         paper.info.title
#         == "Impact of Electron-Electron Cusp on Configuration Interaction Energies"
#     )
#
#     authors = paper.info.authors
#     assert len(authors) == 5
#     assert authors[0].name == "David Prendergast"
#     assert authors[0].affiliation == "Department of Physics"
#     assert authors[1].name == "M. Nolan"
#     assert authors[1].affiliation == "NMRC, University College, Cork, Ireland"
#
#     assert paper.doi == "10.1063/1.1383585"
#     assert paper.journal_ref == "J. Chem. Phys. 115, 1626 (2001)"
#     assert "11 pages, 6 figures, 3 tables" in paper.comment
#     assert paper.info.categories.primary.term == "cond-mat.str-el"
#
#     call_args = mock_session_manager.request.call_args
#     assert call_args is not None
#     _, kwargs = call_args
#
#     query_params = kwargs["params"]
#     assert query_params["search_query"] == "neural networks"
#     assert query_params["max_results"] == mock_config.page_size
#     assert query_params["sortBy"] == SortCriterion.SUBMITTED.value
#     assert query_params["sortOrder"] == SortOrder.ASCENDING.value


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
