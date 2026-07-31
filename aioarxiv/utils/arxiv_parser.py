from datetime import datetime, timezone
from typing import ClassVar, cast
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from aiohttp import ClientResponse
from defusedxml import ElementTree as DefusedET
from pydantic import AnyUrl, HttpUrl

from aioarxiv.exception import ParserException, QueryBuildError
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

from . import create_parser_exception
from .log import ConfigManager, logger

ERROR_ENTRY_ID_PREFIX = "http://arxiv.org/api/errors"


class ArxivParser:
    """Parser for arXiv API Atom responses.

    Attributes:
        NS (ClassVar[dict[str, str]]): XML namespace mapping.

    Args:
        response_context: Raw API response body.
        raw_response: The originating HTTP response.

    Raises:
        ParserException: If the response is not well-formed XML.
    """

    NS: ClassVar[dict[str, str]] = {
        "atom": "http://www.w3.org/2005/Atom",
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
        "arxiv": "http://arxiv.org/schemas/atom",
    }

    def __init__(self, response_context: str, raw_response: ClientResponse) -> None:
        self.response_context = response_context
        self.raw_response = raw_response
        try:
            self.root: ET.Element = DefusedET.fromstring(response_context)
        except ET.ParseError as e:
            raise ParserException(
                url=str(raw_response.url),
                message="Failed to parse response as XML",
                original_error=e,
            ) from e

    @staticmethod
    def build_paper(
        data: ET.Element,
    ) -> Paper:
        """Build a Paper model from a single Atom entry."""
        parser = PaperParser(data)
        basic_info = parser.parse_basics_info()
        return Paper(
            info=basic_info,
            pdf_url=parser.parse_pdf_url(),
            **parser.parse_optional_fields(),
        )

    def _raise_if_error_entry(self) -> None:
        """Detect the arXiv API error signalling convention.

        The API reports parameter errors as HTTP 200 with a single entry whose
        ``<id>`` starts with ``http://arxiv.org/api/errors``; the ``<summary>``
        carries the error message. A legitimate empty feed (``totalResults=0``,
        no entries) is not an error.

        Raises:
            QueryBuildError: If the feed is an API error entry.
        """
        entries = self.root.findall("atom:entry", ArxivParser.NS)
        if len(entries) != 1:
            return

        entry_id = entries[0].findtext("atom:id", default="", namespaces=ArxivParser.NS)
        if not entry_id.startswith(ERROR_ENTRY_ID_PREFIX):
            return

        summary = entries[0].findtext(
            "atom:summary", default="", namespaces=ArxivParser.NS
        )
        raise QueryBuildError(
            f"arXiv API rejected the query: {summary.strip() or 'unknown error'}"
        )

    def parse_feed(self) -> list[Paper]:
        """Parse all entries of the Atom feed into papers.

        Returns:
            list[Paper]: Parsed papers (empty for an empty feed).

        Raises:
            QueryBuildError: If the feed is an API error entry.
            ParserException: If an entry cannot be parsed.
        """
        self._raise_if_error_entry()
        entries = self.root.findall("atom:entry", ArxivParser.NS)
        papers = [self.build_paper(entry) for entry in entries]
        logger.trace(f"Parsed {len(papers)} papers")
        return papers

    def parse_total_result(self) -> int:
        """Parse the total result count from the feed.

        Returns:
            int: Total number of matching results.

        Raises:
            ParserException: If the element is missing or not an integer.
        """
        total_element = self.root.find("opensearch:totalResults", ArxivParser.NS)
        if total_element is None or total_element.text is None:
            raise create_parser_exception(
                self.root,
                str(self.raw_response.url),
                message="Missing total results element",
            )

        try:
            return int(total_element.text)
        except ValueError as e:
            raise create_parser_exception(
                self.root,
                str(self.raw_response.url),
                message=f"Invalid total results value: {total_element.text!r}",
                error=e,
            ) from e

    def build_search_result(self, query_params: SearchParams) -> SearchResult:
        """Build a SearchResult from the parsed feed.

        Args:
            query_params: The search parameters used for the request.

        Returns:
            SearchResult: Result with papers and base metadata; pagination
            fields are finalized by the client.
        """
        return SearchResult(
            papers=self.parse_feed(),
            total_result=self.parse_total_result(),
            page=1,
            has_next=False,
            query_params=query_params,
            metadata=Metadata(
                missing_results=0,
                pagesize=0,
                source=str(self.raw_response.url),
                end_time=None,
            ),
        )


