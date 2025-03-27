from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from yarl import URL

from aioarxiv.client.arxiv_client import ArxivClient
from aioarxiv.exception import QueryBuildError
from aioarxiv.models import (
    BasicInfo,
    Metadata,
    Paper,
    SearchParams,
    SearchResult,
    SortCriterion,
    SortOrder,
)


@pytest.mark.asyncio
async def test_rate_limit_warning(mock_config, mocker):
    """Test rate limit warning when average interval is less than 3 seconds"""
    # Mock the logger
    mock_logger = mocker.patch("aioarxiv.client.arxiv_client.logger")

    config = mock_config.model_copy(
        update={
            "rate_limit_period": 5.0,
            "rate_limit_calls": 2,  # average_interval = 2.5s < 3.0s
        }
    )

    ArxivClient(config=config)

    mock_logger.warning.assert_called_once_with(
        "Configration for rate limit calls and period (2.5/s) may cause rate limiting due to "
        "arXiv API policy which limits to 1 request every 3 seconds. "
        "Please refer to the (arXiv API documentation)[https://info.arxiv.org/help/api/tou.html] "
        "for more details."
    )


@pytest.mark.asyncio
async def test_no_rate_limit_warning(mock_config, mocker):
    """Test no warning when rate limits are acceptable"""
    mock_logger = mocker.patch("aioarxiv.client.arxiv_client.logger")

    config = mock_config.model_copy(
        update={
            "rate_limit_period": 9.0,
            "rate_limit_calls": 2,  # average_interval = 4.5s > 3.0s
        }
    )

    ArxivClient(config=config)

    mock_logger.warning.assert_not_called()


@pytest.mark.asyncio
async def test_client_initialization(mock_config):
    """Test client initialization"""
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
    """Test building search metadata"""
    metadata = Metadata(
        start_time=datetime.now(tz=ZoneInfo(mock_config.timezone)),
        end_time=datetime.now(tz=ZoneInfo(mock_config.timezone)),
        missing_results=0,
        pagesize=10,
        source=URL("http://export.arxiv.org/api/query"),
    )

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
    """Test metadata duration calculation"""
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
    """Test search result computed fields"""
    assert sample_search_result.papers_count == 1
    assert isinstance(sample_search_result.id, UUID)


@pytest.mark.asyncio
async def test_client_context_manager(mock_arxiv_client):
    """Test client context manager"""
    async with mock_arxiv_client as c:
        assert isinstance(c, ArxivClient)

    mock_arxiv_client._session_manager.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_by_query_single_page(
    mock_arxiv_client, sample_search_result, mocker
):
    """Test _search_by_query method with single page result"""
    prepare_mock = mocker.patch.object(
        mock_arxiv_client,
        "_prepare_initial_search",
        return_value=(sample_search_result, False),
    )
    batch_mock = mocker.patch.object(
        mock_arxiv_client,
        "_fetch_batch_results",
    )

    result = await mock_arxiv_client._search_by_query(query="test")

    assert result == sample_search_result
    prepare_mock.assert_called_once_with(
        query="test",
        start=None,
        max_results=None,
        sort_by=None,
        sort_order=None,
    )
    batch_mock.assert_not_called()


@pytest.mark.asyncio
async def test_search_by_ids(mock_arxiv_client, sample_search_result, mocker):
    """Test _search_by_ids method"""
    prepare_mock = mocker.patch.object(
        mock_arxiv_client,
        "_prepare_initial_search",
        return_value=(sample_search_result, False),
    )

    id_list = ["1234.5678", "8765.4321"]
    result = await mock_arxiv_client._search_by_ids(id_list=id_list, start=0)

    assert result == sample_search_result
    prepare_mock.assert_called_once_with(
        id_list=id_list,
        start=0,
    )


@pytest.mark.asyncio
async def test_search_by_ids_with_invalid_id(mock_arxiv_client, mocker):
    """Test _search_by_ids method with invalid ID"""
    mocker.patch.object(
        mock_arxiv_client,
        "_prepare_initial_search",
        side_effect=QueryBuildError("Invalid arXiv ID format"),
    )

    with pytest.raises(QueryBuildError):
        await mock_arxiv_client._search_by_ids(id_list=["invalid-id"])


