from datetime import datetime

import pytest
from pydantic import HttpUrl, ValidationError
from aioarxiv.models import Paper, Metadata, SearchParams, SearchResult


@pytest.fixture
def paper_base_info():
    return {
        "id": "1234.5678",
        "title": "Test",
        "summary": "Test",
        "authors": [{"name": "Test"}],
        "categories": {"primary": {"term": "cs.AI"}, "secondary": []},
        "published": datetime.now(),
        "updated": datetime.now(),
    }


@pytest.mark.parametrize(
    "doi", ["10.1234/test.123", "10.12345/test-123", "10.1234/test_123"]
)
def test_valid_doi(paper_base_info, doi):
    """测试有效的DOI格式"""
    paper = Paper(
        info=paper_base_info, doi=doi, journal_ref=None, pdf_url=None, comment=None
    )
    assert paper.doi == doi


@pytest.mark.parametrize(
    "invalid_doi",
    [
        "11.1234/test.123",  # Not starting with 10
        "10.123/test.123",  # Too few digits
        "test.123",  # Invalid format
    ],
)
def test_invalid_doi(paper_base_info, invalid_doi):
    """Test paper model with invalid DOI"""
    with pytest.raises(ValidationError):
        Paper(
            info=paper_base_info,
            doi=invalid_doi,
            journal_ref=None,
            pdf_url=None,
            comment=None,
        )


@pytest.mark.parametrize(
    ("start", "end", "expected_seconds", "expected_ms"),
    [
        (datetime(2024, 1, 1, 12, 0, 0), datetime(2024, 1, 1, 12, 0, 1), 1.0, 1000.0),
        (
            datetime(2024, 1, 1, 12, 0, 0),
            datetime(2024, 1, 1, 12, 0, 0, 500000),
            0.5,
            500.0,
        ),
    ],
)
def test_metadata_duration(start, end, expected_seconds, expected_ms):
    """测试元数据持续时间计算"""
    metadata = Metadata(
        start_time=start, end_time=end, missing_results=0, pagesize=20, source="test"
    )
    assert metadata.duration_seconds == expected_seconds
    assert metadata.duration_ms == expected_ms


@pytest.mark.parametrize("papers_count", [0, 1, 5])
def test_search_result_papers_count(papers_count, paper_base_info):
    """测试搜索结果论文数量计算"""
    papers = [
        Paper(
            info=paper_base_info,
            doi=None,
            journal_ref=None,
            pdf_url=None,
            comment=None,
        )
        for _ in range(papers_count)
    ]
    result = SearchResult(
        papers=papers,
        total_result=100,
        page=1,
        has_next=True,
        query_params=SearchParams(
            query="test",
            id_list=None,
            start=0,
            max_results=None,
            sort_by=None,
            sort_order=None,
        ),
        metadata=Metadata(missing_results=0, pagesize=20, source="test"),
    )
    assert result.papers_count == papers_count


@pytest.mark.parametrize(
    ("doi", "journal_ref", "pdf_url", "comment"),
    [
        ("10.1234/test.123", "Journal Ref", "https://example.com/pdf", "Test comment"),
        ("10.12345/test-123", None, None, None),
    ],
)
def test_paper_optional_fields(paper_base_info, doi, journal_ref, pdf_url, comment):
    """Test paper model with optional fields"""
    paper = Paper(
        info=paper_base_info,
        doi=doi,
        journal_ref=journal_ref,
        pdf_url=pdf_url,
        comment=comment,
    )
    assert paper.doi == doi
    assert paper.journal_ref == journal_ref
    if pdf_url is not None:
        assert paper.pdf_url == HttpUrl(pdf_url)
    else:
        assert paper.pdf_url is None
    assert paper.comment == comment