class PaperParser:
    """Parser for a single Atom entry element."""

    def __init__(self, entry: ET.Element) -> None:
        self.entry = entry

    def parse_authors(self) -> list[Author]:
        """Parse author elements.

        Returns:
            list[Author]: Authors with optional affiliations.

        Raises:
            ParserException: If no author is present.
        """

        def get_text(element: ET.Element, tag: str, namespace: dict) -> str | None:
            sub_elem = element.find(tag, namespace)
            return sub_elem.text if sub_elem is not None else None

        authors = []
        for author_elem in self.entry.findall("atom:author", ArxivParser.NS):
            name = get_text(author_elem, "atom:name", ArxivParser.NS)
            affiliation = get_text(author_elem, "arxiv:affiliation", ArxivParser.NS)

            if name:
                authors.append(Author(name=name, affiliation=affiliation))

        if not authors:
            raise create_parser_exception(
                self.entry,
                "",
                message="Missing author information",
            )

        logger.trace(f"Authors: {authors}")
        return authors

    def parse_categories(self) -> Category:
        """Parse primary and secondary categories.

        Secondary categories are all ``<category>`` terms minus the primary
        term.

        Returns:
            Category: Parsed category information.

        Raises:
            ParserException: If the primary category is missing.
        """

        def parse_primary() -> PrimaryCategory:
            primary_elem = self.entry.find("arxiv:primary_category", ArxivParser.NS)
            if primary_elem is None:
                raise create_parser_exception(
                    self.entry, "", message="Missing primary category"
                )
            return PrimaryCategory(
                term=primary_elem.get("term", ""),
                scheme=cast("AnyUrl", primary_elem.attrib.get("scheme")),
                label=primary_elem.get("label"),
            )

        def parse_secondary(primary_term: str) -> list[str]:
            return [
                term
                for cat in self.entry.findall("atom:category", ArxivParser.NS)
                if (term := cat.get("term")) and term != primary_term
            ]

        primary = parse_primary()
        secondary = parse_secondary(primary.term)

        return Category(primary=primary, secondary=secondary)

    def parse_basics_info(self) -> BasicInfo:
        """Parse the mandatory entry fields.

        Returns:
            BasicInfo: Basic paper information.

        Raises:
            ParserException: If a mandatory element is missing.
        """

        def get_or_raise(element: ET.Element, tag: str) -> str:
            sub_elem = element.find(f"atom:{tag}", ArxivParser.NS)
            if sub_elem is None or sub_elem.text is None:
                raise create_parser_exception(
                    element,
                    "",
                    message=f"Missing {tag} element",
                )
            return sub_elem.text

        return BasicInfo(
            id=self._extract_arxiv_id(get_or_raise(self.entry, "id")),
            title=get_or_raise(self.entry, "title"),
            summary=get_or_raise(self.entry, "summary"),
            authors=self.parse_authors(),
            categories=self.parse_categories(),
            published=self.parse_datetime(get_or_raise(self.entry, "published")),
            updated=self.parse_datetime(get_or_raise(self.entry, "updated")),
        )

    @staticmethod
    def _extract_arxiv_id(abs_url: str) -> str:
        """Extract the arXiv id from an abs page URL.

        Strips the scheme, host and ``/abs/`` prefix so old-style ids that
        contain a slash (e.g. ``cond-mat/0102536v1``) survive intact.

        Args:
            abs_url: The entry ``<id>`` value, e.g.
                ``http://arxiv.org/abs/cond-mat/0102536v1``.

        Returns:
            str: The arXiv id, e.g. ``cond-mat/0102536v1``.
        """
        _, sep, arxiv_id = abs_url.partition("/abs/")
        return arxiv_id if sep else abs_url

    def parse_pdf_url(self) -> HttpUrl | None:
        """Parse the PDF link.

        Links are matched by ``(rel == "related", title == "pdf")`` per the
        API spec, with ``type == "application/pdf"`` as a fallback.

        Returns:
            Optional[HttpUrl]: The PDF URL, or None if absent.
        """
        links = self.entry.findall("atom:link", ArxivParser.NS)
        if not links:
            logger.warning("No links found in entry")
            return None

        pdf_url = next(
            (
                link.attrib["href"]
                for link in links
                if link.get("rel") == "related"
                and link.get("title") == "pdf"
                and "href" in link.attrib
            ),
            None,
        )
        if pdf_url is None:
            pdf_url = next(
                (
                    link.attrib["href"]
                    for link in links
                    if link.get("type") == "application/pdf" and "href" in link.attrib
                ),
                None,
            )

        if pdf_url is None:
            logger.warning("No PDF link found in entry")
            return None

        return cast("HttpUrl", pdf_url)

    def parse_optional_fields(self) -> dict[str, str | None]:
        """Parse the optional arXiv extension fields.

        Returns:
            dict: Mapping with ``comment``, ``journal_ref`` and ``doi``.
        """
        fields = {
            "comment": self.entry.find("arxiv:comment", ArxivParser.NS),
            "journal_ref": self.entry.find("arxiv:journal_ref", ArxivParser.NS),
            "doi": self.entry.find("arxiv:doi", ArxivParser.NS),
        }

        return {k: v.text if v is not None else None for k, v in fields.items()}

    @staticmethod
    def parse_datetime(date_str: str) -> datetime:
        """Parse an ISO datetime string and convert to the configured timezone.

        The API emits UTC instants (``Z`` suffix); the instant is preserved
        and converted via ``astimezone`` instead of relabeling the tzinfo.

        Args:
            date_str: ISO format datetime string.

        Returns:
            datetime: Datetime in the configured timezone.

        Raises:
            ValueError: If the datetime format is invalid.
        """
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError as e:
            msg = f"Invalid datetime format: {date_str}"
            raise ValueError(msg) from e

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(ConfigManager.get_config().timezone))
