from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re
from typing import Annotated, Optional
import uuid
from zoneinfo import ZoneInfo

from pydantic import (
    UUID4,
    AnyUrl,
    BaseModel,
    Field,
    HttpUrl,
    computed_field,
    field_validator,
)
from yarl import URL

from aioarxiv.config import default_config


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
    affiliation: Optional[str] = Field(
        None, description="Author's institutional affiliation"
    )


class PrimaryCategory(BaseModel):
    """Primary category model for paper classification.

    Attributes:
        term: Category identifier.
        scheme: URI of the classification system.
        label: Human-readable category label.
    """

    term: str = Field(description="Category identifier")
    scheme: Optional[AnyUrl] = Field(None, description="Classification system URI")
    label: Optional[str] = Field(None, description="Category label")


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
    doi: Optional[str] = Field(None, description="DOI (must match regex pattern)")
    journal_ref: Optional[str] = Field(None, description="Journal reference")
    pdf_url: Optional[HttpUrl] = Field(None, description="PDF download URL")
    comment: Optional[str] = Field(None, description="Author comments or notes")

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, v: Optional[str]) -> Optional[str]:
        """Validate DOI format.

        Args:
            v: DOI string to validate.

        Returns:
            The validated DOI string.

        Raises:
            ValueError: If DOI format is invalid.
        """
        if v is None:
            return v

        pattern = r"^10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+$"
        if not re.match(pattern, v):
            msg = "Invalid DOI format. Must match pattern: 10.XXXX/suffix"
            raise ValueError(msg)
        return v


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

    query: Optional[str] = Field(None, description="Search keywords")
    id_list: Optional[list[str]] = Field(
        None, description="Specific arXiv IDs to search"
    )
    start: Optional[int] = Field(default=0, ge=0, description="Starting index")
    max_results: Optional[int] = Field(default=10, gt=0, description="Maximum results")
    sort_by: Optional[SortCriterion] = Field(None, description="Sort criterion")
    sort_order: Optional[SortOrder] = Field(None, description="Sort direction")


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
        default_factory=lambda: datetime.now(tz=ZoneInfo(default_config.timezone)),
        description="Request creation timestamp",
    )
    end_time: Optional[datetime] = Field(
        None,
        description="Request completion timestamp",
    )
    missing_results: int = Field(description="Missing results count")
    pagesize: int = Field(description="Results per page")
    source: URL = Field(description="Data source URL")

    model_config = {"arbitrary_types_allowed": True}

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
        default_factory=lambda: uuid.uuid4(),
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


class DownloadStats(BaseModel):
    """Download statistics model.

    Attributes:
        total: Total number of downloads.
        completed: Number of completed downloads.
        failed: Number of failed downloads.
        start_time: Download start timestamp.
        end_time: Download completion timestamp.
        papers: List of successfully downloaded papers.
        failed_papers: List of papers that failed to download with errors.
    """

    total: int = Field(description="Total downloads")
    completed: int = Field(default=0, description="Completed downloads")
    failed: int = Field(default=0, description="Failed downloads")
    start_time: datetime = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo(default_config.timezone)),
        description="Start timestamp",
    )
    end_time: Optional[datetime] = Field(default=None, description="End timestamp")
    papers: Annotated[
        list[Paper], Field(default_factory=list, description="Downloaded papers")
    ]
    failed_papers: Annotated[
        list[tuple[Paper, Exception]],
        Field(default_factory=list, description="Failed papers with errors"),
    ]

    model_config = {"arbitrary_types_allowed": True}


@dataclass
class PageParam:
    """Page parameters for pagination.

    Attributes:
        start: Starting index.
        end: Ending index.
    """

    start: int
    end: int
