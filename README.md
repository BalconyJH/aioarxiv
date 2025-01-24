# Aioarxiv

<a href="https://raw.githubusercontent.com/BalconyJH/aioarxiv/main/LICENSE">
    <img src="https://img.shields.io/github/license/BalconyJH/aioarxiv" alt="license">
</a>
<a href="https://pypi.org/project/aioarxiv/">
    <img src="https://img.shields.io/pypi/v/aioarxiv?logo=python&logoColor=edb641" alt="pypi">
</a>
<img src="https://img.shields.io/badge/python-3.9+-blue?logo=python&logoColor=edb641" alt="python">
<a href="https://codecov.io/gh/BalconyJH/aioarxiv">
    <img src="https://img.shields.io/codecov/c/github/BalconyJH/aioarxiv" alt="codecov">
</a>
<a href="https://github.com/psf/black">
    <img src="https://img.shields.io/badge/code%20style-black-000000.svg?logo=python&logoColor=edb641" alt="black">
  </a>
<a href="https://github.com/Microsoft/pyright">
    <img src="https://img.shields.io/badge/types-pyright-797952.svg?logo=python&logoColor=edb641" alt="pyright">
</a>
<a href="https://github.com/astral-sh/ruff">
    <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json" alt="ruff">
</a>
<a href="https://github.com/BalconyJH/aioarxiv/actions/workflows/build-docs.yml">
    <img src="https://github.com/BalconyJH/aioarxiv/actions/workflows/build-docs.yml/badge.svg?branch=main&event=push" alt="site"/>
</a>
<a href="https://github.com/BalconyJH/aioarxiv/actions/workflows/pyright.yml">
    <img src="https://github.com/BalconyJH/aioarxiv/actions/workflows/pyright.yml/badge.svg?branch=main&event=push" alt="pyright">
</a>
<a href="https://github.com/BalconyJH/aioarxiv/actions/workflows/ruff.yml">
    <img src="https://github.com/BalconyJH/aioarxiv/actions/workflows/ruff.yml/badge.svg?branch=main&event=push" alt="ruff">
</a>
<a href="https://pypi.org/project/aioarxiv/">
    <img src="https://img.shields.io/pypi/dm/aioarxiv" alt="pypi">
</a>

An async Python client for the arXiv API with enhanced performance and flexible configuration options.

> [!WARNING]
> This project is currently under development and has not yet reached a stable release. We do not recommend using it in
> production environments.

## Features

- Asynchronous API calls for better performance
- Customized configuration client
- Flexible search and download capabilities
- Customizable rate limiting and concurrent requests
- Complete type hints and documentation

## Installation

```bash
pip install aioarxiv
```

## Quick Start

```python
from aioarxiv.client.arxiv_client import ArxivClient
from aioarxiv.utils import logger


async def func():
    async with ArxivClient() as client:
        result = await client.search("ai", max_results=100)
        logger.info(f"Total results: {result.total_result}")
```

## Configuration

You can configure the client by passing an instance of `ArxivConfig` to the `ArxivClient` constructor.
Configuration in Dotenv file is also one of the options, it will automatically load the configuration from the
environment variables.

```python
from aioarxiv.config import ArxivConfig

config = ArxivConfig(
    proxy="http://127.0.0.1:10808",
    log_level="DEBUG",
    page_size=10,
)
```

## Requirements

* Python 3.9 or higher

## License

[MIT License (c) 2025 BalconyJH ](LICENSE)

## Links

* [Documentation](https://balconyjh.github.io/aioarxiv/starter.html)
* [ArXiv API](https://info.arxiv.org/help/api/index.html)