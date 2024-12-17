from typing import TYPE_CHECKING, Optional
from typing_extensions import Self

from aiohttp import ClientResponse, ClientSession, ClientTimeout, TraceConfig

from aioarxiv.config import ArxivConfig, default_config
from aioarxiv.utils import create_trace_config

from .log import logger
from .rate_limiter import RateLimiter

if TYPE_CHECKING:
    from types import TracebackType


class SessionManager:
    def __init__(
        self,
        config: Optional[ArxivConfig] = None,
        session: Optional[ClientSession] = None,
        trace_config: Optional[TraceConfig] = None,
    ):
        """
        初始化会话管理器

        Args:
            config: arXiv API配置对象
            session: aiohttp会话
            trace_config: 请求追踪配置
        """
        self._config = config or default_config
        self._timeout = ClientTimeout(
            total=self._config.timeout,
        )
        self._session = session
        self._trace_config = trace_config or create_trace_config()

    @property
    async def session(self) -> ClientSession:
        """
        获取或创建会话

        Returns:
            ClientSession: aiohttp会话
        """
        if self._session is None or self._session.closed:
            self._session = ClientSession(
                timeout=self._timeout,
                trace_configs=[self._trace_config],
            )
        return self._session

    @RateLimiter.limit()
    async def request(self, method: str, url: str, **kwargs) -> ClientResponse:
        """
        发送受速率限制的请求

        Args:
            method: HTTP方法
            url: 请求URL
            **kwargs: 传递给session.request的额外参数

        Returns:
            ClientResponse: aiohttp响应对象
        """
        if self._config.proxy:
            logger.trace(f"使用代理: {self._config.proxy}")
            kwargs["proxy"] = self._config.proxy

        async with await self.session as client:
            return await client.request(method, url, **kwargs)

    async def close(self) -> None:
        """关闭会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> Self:
        """
        进入会话管理器

        Returns:
            SessionManager: 会话管理器实例
        """
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """
        退出会话管理器

        Args:
            exc_type: 异常类型
            exc_val: 异常值
            exc_tb: 异常回溯
        """
        await self.close()