@pytest.mark.asyncio
async def test_search_by_query_multi_page(
    mock_arxiv_client, sample_search_result, mocker
):
    """Test _search_by_query method with multi-page results"""
    modified_result = sample_search_result.model_copy(
        update={
            "total_result": 150,
            "papers": [sample_search_result.papers[0]] * 50,
        }
    )

    prepare_mock = mocker.patch.object(
        mock_arxiv_client,
        "_prepare_initial_search",
        return_value=(modified_result, True),
    )
    batch_mock = mocker.patch.object(
        mock_arxiv_client,
        "_fetch_batch_results",
        return_value=[sample_search_result],
    )
    aggregate_mock = mocker.patch.object(
        mock_arxiv_client,
        "aggregate_search_results",
        return_value=sample_search_result,
    )

    await mock_arxiv_client._search_by_query(
        query="test query",
        max_results=100,
        sort_by=SortCriterion.SUBMITTED,
        sort_order=SortOrder.ASCENDING,
        start=0,
    )

    prepare_mock.assert_called_once_with(
        query="test query",
        start=0,
        max_results=100,
        sort_by=SortCriterion.SUBMITTED,
        sort_order=SortOrder.ASCENDING,
    )
    batch_mock.assert_called_once()
    aggregate_mock.assert_called_once()


@pytest.mark.asyncio
async def test_aggregate_search_results(mock_arxiv_client, mock_config):
    """Test aggregating multiple search results"""
    # Create sample papers with different IDs
    paper1 = Paper(
        info=BasicInfo.model_validate(
            {
                "id": "2101.00001",
                "title": "Paper 1",
                "summary": "Summary 1",
                "authors": [{"name": "Author 1"}],
                "categories": {"primary": {"term": "cs.AI"}, "secondary": []},
                "published": datetime.now(tz=ZoneInfo(mock_config.timezone)),
                "updated": datetime.now(tz=ZoneInfo(mock_config.timezone)),
            }
        ),
        doi=None,
        journal_ref=None,
        pdf_url=None,
        comment=None,
    )
    paper2 = Paper(
        info=BasicInfo.model_validate(
            {
                "id": "2101.00002",
                "title": "Paper 2",
                "summary": "Summary 2",
                "authors": [{"name": "Author 2"}],
                "categories": {"primary": {"term": "cs.AI"}, "secondary": []},
                "published": datetime.now(tz=ZoneInfo(mock_config.timezone)),
                "updated": datetime.now(tz=ZoneInfo(mock_config.timezone)),
            }
        ),
        doi=None,
        journal_ref=None,
        pdf_url=None,
        comment=None,
    )

    # Create two search results with different metadata
    metadata1 = Metadata(
        start_time=datetime(2024, 1, 1, tzinfo=ZoneInfo(mock_config.timezone)),
        end_time=datetime(2024, 1, 2, tzinfo=ZoneInfo(mock_config.timezone)),
        missing_results=1,
        pagesize=10,
        source=URL("http://test1.com"),
    )
    metadata2 = Metadata(
        start_time=datetime(2024, 1, 2, tzinfo=ZoneInfo(mock_config.timezone)),
        end_time=datetime(2024, 1, 3, tzinfo=ZoneInfo(mock_config.timezone)),
        missing_results=2,
        pagesize=20,
        source=URL("http://test2.com"),
    )

    # Create search results
    result1 = SearchResult(
        papers=[paper1],
        total_result=1,
        page=1,
        has_next=True,
        query_params=SearchParams(
            query="test",
            start=0,
            max_results=10,
            sort_by=None,
            sort_order=None,
            id_list=None,
        ),
        metadata=metadata1,
    )
    result2 = SearchResult(
        papers=[paper2],
        total_result=2,
        page=2,
        has_next=False,
        query_params=SearchParams(
            query="test",
            start=10,
            max_results=10,
            sort_by=None,
            sort_order=None,
            id_list=None,
        ),
        metadata=metadata2,
    )

    # Aggregate results
    aggregated = mock_arxiv_client.aggregate_search_results([result1, result2])

    # Verify aggregated result
    assert len(aggregated.papers) == 2
    assert aggregated.total_result == 2
    assert aggregated.page == 2
    assert aggregated.has_next is True
    assert aggregated.metadata.start_time == metadata1.start_time
    assert aggregated.metadata.end_time == metadata2.end_time
    assert aggregated.metadata.missing_results == 3
    assert aggregated.metadata.pagesize == 30
    assert aggregated.metadata.source == metadata1.source
    assert aggregated.query_params.start == 0
    assert aggregated.query_params.max_results == 2


