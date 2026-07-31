from datetime import datetime, timezone
import pathlib
from typing import TYPE_CHECKING, cast
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from aiohttp import ClientResponse
import pytest
from yarl import URL

from aioarxiv.config import default_config
from aioarxiv.exception import ParserException, QueryBuildError
from aioarxiv.models import Category, Paper, SearchParams
from aioarxiv.utils.arxiv_parser import ArxivParser, PaperParser

if TYPE_CHECKING:
    from pydantic import HttpUrl

DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
SAMPLE_XML_PATH = DATA_DIR / "sample.xml"
ERROR_XML_PATH = DATA_DIR / "error_response.xml"
MULTI_CATEGORY_XML_PATH = DATA_DIR / "multi_category.xml"

ATOM_NS = "{http://www.w3.org/2005/Atom}"

EMPTY_FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <title type="html">ArXiv Query: search_query=all:nothing</title>
    <id>http://arxiv.org/api/empty</id>
    <updated>2024-01-01T00:00:00-05:00</updated>
    <opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">0</opensearch:totalResults>
    <opensearch:startIndex xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">0</opensearch:startIndex>
    <opensearch:itemsPerPage xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">10</opensearch:itemsPerPage>
</feed>
"""


@pytest.fixture
def sample_xml():
    return SAMPLE_XML_PATH.read_text(encoding="utf-8")


@pytest.fixture
def error_xml():
    return ERROR_XML_PATH.read_text(encoding="utf-8")


@pytest.fixture
def multi_category_xml():
    return MULTI_CATEGORY_XML_PATH.read_text(encoding="utf-8")


@pytest.fixture
def mock_response(mocker):
    response = mocker.AsyncMock(spec=ClientResponse)
    response.url = URL("http://test.com")
    return response


@pytest.fixture
def paper_entry(sample_xml):
    root = ET.fromstring(sample_xml)  # noqa: S314
    return root.find(f"{ATOM_NS}entry")


@pytest.fixture
def multi_category_entry(multi_category_xml):
    root = ET.fromstring(multi_category_xml)  # noqa: S314
    return root.find(f"{ATOM_NS}entry")


def test_paper_parser_init(paper_entry):
    parser = PaperParser(paper_entry)
    assert parser.entry == paper_entry


def test_parse_authors(paper_entry):
    parser = PaperParser(paper_entry)
    authors = parser.parse_authors()
    assert len(authors) == 5
    assert authors[0].name == "David Prendergast"
    assert authors[0].affiliation == "Department of Physics"


def test_parse_categories_single(paper_entry):
    parser = PaperParser(paper_entry)
    categories = parser.parse_categories()
    assert isinstance(categories, Category)
    assert categories.primary.term == "cond-mat.str-el"
    assert categories.primary.label is None
    # The only <category> term equals the primary term, so no secondaries.
    assert categories.secondary == []


def test_parse_categories_multiple(multi_category_entry):
    parser = PaperParser(multi_category_entry)
    categories = parser.parse_categories()
    assert categories.primary.term == "cs.AI"
    assert categories.secondary == ["cs.LG", "stat.ML"]


def test_parse_basic_info_preserves_old_style_id(paper_entry):
    parser = PaperParser(paper_entry)
    info = parser.parse_basics_info()
    # Old-style ids contain a slash and must survive intact.
    assert info.id == "cond-mat/0102536v1"
    assert (
        info.title
        == "Impact of Electron-Electron Cusp on Configuration Interaction Energies"
    )
    assert len(info.authors) == 5
    assert isinstance(info.categories, Category)
    assert isinstance(info.published, datetime)
    assert isinstance(info.updated, datetime)


def test_parse_new_style_id(multi_category_entry):
    parser = PaperParser(multi_category_entry)
    info = parser.parse_basics_info()
    assert info.id == "2101.00001v2"


def test_parse_pdf_url(paper_entry):
    parser = PaperParser(paper_entry)
    url = parser.parse_pdf_url()
    assert url == cast("HttpUrl", "http://arxiv.org/pdf/cond-mat/0102536v1")


def test_parse_pdf_url_by_rel_and_title_without_type(paper_entry):
    # Per spec the pdf link is identified by (rel="related", title="pdf");
    # the type attribute is optional.
    for link in paper_entry.findall(f"{ATOM_NS}link"):
        if link.get("title") == "pdf":
            del link.attrib["type"]

    parser = PaperParser(paper_entry)
    url = parser.parse_pdf_url()
    assert url == cast("HttpUrl", "http://arxiv.org/pdf/cond-mat/0102536v1")


def test_parse_pdf_url_fallback_to_mime_type(paper_entry):
    # Fallback: no title="pdf", but a link carries type="application/pdf".
    for link in paper_entry.findall(f"{ATOM_NS}link"):
        if link.get("title") == "pdf":
            del link.attrib["title"]

    parser = PaperParser(paper_entry)
    url = parser.parse_pdf_url()
    assert url == cast("HttpUrl", "http://arxiv.org/pdf/cond-mat/0102536v1")


def test_parse_optional_fields(paper_entry):
    parser = PaperParser(paper_entry)
    fields = parser.parse_optional_fields()
    assert fields["doi"] == "10.1063/1.1383585"
    assert fields["comment"] == (
        """11 pages, 6 figures, 3 tables, LaTeX209, submitted to The Journal of
            Chemical Physics"""
    )
    assert fields["journal_ref"] == "J. Chem. Phys. 115, 1626 (2001)"


def test_parse_datetime_preserves_instant():
    parser = PaperParser(ET.Element("entry"))
    dt = parser.parse_datetime("2024-03-18T00:00:00Z")
    assert dt.tzinfo == ZoneInfo(default_config.timezone)
    # The instant must not shift: converting back to UTC yields the source.
    assert dt == datetime(2024, 3, 18, tzinfo=timezone.utc)


def test_arxiv_parser_build_paper(paper_entry):
    paper = ArxivParser.build_paper(paper_entry)
    assert isinstance(paper, Paper)
    assert paper.info.id == "cond-mat/0102536v1"
    assert str(paper.pdf_url) == "http://arxiv.org/pdf/cond-mat/0102536v1"


def test_arxiv_parser_parse_feed(mock_response, sample_xml):
    parser = ArxivParser(sample_xml, mock_response)
    papers = parser.parse_feed()
    assert len(papers) == 1
    assert isinstance(papers[0], Paper)


def test_parse_feed_raises_on_error_entry(mock_response, error_xml):
    parser = ArxivParser(error_xml, mock_response)
    with pytest.raises(QueryBuildError, match=r"incorrect id format for 1234\.12345"):
        parser.parse_feed()


def test_parse_feed_empty_result_is_not_error(mock_response):
    parser = ArxivParser(EMPTY_FEED_XML, mock_response)
    assert parser.parse_feed() == []
    assert parser.parse_total_result() == 0


def test_parse_total_result_invalid_value(mock_response):
    invalid_xml = EMPTY_FEED_XML.replace(
        ">0</opensearch:totalResults>", ">not-a-number</opensearch:totalResults>"
    )
    parser = ArxivParser(invalid_xml, mock_response)
    with pytest.raises(ParserException):
        parser.parse_total_result()


def test_parse_total_result_missing_element(mock_response):
    root = ET.fromstring(EMPTY_FEED_XML)  # noqa: S314
    total_element = root.find("opensearch:totalResults", ArxivParser.NS)
    assert total_element is not None
    root.remove(total_element)
    parser = ArxivParser(ET.tostring(root, encoding="unicode"), mock_response)

    with pytest.raises(ParserException, match="Missing total results element"):
        parser.parse_total_result()


def test_build_search_result_uses_feed_metadata(mock_response):
    parser = ArxivParser(EMPTY_FEED_XML, mock_response)
    params = SearchParams(query="all:nothing", max_results=10)

    result = parser.build_search_result(params)

    assert result.papers == []
    assert result.total_result == 0
    assert result.page == 1
    assert result.has_next is False
    assert result.query_params == params
    assert result.metadata.missing_results == 0
    assert result.metadata.pagesize == 0
    assert result.metadata.source == "http://test.com"
    assert result.metadata.end_time is None


def test_parser_rejects_malformed_xml(mock_response):
    with pytest.raises(ParserException):
        ArxivParser("<feed>not closed", mock_response)


def test_error_handling_missing_author(paper_entry):
    for author in paper_entry.findall(f"{ATOM_NS}author"):
        paper_entry.remove(author)

    parser = PaperParser(paper_entry)
    with pytest.raises(ParserException):
        parser.parse_authors()


def test_error_handling_missing_primary_category(paper_entry):
    primary_category = paper_entry.find("arxiv:primary_category", ArxivParser.NS)
    assert primary_category is not None
    paper_entry.remove(primary_category)

    parser = PaperParser(paper_entry)
    with pytest.raises(ParserException, match="Missing primary category"):
        parser.parse_categories()


@pytest.mark.parametrize("tag", ["id", "title", "summary", "published", "updated"])
def test_error_handling_missing_basic_element(paper_entry, tag):
    element = paper_entry.find(f"atom:{tag}", ArxivParser.NS)
    assert element is not None
    paper_entry.remove(element)

    parser = PaperParser(paper_entry)
    with pytest.raises(ParserException, match=f"Missing {tag} element"):
        parser.parse_basics_info()


def test_error_handling_invalid_date():
    parser = PaperParser(ET.Element("entry"))
    with pytest.raises(ValueError, match="Invalid datetime format"):
        parser.parse_datetime("invalid-date")


def test_error_handling_missing_pdf_url(paper_entry):
    for link in paper_entry.findall(f"{ATOM_NS}link"):
        paper_entry.remove(link)

    parser = PaperParser(paper_entry)
    assert parser.parse_pdf_url() is None


def test_parse_pdf_url_returns_none_without_pdf_link(paper_entry):
    for link in paper_entry.findall(f"{ATOM_NS}link"):
        if link.get("title") == "pdf":
            paper_entry.remove(link)

    parser = PaperParser(paper_entry)
    assert paper_entry.findall(f"{ATOM_NS}link")
    assert parser.parse_pdf_url() is None


def test_parse_datetime_assumes_utc_for_naive_value():
    parser = PaperParser(ET.Element("entry"))

    parsed = parser.parse_datetime("2024-03-18T00:00:00")

    assert parsed.tzinfo == ZoneInfo(default_config.timezone)
    assert parsed == datetime(2024, 3, 18, tzinfo=timezone.utc)
