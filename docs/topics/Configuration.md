# Configuration

## Configuration Overview

aioarxiv uses `pydantic_settings` for configuration management. All settings can be configured through:

- Environment variables (with `ARXIV_` prefix)
- `.env` file
- Direct code configuration

<note>
All configuration values are validated through Pydantic's type checking system, ensuring:
- Type safety for all settings
- Automatic type conversion where possible
- Validation of constraints (e.g., minimum values)
- Immediate error reporting for invalid configurations
</note>

<tabs>
    <tab title="Environment Variables">
        <code-block lang="bash">
            export ARXIV_BASE_URL="http://export.arxiv.org/api/query"
            export ARXIV_TIMEOUT=30.0
            export ARXIV_TIMEZONE="Asia/Shanghai"
        </code-block>
    </tab>
    <tab title=".env File">
        <code-block lang="text">
            ARXIV_BASE_URL=http://export.arxiv.org/api/query
            ARXIV_TIMEOUT=30.0
            ARXIV_TIMEZONE=Asia/Shanghai
        </code-block>
    </tab>
    <tab title="Python Code">
        <code-block lang="python">
            from aioarxiv import ArxivConfig
            config = ArxivConfig(
                base_url="http://export.arxiv.org/api/query",
                timeout=30.0,
                timezone="Asia/Shanghai"
            )
        </code-block>
    </tab>
</tabs>

## Configuration Model Settings

The configuration model uses the following settings:

- `env_prefix`: "ARXIV_" (prefix for environment variables)
- `env_file_encoding`: "utf-8" (encoding for .env file)
- `case_sensitive`: False (case-insensitive environment variables)
- `env_file`: ".env" (default environment file name)
- `extra`: "allow" (allows additional configuration fields)

## Configuration Details

<table>
    <tr>
        <th>Parameter</th>
        <th>Description</th>
        <th>Type</th>
        <th>Default</th>
        <th>Constraint</th>
        <th>Environment Variable</th>
    </tr>
    <tr>
        <td>base_url</td>
        <td>Base URL for the arXiv API</td>
        <td>string</td>
        <td><code>http://export.arxiv.org/api/query</code></td>
        <td>-</td>
        <td><code>ARXIV_BASE_URL</code></td>
    </tr>
    <tr>
        <td>timeout</td>
        <td>API request timeout in seconds</td>
        <td>float</td>
        <td><code>30.0</code></td>
        <td>gt=0 (greater than 0)</td>
        <td><code>ARXIV_TIMEOUT</code></td>
    </tr>
    <tr>
        <td>timezone</td>
        <td>Timezone setting</td>
        <td>string</td>
        <td><code>Asia/Shanghai</code></td>
        <td>-</td>
        <td><code>ARXIV_TIMEZONE</code></td>
    </tr>
    <tr>
        <td>max_retries</td>
        <td>Maximum number of retry attempts for failed requests</td>
        <td>integer</td>
        <td><code>3</code></td>
        <td>ge=0 (greater than or equal to 0)</td>
        <td><code>ARXIV_MAX_RETRIES</code></td>
    </tr>
    <tr>
        <td>rate_limit_calls</td>
        <td>Maximum number of requests within the rate limit window</td>
        <td>integer</td>
        <td><code>1</code></td>
        <td>ge=0 (greater than or equal to 0)</td>
        <td><code>ARXIV_RATE_LIMIT_CALLS</code></td>
    </tr>
    <tr>
        <td>rate_limit_period</td>
        <td>Rate limit window period in seconds</td>
        <td>float</td>
        <td><code>3.0</code></td>
        <td>ge=0 (greater than or equal to 0)</td>
        <td><code>ARXIV_RATE_LIMIT_PERIOD</code></td>
    </tr>
    <tr>
        <td>max_concurrent_requests</td>
        <td>Maximum number of concurrent requests</td>
        <td>integer</td>
        <td><code>1</code></td>
        <td>-</td>
        <td><code>ARXIV_MAX_CONCURRENT_REQUESTS</code></td>
    </tr>
    <tr>
        <td>proxy</td>
        <td>HTTP/HTTPS proxy URL</td>
        <td>string | None</td>
        <td><code>None</code></td>
        <td>-</td>
        <td><code>ARXIV_PROXY</code></td>
    </tr>
    <tr>
        <td>log_level</td>
        <td>Logging level</td>
        <td>string</td>
        <td><code>INFO</code></td>
        <td>-</td>
        <td><code>ARXIV_LOG_LEVEL</code></td>
    </tr>
    <tr>
        <td>page_size</td>
        <td>Number of results per page</td>
        <td>integer</td>
        <td><code>1000</code></td>
        <td>-</td>
        <td><code>ARXIV_PAGE_SIZE</code></td>
    </tr>
    <tr>
        <td>min_wait</td>
        <td>Minimum wait time between retries in seconds</td>
        <td>float</td>
        <td><code>3.0</code></td>
        <td>gt=0 (greater than 0)</td>
        <td><code>ARXIV_MIN_WAIT</code></td>
    </tr>
</table>

## Configuration Examples

<list>
<li>Basic Configuration:
    <code-block lang="python">
        from aioarxiv import ArxivConfig
        config = ArxivConfig(
            timeout=60.0,
            max_retries=5,
            log_level="DEBUG"
        )
    </code-block>
</li>

<li>Proxy Configuration:
    <code-block lang="python">
        from aioarxiv import ArxivConfig
        config = ArxivConfig(
            proxy="http://localhost:8080",
            timeout=60.0,
            max_retries=5
        )
    </code-block>
</li>

<li>Rate Limiting:
    <code-block lang="python">
        from aioarxiv import ArxivConfig
        config = ArxivConfig(
            rate_limit_calls=2,
            rate_limit_period=5.0,
            max_concurrent_requests=2
        )
    </code-block>
</li>
</list>

<p>The configuration object can be passed to the client instance:</p>

<code-block lang="python">
from aioarxiv import ArxivClient, ArxivConfig

config = ArxivConfig(timeout=60.0, max_retries=5)
client = ArxivClient(config=config)
</code-block>

<note>All configuration items can be overridden using environment variables. The environment variable names are the uppercase version of the configuration items with an <code>ARXIV_</code> prefix.</note>

<tip>
It's recommended to use a <code>.env</code> file for managing configurations in production environments, making it easier to manage different environment settings.
</tip>