# Aioarxiv

An async Python client for the arXiv API with enhanced performance and flexible configuration options.

<a href="https://raw.githubusercontent.com/BalconyJH/aioarxiv/main/LICENSE">
    <img src="https://img.shields.io/github/license/BalconyJH/aioarxiv" alt="license">
</a>
<a href="https://pypi.org/project/aioarxiv/">
    <img src="https://img.shields.io/pypi/v/aioarxiv?logo=python&logoColor=edb641" alt="pypi">
</a>
<a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=edb641" alt="python">
</a>
<a href="https://codecov.io/gh/BalconyJH/aioarxiv">
    <img src="https://img.shields.io/codecov/c/github/BalconyJH/aioarxiv" alt="codecov">
</a>
<a href="https://github.com/DetachHead/basedpyright">
    <img src="https://img.shields.io/badge/types-basedpyright-797952.svg?logo=python&logoColor=edb641" alt="basedpyright">
</a>
<a href="https://github.com/astral-sh/ruff">
    <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json" alt="ruff">
</a>
<a href="https://github.com/astral-sh/uv">
    <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv">
</a>
<a href="https://github.com/BalconyJH/aioarxiv/actions/workflows/ci.yml">
    <img src="https://github.com/BalconyJH/aioarxiv/actions/workflows/ci.yml/badge.svg?branch=main&event=push" alt="ci">
</a>
<a href="https://github.com/BalconyJH/aioarxiv/actions/workflows/coverage.yml">
    <img src="https://github.com/BalconyJH/aioarxiv/actions/workflows/coverage.yml/badge.svg?branch=main&event=push" alt="coverage">
</a>
<a href="https://github.com/BalconyJH/aioarxiv/actions/workflows/docs.yml">
    <img src="https://github.com/BalconyJH/aioarxiv/actions/workflows/docs.yml/badge.svg?branch=main&event=push" alt="docs">
</a>
<a href="https://pypi.org/project/aioarxiv/">
    <img src="https://img.shields.io/pypi/dm/aioarxiv" alt="downloads">
</a>

> [!WARNING]
> This project is currently under development and has not yet reached a stable release. We do not recommend using it in
> production environments.

## Features

- Asynchronous API calls for better performance
- Customized configuration client
- Flexible search and download capabilities
- Rate limiting and concurrency control aligned with the arXiv API terms of use
- Complete type hints (PEP 561) and documentation

## Installation

```bash
pip install aioarxiv
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add aioarxiv
```

## Quick Start

```python
import asyncio

from aioarxiv import ArxivClient


async def main() -> None:
    async with ArxivClient() as client:
        result = await client.search("all:electron", max_results=10)
        print(f"Total results: {result.total_result}")
        for paper in result.papers:
            print(paper.info.title)


asyncio.run(main())
```

## Configuration

You can configure the client by passing an instance of `ArxivConfig` to the `ArxivClient` constructor.
Configuration in a dotenv file is also an option; values are loaded automatically from environment
variables with the `ARXIV_` prefix.

```python
from aioarxiv import ArxivClient, ArxivConfig

config = ArxivConfig(
    proxy="http://127.0.0.1:10808",
    log_level="DEBUG",
    page_size=10,
)
client = ArxivClient(config=config)
```

## Requirements

* Python 3.10 or higher

## License

[MIT License (c) 2025 BalconyJH](LICENSE)

## Links

* [Documentation](https://balconyjh.github.io/aioarxiv/)
* [arXiv API](https://info.arxiv.org/help/api/index.html)
