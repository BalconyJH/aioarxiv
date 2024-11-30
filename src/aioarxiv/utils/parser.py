from datetime import datetime
import xml.etree.ElementTree as ET
from typing import ClassVar, Optional, cast

from aiohttp import ClientResponse
from pydantic import AnyUrl, HttpUrl

from .log import logger
from . import create_parser_exception
from ..exception import ParserException
from ..models import (
    Paper,
    Author,
    Category,
    Metadata,
    BasicInfo,
    SearchParams,
    SearchResult,
    PrimaryCategory,
)


class ArxivParser:
    """
    arXiv API响应解析器

    Attributes:
        NS (ClassVar[dict[str, str]]): XML命名空间

    Args:
        response_context: API响应内容

    Raises:
        ParserException: 如果解析失败
    """

    NS: ClassVar[dict[str, str]] = {
        "atom": "http://www.w3.org/2005/Atom",
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
        "arxiv": "http://arxiv.org/schemas/atom",
    }

    def __init__(self, response_context: str, raw_response: ClientResponse):
        self.response_context = response_context
        self.raw_response = raw_response
        self.entry = ET.fromstring(response_context)  # Root element of the XML tree

    @staticmethod
    def build_paper(
        data: ET.Element,
    ) -> Paper:
        """统一处理论文解析"""
        parser = PaperParser(data)
        basic_info = parser.parse_basics_info()
        return Paper(
            info=basic_info,
            pdf_url=parser.parse_pdf_url(),
            **parser.parse_optional_fields(),
        )

    def _parse_root(self) -> list[Paper]:
        """
        解析根元素

        Returns:
            tuple[list[Paper], int]: 论文列表和总结果数
        """
        papers = []
        for i, entry in enumerate(self.entry.findall("atom:entry", ArxivParser.NS)):
            try:
                papers.append(self.build_paper(entry))
            except Exception as e:
                raise create_parser_exception(
                    entry,
                    str(self.raw_response.url),
                    message=f"解析第 {i + 1} 篇论文失败",
                    namespace=ArxivParser.NS["atom"],
                    error=e,
                ) from e

        return papers

    def parse_feed(self) -> list[Paper]:
        """
        解析arXiv API的Atom feed内容

        Returns:
            tuple[list[Paper], int]: 论文列表和总结果数
        """
        try:
            return self._parse_root()
        except ET.ParseError as e:
            raise create_parser_exception(
                self.entry,
                str(self.raw_response.url),
                message="解析失败",
                error=e,
            ) from e
        except ParserException:
            raise


class RootParser:
    def __init__(self, response_context: str):
        self.response_context = response_context
        self.entry = ET.fromstring(response_context)

    def parse_total_result(self) -> int:
        """
        解析总结果数

        Returns:
            int: 总结果数

        Raises:
            ParserException: 如果解析失败
        """
        total_element = self.entry.find("opensearch:totalResults", ArxivParser.NS)
        if total_element is None or total_element.text is None:
            raise create_parser_exception(
                self.entry,
                "",
                message="缺少总结果数元素",
            )

        return int(total_element.text)

    def build_search_result(self, query_params: SearchParams) -> SearchResult:
        return SearchResult(
            papers=[],
            total_result=self.parse_total_result(),
            page=1,
            has_next=False,
            query_params=query_params,
            metadata=Metadata(
                missing_results=0,
                pagesize=0,
                source="arxiv",
            ),
        )


