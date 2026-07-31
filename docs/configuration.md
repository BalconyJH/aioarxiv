# Configuration

aioarxiv uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
for configuration. Every setting can be provided through:

- environment variables (with the `ARXIV_` prefix),
- a `.env` file in the working directory,
- direct code configuration via `ArxivConfig`.

All values are validated by Pydantic: types are checked and converted where
possible, constraints (such as minimum values) are enforced, and invalid
configurations fail immediately with a clear error.

=== "Environment variables"

    ```bash
    export ARXIV_TIMEOUT=60.0
    export ARXIV_MAX_RETRIES=5
    export ARXIV_PROXY="http://localhost:8080"
    ```

=== ".env file"

    ```text
    ARXIV_TIMEOUT=60.0
    ARXIV_MAX_RETRIES=5
    ARXIV_PROXY=http://localhost:8080
    ```

=== "Python code"

    ```python
    from aioarxiv import ArxivConfig

    config = ArxivConfig(
        timeout=60.0,
        max_retries=5,
        proxy="http://localhost:8080",
    )
    ```

Pass the configuration object to the client:

```python
from aioarxiv import ArxivClient, ArxivConfig


async def main() -> None:
    config = ArxivConfig(timeout=60.0, max_retries=5)
    async with ArxivClient(config=config) as client:
        result = await client.search("cat:cs.AI", max_results=10)
```

## Fields

| Field | Description | Type | Default | Constraint | Environment variable |
| --- | --- | --- | --- | --- | --- |
| `base_url` | Base URL for the arXiv API | `str` | `https://export.arxiv.org/api/query` | - | `ARXIV_BASE_URL` |
| `timeout` | Request timeout in seconds | `float` | `30.0` | `> 0` | `ARXIV_TIMEOUT` |
| `timezone` | Timezone for timestamp operations | `str` | `Asia/Shanghai` | - | `ARXIV_TIMEZONE` |
| `max_retries` | Maximum retry attempts for failed requests | `int` | `3` | `>= 0` | `ARXIV_MAX_RETRIES` |
| `rate_limit_calls` | Maximum requests within the rate limit window | `int` | `1` | `>= 0` | `ARXIV_RATE_LIMIT_CALLS` |
| `rate_limit_period` | Rate limit window period in seconds | `float` | `3.0` | `>= 0` | `ARXIV_RATE_LIMIT_PERIOD` |
| `max_concurrent_requests` | Maximum number of concurrent requests | `int` | `1` | `>= 1` | `ARXIV_MAX_CONCURRENT_REQUESTS` |
| `proxy` | HTTP/HTTPS proxy URL | `str \| None` | `None` | - | `ARXIV_PROXY` |
| `log_level` | Logging level | `str` | `INFO` | - | `ARXIV_LOG_LEVEL` |
| `page_size` | Number of results fetched per page | `int` | `1000` | `> 0, <= 2000` | `ARXIV_PAGE_SIZE` |
| `min_wait` | Minimum wait time between retries in seconds | `float` | `3.0` | `> 0` | `ARXIV_MIN_WAIT` |

!!! warning "Respect the arXiv rate limit"

    The defaults (`rate_limit_calls=1`, `rate_limit_period=3.0`) match the
    [arXiv API Terms of Use](https://info.arxiv.org/help/api/tou.html): one
    request every three seconds over a single connection. The client logs a
    warning when a configuration averages less than three seconds per request.

## Model settings

The settings model is declared with:

- `env_prefix`: `"ARXIV_"` - prefix for environment variables
- `env_file`: `".env"` - default environment file name
- `env_file_encoding`: `"utf-8"` - encoding for the `.env` file
- `case_sensitive`: `False` - environment variables are case-insensitive
- `extra`: `"allow"` - additional fields are accepted

## Examples

Rate limiting tuned for a mirror you operate yourself:

```python
from aioarxiv import ArxivConfig

config = ArxivConfig(
    rate_limit_calls=2,
    rate_limit_period=5.0,
    max_concurrent_requests=2,
)
```

Proxy with longer timeout:

```python
from aioarxiv import ArxivConfig

config = ArxivConfig(
    proxy="http://proxy.example.com:8080",
    timeout=60.0,
    max_retries=5,
)
```

!!! tip

    Prefer a `.env` file for production deployments; it keeps per-environment
    settings out of code and works with any process manager.
