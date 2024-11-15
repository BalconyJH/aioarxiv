# Aioarxiv

An async Python client for the arXiv API with enhanced performance and flexible configuration options.

> ⚠️ Warning: This project is currently in beta. Not recommended for production use.

## Features

- Asynchronous API calls for better performance
- Flexible search and download capabilities
- Customizable rate limiting and concurrent requests
- Simple error handling

## Installation

```bash
pip install aioarxiv
```

## Quick Start

```python
import asyncio
from aioarxiv import ArxivClient

async def main():
    async with ArxivClient() as client:
        async for paper in client.search("quantum computing", max_results=1):
            print(f"Title: {paper.title}")
            print(f"Authors: {', '.join(a.name for a in paper.authors)}")
            print(f"Summary: {paper.summary[:200]}...")
            
            # Download PDF
            file_path = await client.download_paper(paper)
            print(f"Downloaded to: {file_path}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Configuration

```python
from aioarxiv import ArxivConfig, ArxivClient

config = ArxivConfig(
    rate_limit_calls=3,      # Rate limit per window
    rate_limit_period=1.0,   # Window period in seconds
    max_concurrent_requests=3 # Max concurrent requests
)

client = ArxivClient(config=config)
```

## Error Handling
    
```python
try:
    async for paper in client.search("quantum computing"):
        print(paper.title)
except SearchCompleteException:
    print("Search complete")
```

## Requirements
* Python 3.9 or higher

## License
[MIT License (c) 2024 BalconyJH ](LICENSE)

## Links
* Documentation for aioarxiv is WIP
* [ArXiv API](https://info.arxiv.org/help/api/index.html)