class PaperParser:
    """Paper解析器"""

    def __init__(self, entry: ET.Element):
        self.entry = entry

    def parse_authors(self) -> list[Author]:
        """
        解析作者信息

        Returns:
            list[Author]: 作者列表
        """

        def get_text(element: ET.Element, tag: str, namespace: dict) -> Optional[str]:
            """辅助函数，用于获取子元素的文本内容"""
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
                message="缺少作者信息",
            )

        logger.trace(f"作者信息: {authors}")
        return authors

    def parse_categories(self) -> Category:
        """
        解析分类信息

        Returns:
            Category: 分类信息
        """

        def parse_primary() -> PrimaryCategory:
            """
            解析主分类信息

            Returns:
                PrimaryCategory: 主分类信息
            """
            primary_elem = self.entry.find("arxiv:primary_category", ArxivParser.NS)

            if primary_elem is None or "term" not in primary_elem.attrib:
                logger.warning("未找到主分类信息，使用默认分类")
                return PrimaryCategory(term="unknown", scheme=None, label=None)

            return PrimaryCategory(
                term=primary_elem.attrib["term"],
                scheme=cast(AnyUrl, primary_elem.attrib.get("scheme")),
                label=primary_elem.attrib.get("label"),
            )

        def parse_secondary() -> list[str]:
            """
            解析次级分类信息

            Returns:
                list[str]: 次级分类列表
            """
            categories = self.entry.findall("atom:category", ArxivParser.NS)
            primary_elem = self.entry.find("arxiv:primary_category", ArxivParser.NS)

            return [
                c.attrib["term"]
                for c in categories
                if "term" in c.attrib and c != primary_elem
            ]

        logger.trace(
            f"主分类信息: {parse_primary().model_dump()}, "
            f"次级分类信息: {parse_secondary()}"
        )
        return Category(primary=parse_primary(), secondary=parse_secondary())

    def parse_basics_info(self) -> BasicInfo:
        """
        解析基础信息

        Returns:
            BasicInfo: 基础信息
        """

        def get_or_raise(element: ET.Element, tag: str) -> str:
            sub_elem = element.find(f"atom:{tag}", ArxivParser.NS)
            if sub_elem is None or sub_elem.text is None:
                raise create_parser_exception(
                    element,
                    "",
                    message=f"缺少 {tag} 元素",
                )
            return sub_elem.text

        return BasicInfo(
            id=get_or_raise(self.entry, "id").split("/")[-1],
            title=get_or_raise(self.entry, "title"),
            summary=get_or_raise(self.entry, "summary"),
            authors=self.parse_authors(),
            categories=self.parse_categories(),
            published=self.parse_datetime(get_or_raise(self.entry, "published")),
            updated=self.parse_datetime(get_or_raise(self.entry, "updated")),
        )

    def parse_pdf_url(self) -> Optional[HttpUrl]:
        """
        解析PDF链接

        Returns:
            Optional[str]: PDF链接或None
        """
        try:
            links = self.entry.findall("atom:link", ArxivParser.NS)
            if not links:
                logger.warning("未找到任何链接")
                return None

            pdf_url = next(
                (
                    link.attrib["href"]
                    for link in links
                    if link.attrib.get("type") == "application/pdf"
                ),
                None,
            )

            if pdf_url is None:
                logger.warning("未找到PDF链接")
                return None

            return cast(HttpUrl, pdf_url)  # stupid type checker

        except (KeyError, AttributeError) as e:
            raise create_parser_exception(
                self.entry,
                "PDF链接解析失败",
                namespace=ArxivParser.NS["atom"],
                error=e,
            ) from e

    def parse_optional_fields(self) -> dict[str, Optional[str]]:
        """
        解析可选字段

        Returns:
            dict: 可选字段字典
        """
        fields = {
            "comment": self.entry.find("arxiv:comment", ArxivParser.NS),
            "journal_ref": self.entry.find("arxiv:journal_ref", ArxivParser.NS),
            "doi": self.entry.find("arxiv:doi", ArxivParser.NS),
        }

        return {k: v.text if v is not None else None for k, v in fields.items()}

    @staticmethod
    def parse_datetime(date_str: str) -> datetime:
        """
        解析ISO格式的日期时间字符串

        Args:
            date_str: ISO格式的日期时间字符串

        Returns:
            datetime: 解析后的datetime对象

        Raises:
            ValueError: 日期格式无效
        """
        try:
            normalized_date = date_str.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized_date)
        except ValueError as e:
            raise ValueError(f"日期格式: {date_str} 不符合预期") from e
