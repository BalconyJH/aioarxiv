from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ArxivConfig(BaseSettings):
    """arXiv API 配置类"""

    base_url: str = Field(
        default="http://export.arxiv.org/api/query", description="arXiv API 基础URL"
    )
    timeout: float = Field(default=30.0, description="请求超时时间(秒)", gt=0)
    max_retries: int = Field(default=3, description="最大重试次数", ge=0)
    rate_limit_calls: int = Field(
        default=5, description="速率限制窗口内的最大请求数", ge=0
    )
    rate_limit_period: float = Field(
        default=1.0, description="速率限制窗口期(秒)", ge=0
    )
    max_concurrent_requests: int = Field(default=5, description="最大并发请求数")
    proxy: Optional[str] = Field(default=None, description="HTTP/HTTPS代理URL")
    log_level: str = Field(default="INFO", description="日志等级")
    page_size: int = Field(default=20, description="每页结果数")
    min_wait: float = Field(default=1.0, description="最小重试等待时间(秒)", gt=0)

    model_config = SettingsConfigDict(
        env_prefix="ARXIV_",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_file=".env",
        extra="allow",
    )


default_config = ArxivConfig()