@pytest.mark.asyncio
async def test_aggregate_search_results_empty_list(mock_arxiv_client):
    """Test aggregating empty results list raises ValueError"""
    with pytest.raises(ValueError, match="Results list cannot be empty"):
        mock_arxiv_client.aggregate_search_results([])


@pytest.mark.asyncio
async def test_prepare_initial_search_query(
    mock_arxiv_client, sample_search_result, mocker
):
    """Test preparing initial search with query"""
    fetch_mock = mocker.patch.object(
        mock_arxiv_client, "_fetch_page", return_value=mocker.AsyncMock()
    )
    mocker.patch(
        "aioarxiv.client.arxiv_client.ArxivParser",
        return_value=mocker.Mock(build_search_result=lambda _: sample_search_result),
    )

    # Test query search with max_results less than page_size
    result, needs_more = await mock_arxiv_client._prepare_initial_search(
        query="test query",
        max_results=5,
        sort_by=SortCriterion.SUBMITTED,
        sort_order=SortOrder.ASCENDING,
    )

    assert isinstance(result, SearchResult)
    assert needs_more is False
    fetch_mock.assert_called_once()
    assert fetch_mock.call_args.args[0] == SearchParams(
        query="test query",
        start=None,
        max_results=5,
        sort_by=SortCriterion.SUBMITTED,
        sort_order=SortOrder.ASCENDING,
        id_list=None,
    )


@pytest.mark.asyncio
async def test_prepare_initial_search_id_list(
    mock_arxiv_client, sample_search_result, mocker
):
    """Test preparing initial search with ID list"""
    fetch_mock = mocker.patch.object(
        mock_arxiv_client, "_fetch_page", return_value=mocker.AsyncMock()
    )
    mocker.patch(
        "aioarxiv.client.arxiv_client.ArxivParser",
        return_value=mocker.Mock(build_search_result=lambda _: sample_search_result),
    )

    id_list = ["2101.00123", "2101.00124"]
    result, needs_more = await mock_arxiv_client._prepare_initial_search(
        id_list=id_list,
        start=0,
    )

    assert isinstance(result, SearchResult)
    assert needs_more is False  # ID list searches never need more results
    fetch_mock.assert_called_once()
    assert fetch_mock.call_args.args[0] == SearchParams(
        query=None,
        start=0,
        max_results=mock_arxiv_client._config.page_size,
        sort_by=None,
        sort_order=None,
        id_list=id_list,
    )


@pytest.mark.asyncio
async def test_prepare_initial_search_needs_more(
    mock_arxiv_client, sample_search_result, mocker
):
    """Test preparing initial search that requires more results"""
    # Modify sample result to have more total results
    modified_result = sample_search_result.model_copy(
        update={"total_result": 100, "papers": [sample_search_result.papers[0]] * 50}
    )

    fetch_mock = mocker.patch.object(
        mock_arxiv_client, "_fetch_page", return_value=mocker.AsyncMock()
    )
    mocker.patch(
        "aioarxiv.client.arxiv_client.ArxivParser",
        return_value=mocker.Mock(build_search_result=lambda _: modified_result),
    )

    result, needs_more = await mock_arxiv_client._prepare_initial_search(
        query="test query",
        max_results=75,  # More than initial page size but less than total
    )

    assert isinstance(result, SearchResult)
    assert needs_more is True
    fetch_mock.assert_called_once()
    assert result.total_result == 100
