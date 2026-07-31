"""Asynchronous Python client for the arXiv API."""

from importlib.metadata import PackageNotFoundError, version

from aioarxiv.client import ArxivClient, ArxivDownloader, DownloadTracker
from aioarxiv.config import ArxivConfig, default_config
from aioarxiv.exception import (
    ArxivException,
    HTTPException,
    PaperDownloadException,
    ParserException,
    QueryBuildError,
    RateLimitException,
    TimeoutException,
)
from aioarxiv.models import (
    Author,
    BasicInfo,
    Category,
    Metadata,
    Paper,
    PrimaryCategory,
    SearchParams,
    SearchResult,
    SortCriterion,
    SortOrder,
)

try:
    __version__ = version("aioarxiv")
except PackageNotFoundError:  # pragma: no cover - source tree without metadata
    __version__ = "0.0.0"

__all__ = [
    "ArxivClient",
    "ArxivConfig",
    "ArxivDownloader",
    "ArxivException",
    "Author",
    "BasicInfo",
    "Category",
    "DownloadTracker",
    "HTTPException",
    "Metadata",
    "Paper",
    "PaperDownloadException",
    "ParserException",
    "PrimaryCategory",
    "QueryBuildError",
    "RateLimitException",
    "SearchParams",
    "SearchResult",
    "SortCriterion",
    "SortOrder",
    "TimeoutException",
    "__version__",
    "default_config",
]
