import xml.etree.ElementTree as ET
from datetime import datetime
from typing import ClassVar, Optional, cast

from pydantic import HttpUrl

from ..exception import ParseErrorContext, ParserException
from ..models import Author, Category, Paper
from .log import logger


class ArxivParser:
    """
    arXiv API响应解析器

    Attributes:
        NS (ClassVar[dict[str, str]]): XML命名空间

    Args:
        entry (ET.Element): 根元素

    Raises:
        ParserException: 如果解析失败
    """
    NS: ClassVar[dict[str, str]] = {
        "atom": "http://www.w3.org/2005/Atom",
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    def __init__(self, entry: ET.Element):
        self.entry = entry

    def _create_parser_exception(
            self, message: str, url: str = "", error: Optional[Exception] = None
    ) -> ParserException:
        """创建解析异常"""
        return ParserException(
            url=url,
            message=message,
            context=ParseErrorContext(
                raw_content=ET.tostring(self.entry, encoding="unicode"),
                element_name=self.entry.tag,
            ),
            original_error=error,
        )

    def parse_authors(self) -> list[Author]:
        """
        解析作者信息

        Returns:
            list[Author]: 作者列表

        Raises:
            ParserException: 如果作者信息无效
        """
        logger.debug("开始解析作者信息")
        authors = []
        for author_elem in self.entry.findall("atom:author", self.NS):
            name = author_elem.find("atom:name", self.NS)
            if name is not None and name.text:
                authors.append(Author(name=name.text))
            else:
                logger.warning("发现作者信息不完整")
        return authors

    def parse_entry_id(self) -> str:
        """解析论文ID

        Returns:
            str: 论文ID

        Raises:
            ParserException: 如果ID元素缺失或无效
        """
        id_elem = self.entry.find("atom:id", self.NS)
        if id_elem is None or id_elem.text is None:
            raise ParserException(
                url="",
                message="缺少论文ID",
                context=ParseErrorContext(
                    raw_content=ET.tostring(self.entry, encoding="unicode"),
                    element_name="id",
                    namespace=self.NS["atom"],
                ),
            )

        return id_elem.text

    def parse_categories(self) -> Category:
        """
        解析分类信息

        Returns:
            Category: 分类信息

        Raises:
            ParserException: 如果分类信息无效
        """
        logger.debug("开始解析分类信息")
        primary = self.entry.find("arxiv:primary_category", self.NS)
        categories = self.entry.findall("atom:category", self.NS)

        if primary is None or "term" not in primary.attrib:
            logger.warning("未找到主分类信息，使用默认分类")
            primary_category = "unknown"
        else:
            primary_category = primary.attrib["term"]

        return Category(
            primary=primary_category,
            secondary=[c.attrib["term"] for c in categories if "term" in c.attrib],
        )

    def parse_required_fields(self) -> dict:
        """
        解析必要字段

        Returns:
            dict: 必要字段字典

        Raises:
            ParserException: 如果字段缺失
        """
        fields = {
            "title": self.entry.find("atom:title", self.NS),
            "summary": self.entry.find("atom:summary", self.NS),
            "published": self.entry.find("atom:published", self.NS),
            "updated": self.entry.find("atom:updated", self.NS),
        }

        missing = [k for k, v in fields.items() if v is None or v.text is None]
        if missing:
            raise self._create_parser_exception(
                f"缺少必要字段: {', '.join(missing)}"
            )

        return {
            k: v.text for k, v in fields.items() if v is not None and v.text is not None
        }

    def _parse_pdf_url(self) -> Optional[str]:
        """
        解析PDF链接

        Returns:
            Optional[str]: PDF链接或None

        Raises:
            ParserException: 如果PDF链接无效
        """
        try:
            links = self.entry.findall("atom:link", self.NS)
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

            return pdf_url

        except (KeyError, AttributeError) as e:
            logger.error("解析PDF链接失败", exc_info=True)
            raise ParserException(
                url="",
                message="解析PDF链接失败",
                context=ParseErrorContext(
                    raw_content=ET.tostring(self.entry, encoding="unicode"),
                    element_name="link",
                    namespace=self.NS["atom"],
                ),
                original_error=e,
            )

    def parse_optional_fields(self) -> dict:
        """
        解析可选字段

        Returns:
            dict: 可选字段字典

        Raises:
            ParserException: 如果字段无效
        """
        fields = {
            "comment": self.entry.find("arxiv:comment", self.NS),
            "journal_ref": self.entry.find("arxiv:journal_ref", self.NS),
            "doi": self.entry.find("arxiv:doi", self.NS),
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
            logger.error(f"日期解析失败: {date_str}", exc_info=True)
            raise ValueError(f"无效的日期格式: {date_str}") from e

    def build_paper(
            self,
            index: int,
    ) -> Paper:
        """统一处理论文解析"""
        try:
            required_fields = self.parse_required_fields()
            return Paper(
                id=self.parse_entry_id().split("/")[-1],
                title=required_fields["title"],
                summary=required_fields["summary"],
                authors=self.parse_authors(),
                categories=self.parse_categories(),
                pdf_url=cast(HttpUrl, self._parse_pdf_url()),
                published=self.parse_datetime(
                    required_fields["published"].replace("Z", "+00:00")
                ),
                updated=self.parse_datetime(
                    required_fields["updated"].replace("Z", "+00:00")
                ),
                **self.parse_optional_fields(),
            )
        except ParserException:
            raise
        except Exception as e:
            raise ParserException(
                url="",
                message=f"解析第 {index + 1} 篇论文失败",
                context=ParseErrorContext(
                    raw_content=ET.tostring(self.entry, encoding="unicode"),
                    position=index,
                    element_name=self.entry.tag,
                ),
                original_error=e,
            )

    @classmethod
    def _parse_root(
            cls,
            root: ET.Element,
            url: str
    ) -> tuple[list[Paper], int]:
        """解析根元素"""
        # 解析总结果数
        total_element = root.find("opensearch:totalResults", cls.NS)
        if total_element is None or total_element.text is None:
            raise ParserException(
                url=url,
                message="缺少总结果数元素",
                context=ParseErrorContext(
                    raw_content=ET.tostring(root, encoding="unicode"),
                    element_name="totalResults",
                    namespace=cls.NS["opensearch"],
                ),
            )

        total_results = int(total_element.text)

        # 解析论文列表
        papers = []
        for i, entry in enumerate(root.findall("atom:entry", cls.NS)):
            try:
                parser = cls(entry)
                papers.append(parser.build_paper(i))
            except Exception as e:
                raise ParserException(
                    url=url,
                    message=f"解析第 {i + 1} 篇论文失败",
                    context=ParseErrorContext(
                        raw_content=ET.tostring(entry, encoding="unicode"),
                        position=i,
                        element_name=entry.tag,
                        namespace=cls.NS["atom"],
                    ),
                    original_error=e,
                )

        return papers, total_results

    @classmethod
    async def parse_feed(
            cls,
            content: str,
            url: str = ""
    ) -> tuple[list[Paper], int]:
        """
        解析arXiv API的Atom feed内容

        Args:
            content: XML内容
            url: 请求URL,用于错误上下文

        Returns:
            tuple[list[Paper], int]: 论文列表和总结果数
        """
        logger.debug("开始解析feed内容")
        try:
            root = ET.fromstring(content)
            return cls._parse_root(root, url)
        except ET.ParseError as e:
            logger.error("XML格式错误", exc_info=True)
            raise ParserException(
                url=url,
                message="XML格式错误",
                context=ParseErrorContext(raw_content=content),
                original_error=e,
            )
        except ParserException:
            raise
        except Exception as e:
            raise ParserException(
                url=url,
                message="未知解析错误",
                context=ParseErrorContext(raw_content=content),
                original_error=e,
            )
