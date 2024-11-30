import re
from enum import Enum
from typing import Optional
from datetime import datetime

from pydantic import Field, AnyUrl, HttpUrl, BaseModel, computed_field, field_validator


class SortCriterion(str, Enum):
    """排序标准"""

    RELEVANCE = "relevance"
    LAST_UPDATED = "lastUpdatedDate"
    SUBMITTED = "submittedDate"


class SortOrder(str, Enum):
    """排序方向"""

    ASCENDING = "ascending"
    DESCENDING = "descending"


class Author(BaseModel):
    """作者模型"""

    name: str = Field(description="作者姓名")
    affiliation: Optional[str] = Field(None, description="作者的机构隶属信息")


class PrimaryCategory(BaseModel):
    """主分类模型"""

    term: str = Field(description="分类标识符（必须）")
    scheme: Optional[AnyUrl] = Field(None, description="分类系统的 URI")
    label: Optional[str] = Field(None, description="分类标签")


class Category(BaseModel):
    """分类模型"""

    primary: PrimaryCategory = Field(description="主分类")
    secondary: list[str] = Field(description="次级分类列表")


class BasicInfo(BaseModel):
    """基础论文信息"""

    id: str = Field(description="arXiv ID")
    title: str = Field(description="标题")
    summary: str = Field(description="摘要")
    authors: list[Author] = Field(description="作者列表")
    categories: Category = Field(description="分类")
    published: datetime = Field(description="发布时间")
    updated: datetime = Field(description="更新时间")


class Paper(BaseModel):
    """论文模型"""

    info: BasicInfo = Field(description="基础信息")
    doi: Optional[str] = Field(None, description="DOI，格式需符合正则")
    journal_ref: Optional[str] = Field(None, description="期刊引用")
    pdf_url: Optional[HttpUrl] = Field(None, description="PDF下载链接")
    comment: Optional[str] = Field(None, description="作者评论或注释")

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v

        pattern = r"^10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+$"
        if not re.match(pattern, v):
            raise ValueError("Invalid DOI format. Must match pattern: 10.XXXX/suffix")
        return v


class SearchParams(BaseModel):
    """搜索参数"""

    query: str = Field(description="搜索关键词")
    id_list: Optional[list[str]] = Field(None, description="需要精确搜索的ID列表")
    start: int = Field(default=0, ge=0, description="起始索引")
    max_results: Optional[int] = Field(default=None, gt=0, description="最大返回结果数")
    sort_by: Optional[SortCriterion] = Field(None, description="排序标准")
    sort_order: Optional[SortOrder] = Field(None, description="排序方向")


class Metadata(BaseModel):
    """元数据模型"""

    start_time: datetime = Field(
        default_factory=datetime.now, description="请求创建时间"
    )
    end_time: datetime = Field(default_factory=datetime.now, description="请求结束时间")
    missing_results: int = Field(description="缺失结果数")
    pagesize: int = Field(description="每页结果数")
    source: str = Field(description="数据源")

    @computed_field
    def duration_seconds(self) -> float:
        """持续时间(秒)，保留3位小数"""
        return round((self.end_time - self.start_time).total_seconds(), 3)

    @computed_field
    def duration_ms(self) -> float:
        """持续时间(毫秒)，保留3位小数"""
        delta = self.end_time - self.start_time
        return round(delta.total_seconds() * 1000, 3)


class SearchResult(BaseModel):
    """搜索结果模型"""

    papers: list[Paper] = Field(description="论文结果列表")
    total_result: int = Field(description="匹配的总论文数量")
    page: int = Field(description="当前页码")
    has_next: bool = Field(description="是否有下一页")
    query_params: SearchParams = Field(description="搜索参数")
    metadata: Metadata = Field(description="元数据")

    @computed_field
    def papers_count(self) -> int:
        return len(self.papers)


class NamespaceModel(BaseModel):
    """命名空间模型"""

    atom: str = Field("http://www.w3.org/2005/Atom", description="Atom 命名空间")
    opensearch: str = Field(
        "http://a9.com/-/spec/opensearch/1.1/", description="OpenSearch 命名空间"
    )
    arxiv: str = Field("http://arxiv.org/schemas/atom", description="arXiv 命名空间")
