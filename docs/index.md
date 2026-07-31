# aioarxiv

Async Python client for the [arXiv API](https://info.arxiv.org/help/api/index.html)
with built-in rate limiting and paper downloads.

## Features

- Async paper search and downloads from arXiv
- Built-in rate limiting and concurrency control
- Customizable configuration via code, environment variables, or `.env` files
- Atom feed parsing into typed models
- Type-safe results validated with Pydantic

## Installation

aioarxiv requires Python 3.10 or higher.

=== "uv"

    ```bash
    uv add aioarxiv
    ```

=== "pip"

    ```bash
    pip install aioarxiv
    ```

## Quickstart

```python
import asyncio

from aioarxiv import ArxivClient


async def main() -> None:
    async with ArxivClient() as client:
        result = await client.search("cat:cs.AI", max_results=10)
        for paper in result.papers:
            print(paper.info.title)


asyncio.run(main())
```

See [Usage](usage.md) for search, pagination, and download examples, and
[Configuration](configuration.md) for tuning timeouts, proxies, and rate limits.

## Links

- [GitHub repository](https://github.com/BalconyJH/aioarxiv)
- [PyPI project](https://pypi.org/project/aioarxiv/)
- [arXiv API user manual](https://info.arxiv.org/help/api/user-manual.html)
- [Issue tracker](https://github.com/BalconyJH/aioarxiv/issues)
