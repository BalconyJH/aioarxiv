from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


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

    name: str
    affiliation: Optional[str] = None


class Category(BaseModel):
    """分类模型"""

    primary: str
    secondary: list[str] = Field(default_factory=list)


class Paper(BaseModel):
    """论文模型"""

    id: str = Field(description="arXiv ID")
    title: str
    summary: str
    authors: list[Author]
    categories: Category
    doi: Optional[str] = None
    journal_ref: Optional[str] = None
    pdf_url: Optional[HttpUrl] = None
    published: datetime
    updated: datetime
    comment: Optional[str] = None


class SearchParams(BaseModel):
    """搜索参数"""

    query: str
    id_list: list[str] = Field(default_factory=list)
    max_results: Optional[int] = Field(default=None, gt=0)
    start: int = Field(default=0, ge=0)
    sort_by: Optional[SortCriterion] = None
    sort_order: Optional[SortOrder] = None
