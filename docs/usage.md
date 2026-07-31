# Usage

## Client lifecycle

`ArxivClient` owns an aiohttp session and should be used as an async context
manager so the underlying connections are always released:

```python
from aioarxiv import ArxivClient


async def main() -> None:
    async with ArxivClient() as client:
        result = await client.search("quantum computing")
```

If you cannot use `async with`, call `await client.close()` yourself when done.

## Searching

### By keyword query

`search()` accepts an arXiv query expression. Field prefixes (`ti:`, `au:`,
`abs:`, `cat:`, `all:`, ...) and the boolean operators `AND`, `OR`, and
`ANDNOT` work as described in the
[arXiv API user manual](https://info.arxiv.org/help/api/user-manual.html#query_details).

```python
from aioarxiv import ArxivClient


async def search_papers() -> None:
    async with ArxivClient() as client:
        # Simple keyword search
        result = await client.search("quantum computing", max_results=10)

        # Field-prefixed search with boolean operators
        result = await client.search(
            "cat:cs.AI AND ti:transformer",
            max_results=10,
        )

        print(f"Matched {result.total_result} papers")
        for paper in result.papers:
            print(paper.info.title)
```

### By arXiv ID list

Pass `id_list` instead of a query to fetch specific papers:

```python
from aioarxiv import ArxivClient


async def fetch_specific_papers() -> None:
    async with ArxivClient() as client:
        result = await client.search(id_list=["2103.00020", "2103.00021"])
```

### Sorting

Use `SortCriterion` and `SortOrder` to control result ordering:

```python
from aioarxiv import ArxivClient
from aioarxiv.models import SortCriterion, SortOrder


async def sorted_search() -> None:
    async with ArxivClient() as client:
        result = await client.search(
            "quantum computing",
            max_results=10,
            sort_by=SortCriterion.LAST_UPDATED,
            sort_order=SortOrder.DESCENDING,
        )
```

### Pagination and API limits

`search()` fetches results in pages of `page_size` (see
[Configuration](configuration.md)) and aggregates them until `max_results` is
reached, so you usually do not need to paginate manually. Use `start` to begin
at a specific offset.

!!! note "arXiv API limits"

    - A single API request returns at most **2000** results per page.
    - The API refuses to page beyond **30000** total results for one query
      (HTTP 400); refine your query instead of paging deeper.
    - The [arXiv Terms of Use](https://info.arxiv.org/help/api/tou.html)
      require **no more than one request every three seconds** from a single
      connection. The default configuration respects this; the client logs a
      warning if you configure a more aggressive rate.

!!! warning "Combining a query with an ID list"

    When you pass both `query` and `id_list`, the query is applied as a filter
    within the ID list and only the first page is returned; `max_results` and
    `start` are not paginated for this combined form. Filter locally instead if
    you need more than one page of results.

## Downloading papers

The downloader is opt-in. Pass `enable_downloader=True` (and optionally
`download_dir`) when constructing the client.

### Single paper

```python
from pathlib import Path

from aioarxiv import ArxivClient


async def download_one() -> None:
    async with ArxivClient(
        enable_downloader=True,
        download_dir=Path("./papers"),
    ) as client:
        result = await client.search(id_list=["2103.00020"])
        paper = result.papers[0]

        # Download with a generated filename
        await client.download_paper(paper)

        # Download with a custom filename
        await client.download_paper(paper, "quantum_paper.pdf")
```

### Batch download

`download_search_result()` downloads every paper in a search result and
returns a `DownloadTracker` with per-paper outcomes:

```python
from pathlib import Path

from aioarxiv import ArxivClient


async def download_many() -> None:
    async with ArxivClient(
        enable_downloader=True,
        download_dir=Path("./papers"),
    ) as client:
        result = await client.search("quantum computing", max_results=5)
        tracker = await client.download_search_result(result)
        if tracker is not None:
            print(f"Total: {tracker.total}")
            print(f"Completed: {tracker.completed}")
            print(f"Failed: {tracker.failed}")
```

## Error handling

```python
from aioarxiv import ArxivClient
from aioarxiv.exception import (
    HTTPException,
    PaperDownloadException,
    QueryBuildError,
)


async def handle_errors() -> None:
    try:
        async with ArxivClient(enable_downloader=True) as client:
            result = await client.search("quantum computing", max_results=5)
            await client.download_search_result(result)
    except HTTPException as e:
        print(f"HTTP error: {e.status_code}")
    except QueryBuildError as e:
        print(f"Query error: {e}")
    except PaperDownloadException as e:
        print(f"Download error: {e}")
```

## Working with results

```python
from aioarxiv import ArxivClient


async def process_papers() -> None:
    async with ArxivClient() as client:
        result = await client.search("quantum computing", max_results=10)

        for paper in result.papers:
            print(f"Title: {paper.info.title}")
            print(f"Authors: {', '.join(a.name for a in paper.info.authors)}")
            print(f"Published: {paper.info.published}")
            print(f"Updated: {paper.info.updated}")
            print(f"Summary: {paper.info.summary}")

            if paper.doi:
                print(f"DOI: {paper.doi}")
            if paper.journal_ref:
                print(f"Journal: {paper.journal_ref}")
            if paper.pdf_url:
                print(f"PDF URL: {paper.pdf_url}")
```
