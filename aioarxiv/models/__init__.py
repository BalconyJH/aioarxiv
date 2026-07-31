from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import uuid
from zoneinfo import ZoneInfo

from pydantic import (
    UUID4,
    AnyUrl,
    BaseModel,
    Field,
    HttpUrl,
    computed_field,
)

from aioarxiv.utils.log import ConfigManager


class SortCriterion(str, Enum):
    """Sort criteria for search results."""

    RELEVANCE = "relevance"
    LAST_UPDATED = "lastUpdatedDate"
    SUBMITTED = "submittedDate"


class SortOrder(str, Enum):
    """Sort direction for search results."""

    ASCENDING = "ascending"
    DESCENDING = "descending"


class Author(BaseModel):
    """Author model representing paper authors.

    Attributes:
        name: Author's full name.
        affiliation: Author's institutional affiliation.
    """

    name: str = Field(description="Author's name")
    affiliation: str | None = Field(
        default=None, description="Author's institutional affiliation"
    )


class PrimaryCategory(BaseModel):
    """Primary category model for paper classification.

    Attributes:
        term: Category identifier.
        scheme: URI of the classification system.
        label: Human-readable category label.
    """

    term: str = Field(description="Category identifier")
    scheme: AnyUrl | None = Field(default=None, description="Classification system URI")
    label: str | None = Field(default=None, description="Category label")


class Category(BaseModel):
    """Category model containing primary and secondary classifications.

    Attributes:
        primary: Primary category classification.
        secondary: List of secondary category classifications.
    """

    primary: PrimaryCategory = Field(description="Primary category")
    secondary: list[str] = Field(description="Secondary categories")


class BasicInfo(BaseModel):
    """Basic paper information model.

    Attributes:
        id: arXiv paper ID.
        title: Paper title.
        summary: Paper abstract.
        authors: List of paper authors.
        categories: Paper categories.
        published: Publication timestamp.
        updated: Last update timestamp.
    """

    id: str = Field(description="arXiv ID")
    title: str = Field(description="Title")
    summary: str = Field(description="Abstract")
    authors: list[Author] = Field(description="Authors")
    categories: Category = Field(description="Categories")
    published: datetime = Field(description="Publication timestamp")
    updated: datetime = Field(description="Last update timestamp")


class Paper(BaseModel):
    """Paper model containing complete paper information.

    Attributes:
        info: Basic paper information.
        doi: Digital Object Identifier.
        journal_ref: Journal reference.
        pdf_url: URL for PDF download.
        comment: Author comments or notes.
    """

    info: BasicInfo = Field(description="Basic information")
    doi: str | None = Field(default=None, description="DOI as provided by arXiv")
    journal_ref: str | None = Field(default=None, description="Journal reference")
    pdf_url: HttpUrl | None = Field(default=None, description="PDF download URL")
    comment: str | None = Field(default=None, description="Author comments or notes")


class SearchParams(BaseModel):
    """Search parameters model.

    Attributes:
        query: Search keywords.
        id_list: List of specific arXiv IDs to search.
        start: Starting index for results.
        max_results: Maximum number of results to return.
        sort_by: Sorting criterion.
        sort_order: Sort direction.
    """

    query: str | None = Field(default=None, description="Search keywords")
    id_list: list[str] | None = Field(
        default=None, description="Specific arXiv IDs to search"
    )
    start: int | None = Field(default=0, ge=0, description="Starting index")
    max_results: int | None = Field(default=10, gt=0, description="Maximum results")
    sort_by: SortCriterion | None = Field(default=None, description="Sort criterion")
    sort_order: SortOrder | None = Field(default=None, description="Sort direction")


class Metadata(BaseModel):
    """Metadata model for search operations.

    Attributes:
        start_time: Request creation timestamp.
        end_time: Request completion timestamp.
        missing_results: Number of missing results.
        pagesize: Results per page.
        source: Data source URL.
    """

    start_time: datetime = Field(
        default_factory=lambda: datetime.now(
            tz=ZoneInfo(ConfigManager.get_config().timezone)
        ),
        description="Request creation timestamp",
    )
    end_time: datetime | None = Field(
        default=None,
        description="Request completion timestamp",
    )
    missing_results: int = Field(description="Missing results count")
    pagesize: int = Field(description="Results per page")
    source: str = Field(description="Data source URL")

    @computed_field
    def duration_seconds(self) -> float:
        """Calculate duration in seconds (3 decimal places)."""
        if self.end_time is None:
            return 0.000
        return round((self.end_time - self.start_time).total_seconds(), 3)

    @computed_field
    def duration_ms(self) -> float:
        """Calculate duration in milliseconds (3 decimal places)."""
        if self.end_time is None:
            return 0.000
        delta = self.end_time - self.start_time
        return round(delta.total_seconds() * 1000, 3)


class SearchResult(BaseModel):
    """Search result model containing papers and metadata.

    Attributes:
        id: Result UUID.
        papers: List of paper results.
        total_result: Total number of matching papers.
        page: Current page number.
        has_next: Whether there are more pages.
        query_params: Search parameters used.
        metadata: Search operation metadata.
    """

    id: UUID4 = Field(
        default_factory=uuid.uuid4,
        description="Result UUID",
    )
    papers: list[Paper] = Field(description="Paper results")
    total_result: int = Field(description="Total matching papers")
    page: int = Field(description="Current page number")
    has_next: bool = Field(description="Has next page")
    query_params: SearchParams = Field(description="Search parameters")
    metadata: Metadata = Field(description="Operation metadata")

    @computed_field
    def papers_count(self) -> int:
        """Get the number of papers in the result."""
        return len(self.papers)


@dataclass
class PageParam:
    """Page parameters for pagination.

    Attributes:
        start: Starting index.
        end: Ending index.
    """

    start: int
    end: int
