# API Reference

## ArxivClient {id="arxiv-client"}

The main class for interacting with the arXiv API. Provides methods for searching papers and downloading PDFs.

### Basic Usage {id="basic-usage"}

```python
from aioarxiv.client.arxiv_client import ArxivClient


async def foo():
    async with ArxivClient() as client:
        # Search by query
        result = await client.search("quantum computing")

        # Search by IDs
        result = await client.search(id_list=["2103.00020", "2103.00021"])

        # Download papers
        await client.download_search_result(result)
```

### Constructor {id="constructor"}

```python
from typing import Optional
from aioarxiv.config import ArxivConfig
from aioarxiv.utils.session import SessionManager
from pathlib import Path


def __init__(
        config: Optional[ArxivConfig] = None,
        session_manager: Optional[SessionManager] = None,
        *,
        enable_downloader: bool = False,
        download_dir: Optional[Path] = None,
) -> None: ...
```

#### Parameters {id="constructor-parameters"}

- `config`: Optional[ArxivConfig] - Custom configuration for the client
- `session_manager`: Optional[SessionManager] - Custom session manager
- `enable_downloader`: bool - Whether to enable the paper downloader
- `download_dir`: Optional[Path] - Directory path for downloading papers

### Methods {id="methods"}

#### search() {id="method-search"}

Search arXiv papers via either a keyword query or arXiv ID list.

```python
from typing import Optional, overload
from aioarxiv.models import SearchResult, SortCriterion, SortOrder


@overload
async def search(
        query: str,
        id_list: None = None,
        max_results: Optional[int] = None,
        sort_by: Optional[SortCriterion] = None,
        sort_order: Optional[SortOrder] = None,
        start: Optional[int] = None,
) -> SearchResult: ...


@overload
async def search(
        query: None = None,
        id_list: list[str] = ...,
        max_results: Optional[int] = None,
        sort_by: Optional[SortCriterion] = None,
        sort_order: Optional[SortOrder] = None,
        start: Optional[int] = None,
) -> SearchResult: ...
```

##### Parameters {id="search-parameters"}

- `query`: Optional[str] - Keyword-based query string
- `id_list`: Optional[list[str]] - List of arXiv IDs to retrieve
- `max_results`: Optional[int] - Maximum number of results to return
- `sort_by`: Optional[SortCriterion] - Criterion to sort results by
- `sort_order`: Optional[SortOrder] - Order of sorting
- `start`: Optional[int] - Starting index for results

##### Returns {id="search-returns"}

- `SearchResult` - Object containing search results and metadata

#### download_paper() {id="method-download-paper"}

Download a single paper from arXiv.

```python
from typing import Optional
from aioarxiv.models import Paper


async def download_paper(
        paper: Paper,
        filename: Optional[str] = None,
) -> Optional[None]: ...
```

##### Parameters {id="download-paper-parameters"}

- `paper`: Paper - Paper object containing download information
- `filename`: Optional[str] - Custom filename for the downloaded paper

##### Returns {id="download-paper-returns"}

- `Optional[None]` - None if downloader is disabled

#### download_search_result() {id="method-download-search-result"}

Download all papers from a search result.

```python
from typing import Optional
from aioarxiv.models import SearchResult
from aioarxiv.client.downloader import DownloadTracker


async def download_search_result(
        search_result: SearchResult,
) -> Optional[DownloadTracker]: ...
```

##### Parameters {id="download-search-result-parameters"}

- `search_result`: SearchResult - Search result containing papers to download

##### Returns {id="download-search-result-returns"}

- `Optional[DownloadTracker]` - Download tracker if downloader is enabled

### Enums {id="enums"}

#### SortCriterion {id="enum-sort-criterion"}

```python
from enum import Enum


class SortCriterion(str, Enum):
    RELEVANCE = "relevance"
    LAST_UPDATED = "lastUpdatedDate"
    SUBMITTED = "submittedDate"
```

#### SortOrder {id="enum-sort-order"}

```python
from enum import Enum


class SortOrder(str, Enum):
    ASCENDING = "ascending"
    DESCENDING = "descending"
```

### Models {id="models"}

#### SearchResult {id="model-search-result"}

Contains search results and metadata.

##### Attributes {id="search-result-attributes"}

- `id`: UUID4 - Result identifier
- `papers`: list[Paper] - List of papers in the result
- `total_result`: int - Total number of matching papers
- `page`: int - Current page number
- `has_next`: bool - Whether more results are available
- `query_params`: SearchParams - Search parameters used
- `metadata`: Metadata - Search operation metadata

#### Paper {id="model-paper"}

Represents an arXiv paper.

##### Attributes {id="paper-attributes"}

- `info`: BasicInfo - Basic paper information
- `doi`: Optional[str] - Digital Object Identifier
- `journal_ref`: Optional[str] - Journal reference
- `pdf_url`: Optional[HttpUrl] - URL for PDF download
- `comment`: Optional[str] - Author comments

### Error Handling {id="error-handling"}

The client may raise the following exceptions:

- `HTTPException`: For HTTP request errors
- `QueryBuildError`: For search query construction errors
- `PaperDownloadException`: For paper download failures
- `ValidationException`: For data validation errors

### Context Manager Support {id="context-manager"}

The client supports async context management:

```python
from aioarxiv.client.arxiv_client import ArxivClient


async def foo():
    async with ArxivClient() as client:
        result = await client.search("quantum computing")
```

