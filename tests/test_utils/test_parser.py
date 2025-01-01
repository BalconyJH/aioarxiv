from datetime import datetime
import pathlib
from typing import cast
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from aiohttp import ClientResponse
from pydantic import HttpUrl
import pytest
from yarl import URL

from aioarxiv.exception import ParserException
from aioarxiv.models import Category, Paper, SearchParams
from aioarxiv.utils.parser import ArxivParser, PaperParser, RootParser

SAMPLE_XML_PATH = pathlib.Path(__file__).parent.parent / "data" / "sample.xml"


@pytest.fixture
def sample_xml():
    return SAMPLE_XML_PATH.read_text(encoding="utf-8")


@pytest.fixture
def mock_response(mocker, sample_xml):
    response = mocker.AsyncMock(spec=ClientResponse)
    response.url = URL("http://test.com")
    response.text = mocker.AsyncMock(return_value=sample_xml)
    return response


@pytest.fixture
def paper_entry(sample_xml):
    root = ET.fromstring(sample_xml)
    return root.find("{http://www.w3.org/2005/Atom}entry")


def test_paper_parser_init(paper_entry):
    parser = PaperParser(paper_entry)
    assert parser.entry == paper_entry


def test_parse_authors(paper_entry):
    parser = PaperParser(paper_entry)
    authors = parser.parse_authors()
    assert len(authors) == 5
    assert authors[0].name == "David Prendergast"
    assert authors[0].affiliation == "Department of Physics"


def test_parse_categories(paper_entry):
    parser = PaperParser(paper_entry)
    categories = parser.parse_categories()
    assert isinstance(categories, Category)
    assert categories.primary.term == "cond-mat.str-el"
    assert categories.primary.label is None
    assert len(categories.secondary) == 0


def test_parse_basic_info(paper_entry):
    parser = PaperParser(paper_entry)
    info = parser.parse_basics_info()
    assert info.id == "0102536v1"
    assert (
        info.title
        == "Impact of Electron-Electron Cusp on Configuration Interaction Energies"
    )
    assert (
        info.summary
        == """  The effect of the electron-electron cusp on the convergence of configuration
            interaction (CI) wave functions is examined. By analogy with the
            pseudopotential approach for electron-ion interactions, an effective
            electron-electron interaction is developed which closely reproduces the
            scattering of the Coulomb interaction but is smooth and finite at zero
            electron-electron separation. The exact many-electron wave function for this
            smooth effective interaction has no cusp at zero electron-electron separation.
            We perform CI and quantum Monte Carlo calculations for He and Be atoms, both
            with the Coulomb electron-electron interaction and with the smooth effective
            electron-electron interaction. We find that convergence of the CI expansion of
            the wave function for the smooth electron-electron interaction is not
            significantly improved compared with that for the divergent Coulomb interaction
            for energy differences on the order of 1 mHartree. This shows that, contrary to
            popular belief, description of the electron-electron cusp is not a limiting
            factor, to within chemical accuracy, for CI calculations.
        """  # noqa: E501
    )
    assert len(info.authors) == 5
    assert isinstance(info.categories, Category)
    assert isinstance(info.published, datetime)
    assert isinstance(info.updated, datetime)


def test_parse_pdf_url(paper_entry):
    parser = PaperParser(paper_entry)
    url = parser.parse_pdf_url()
    assert url == cast(HttpUrl, "http://arxiv.org/pdf/cond-mat/0102536v1")


def test_parse_optional_fields(paper_entry):
    parser = PaperParser(paper_entry)
    fields = parser.parse_optional_fields()
    assert fields["doi"] == "10.1063/1.1383585"
    assert fields["comment"] == (
        """11 pages, 6 figures, 3 tables, LaTeX209, submitted to The Journal of
            Chemical Physics"""
    )
    assert fields["journal_ref"] == "J. Chem. Phys. 115, 1626 (2001)"


def test_parse_datetime():
    parser = PaperParser(ET.Element("entry"))
    dt = parser.parse_datetime("2024-03-18T00:00:00Z")
    assert isinstance(dt, datetime)
    assert dt.tzinfo == ZoneInfo("Asia/Shanghai")


def test_root_parser_total_result(sample_xml):
    root = RootParser(sample_xml, URL("http://test.com"))
    assert root.parse_total_result() == 218712


def test_root_parser_build_search_result(sample_xml):
    root = RootParser(sample_xml, URL("http://test.com"))
    params = SearchParams(query="test")  # pyright: ignore [reportCallIssue]
    result = root.build_search_result(params)
    assert result.total_result == 218712
    assert result.page == 1
    assert result.query_params == params


def test_arxiv_parser_build_paper(paper_entry):
    paper = ArxivParser.build_paper(paper_entry)
    assert isinstance(paper, Paper)
    assert paper.info.id == "0102536v1"
    assert str(paper.pdf_url) == "http://arxiv.org/pdf/cond-mat/0102536v1"


@pytest.mark.asyncio
async def test_arxiv_parser_parse_feed(mock_response, sample_xml):
    parser = ArxivParser(sample_xml, mock_response)
    papers = parser.parse_feed()
    assert len(papers) == 1
    assert isinstance(papers[0], Paper)


def test_error_handling_missing_author(paper_entry):
    # Remove all authors
    for author in paper_entry.findall("{http://www.w3.org/2005/Atom}author"):
        paper_entry.remove(author)

    parser = PaperParser(paper_entry)
    with pytest.raises(ParserException):
        parser.parse_authors()


def test_error_handling_invalid_date():
    parser = PaperParser(ET.Element("entry"))
    with pytest.raises(ValueError, match=r"日期格式: .* 不符合预期"):
        parser.parse_datetime("invalid-date")


def test_error_handling_missing_pdf_url(paper_entry):
    # Remove PDF link
    for link in paper_entry.findall("{http://www.w3.org/2005/Atom}link"):
        paper_entry.remove(link)

    parser = PaperParser(paper_entry)
    assert parser.parse_pdf_url() is None
