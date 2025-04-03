from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ArxivConfig(BaseSettings):
    """Configuration class for arXiv API.

    This class manages configuration settings for interacting with the arXiv API,
    including network settings, rate limiting, and other operational parameters.

    Attributes:
        base_url (str): Base URL for arXiv API endpoints.
        timeout (float): Request timeout in seconds.
        timezone (str): Timezone for timestamp operations.
        max_retries (int): Maximum number of retry attempts for failed requests.
        rate_limit_calls (int): Maximum number of requests within the rate limit window.
        rate_limit_period (float): Rate limit window period in seconds.
        max_concurrent_requests (int): Maximum number of concurrent requests.
        proxy (Optional[str]): HTTP/HTTPS proxy URL.
        log_level (str): Logging level for the application.
        page_size (int): Number of results per page.
        min_wait (float): Minimum wait time between retries in seconds.
    """

    base_url: str = Field(
        default="http://export.arxiv.org/api/query",
        description="Base URL for arXiv API endpoints",
    )
    timeout: float = Field(default=30.0, description="Request timeout in seconds", gt=0)
    timezone: str = Field(
        default="Asia/Shanghai", description="Timezone for operations"
    )
    max_retries: int = Field(
        default=3, description="Maximum number of retry attempts", ge=0
    )
    rate_limit_calls: int = Field(
        default=1,
        description="Maximum requests within rate limit window",
        ge=0,
    )
    rate_limit_period: float = Field(
        default=3.0,
        description="Rate limit window period in seconds",
        ge=0,
    )
    max_concurrent_requests: int = Field(
        default=1, description="Maximum number of concurrent requests"
    )
    proxy: Optional[str] = Field(default=None, description="HTTP/HTTPS proxy URL")
    log_level: str = Field(default="INFO", description="Application logging level")
    page_size: int = Field(default=1000, description="Results per page")
    min_wait: float = Field(
        default=3.0, description="Minimum retry wait time in seconds", gt=0
    )

    model_config = SettingsConfigDict(
        env_prefix="ARXIV_",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_file=".env",
        extra="allow",
    )


default_config = ArxivConfig()
