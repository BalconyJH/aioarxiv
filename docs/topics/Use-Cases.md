# Use Cases

## Basic Search {id="basic-search"}

### Search by Keywords {id="search-by-keywords"}

```python
from aioarxiv.client.arxiv_client import ArxivClient
from aioarxiv.models import SortCriterion, SortOrder

async def search_papers():
    async with ArxivClient() as client:
        # Simple keyword search
        result = await client.search("quantum computing")
        
        # Search with multiple keywords
        result = await client.search("machine learning AND neural networks")
        
        # Search with sorting
        result = await client.search(
            "quantum computing",
            sort_by=SortCriterion.LAST_UPDATED,
            sort_order=SortOrder.DESCENDING
        )
```

### Search by IDs {id="search-by-ids"}

```python
from aioarxiv.client.arxiv_client import ArxivClient

async def search_specific_papers():
    async with ArxivClient() as client:
        # Search for specific papers by their arXiv IDs
        result = await client.search(
            id_list=["2103.00020", "2103.00021"]
        )
```

## Paper Download {id="paper-download"}

### Download Single Paper {id="download-single-paper"}

```python
from pathlib import Path
from aioarxiv.client.arxiv_client import ArxivClient

async def download_paper():
    download_dir = Path("./papers")
    async with ArxivClient(
        enable_downloader=True,
        download_dir=download_dir
    ) as client:
        # Search and download a specific paper
        result = await client.search(id_list=["2103.00020"])
        paper = result.papers[0]
        
        # Download with default filename
        await client.download_paper(paper)
        
        # Download with custom filename
        await client.download_paper(paper, "quantum_paper.pdf")
```

### Batch Download {id="batch-download"}

```python
from pathlib import Path
from aioarxiv.client.arxiv_client import ArxivClient

async def batch_download():
    download_dir = Path("./papers")
    async with ArxivClient(
        enable_downloader=True,
        download_dir=download_dir
    ) as client:
        # Search for papers
        result = await client.search(
            "quantum computing",
            max_results=5
        )
        
        # Download all papers from search result
        tracker = await client.download_search_result(result)
        
        # Check download statistics
        print(f"Total: {tracker.total}")
        print(f"Completed: {tracker.completed}")
        print(f"Failed: {tracker.failed}")
```

## Advanced Usage {id="advanced-usage"}

### Custom Configuration {id="custom-configuration"}

```python
from aioarxiv.client.arxiv_client import ArxivClient
from aioarxiv.config import ArxivConfig

async def custom_client():
    # Create custom configuration
    config = ArxivConfig(
        timeout=60.0,
        max_retries=5,
        rate_limit_calls=2,
        rate_limit_period=6.0,
        proxy="http://proxy.example.com:8080"
    )
    
    # Initialize client with custom config
    async with ArxivClient(config=config) as client:
        result = await client.search("quantum computing")
```

### Error Handling {id="error-handling-example"}

```python
from aioarxiv.client.arxiv_client import ArxivClient
from aioarxiv.exception import (
    HTTPException,
    QueryBuildError,
    PaperDownloadException
)

async def handle_errors():
    try:
        async with ArxivClient(enable_downloader=True) as client:
            # Search with invalid query
            result = await client.search("quantum computing")
            
            # Try to download papers
            await client.download_search_result(result)
            
    except HTTPException as e:
        print(f"HTTP error: {e.status_code}")
    except QueryBuildError as e:
        print(f"Query error: {e}")
    except PaperDownloadException as e:
        print(f"Download error: {e}")
```

### Pagination {id="pagination-example"}

```python
from aioarxiv.client.arxiv_client import ArxivClient

async def paginated_search():
    async with ArxivClient() as client:
        # Get first page
        result = await client.search(
            "quantum computing",
            max_results=10,
            start=0
        )
        
        # Get second page
        if result.has_next:
            next_result = await client.search(
                "quantum computing",
                max_results=10,
                start=10
            )
```

## Working with Results {id="working-with-results"}

### Processing Papers {id="processing-papers"}

```python
from aioarxiv.client.arxiv_client import ArxivClient


async def process_papers():
    async with ArxivClient() as client:
        result = await client.search("quantum computing")

        for paper in result.papers:
            # Access paper information
            print(f"Title: {paper.info.title}")
            print(f"Authors: {', '.join(a.name for a in paper.info.authors)}")
            print(f"Published: {paper.info.published}")
            print(f"Updated: {paper.info.updated}")
            print(f"Summary: {paper.info.summary}")

            # Access additional information
            if paper.doi:
                print(f"DOI: {paper.doi}")
            if paper.journal_ref:
                print(f"Journal: {paper.journal_ref}")
            if paper.pdf_url:
                print(f"PDF URL: {paper.pdf_url}")
```