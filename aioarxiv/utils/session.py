import asyncio
from contextlib import nullcontext
import ssl
from types import TracebackType
from typing import Any
from typing_extensions import Self

from aiohttp import (
    ClientResponse,
    ClientSession,
    ClientTimeout,
    TCPConnector,
    TraceConfig,
)
from aiolimiter import AsyncLimiter
import certifi

from aioarxiv.config import ArxivConfig, default_config
from aioarxiv.utils import create_trace_config

from .log import logger


class SessionManager:
    """A session manager that handles HTTP requests with rate limiting and connection
    management.

    Every request issued through :meth:`request` passes two gates, in order:

    1. An ``asyncio.Semaphore`` bounding the number of in-flight requests to
       ``max_concurrent_requests``. It is held for the whole request, so it
       genuinely caps concurrency.
    2. An ``aiolimiter.AsyncLimiter`` enforcing a strict spacing of
       ``rate_limit_period / rate_limit_calls`` seconds between request starts
       (the first request is immediate). With the default configuration
       (1 call / 3 s) this matches the arXiv API Terms of Use.

    The semaphore is acquired first so a task claims a concurrency slot before
    consuming a rate slot; otherwise a task could pass the rate gate and then
    sit blocked on the concurrency gate, wasting its interval.

    Args:
        config (Optional[ArxivConfig]): Configuration for arXiv API and rate limiting.
            Defaults to default_config.
        session (Optional[ClientSession]): An existing aiohttp session to use.
            Defaults to None.
        trace_config (Optional[TraceConfig]): Configuration for request tracing.
            Defaults to None.

    Usage:
        ```python
        # Basic usage with default configuration
        async with SessionManager() as manager:
            response = await manager.request("GET", "http://api.example.com/data")
            data = await response.json()

        # Custom configuration with rate limiting
        config = ArxivConfig(
            rate_limit_calls=5,
            rate_limit_period=1.0,
            timeout=30.0,
            proxy="http://proxy.example.com",
        )

        async with SessionManager(config=config) as manager:
            # Makes rate-limited requests
            responses = await asyncio.gather(*(
                manager.request("GET", f"http://api.example.com/item/{i}")
                for i in range(10)
            ))
        ```
    """

    def __init__(
        self,
        config: ArxivConfig | None = None,
        session: ClientSession | None = None,
        trace_config: TraceConfig | None = None,
    ) -> None:
        """Initialize the session manager.

        Args:
            config (Optional[ArxivConfig]): arXiv API configuration object.
                Defaults to default_config.
            session (Optional[ClientSession]): Existing aiohttp session to use.
                Defaults to None.
            trace_config (Optional[TraceConfig]): Request tracing configuration.
                Defaults to None.
        """
        self._config = config or default_config
        self._timeout = ClientTimeout(total=self._config.timeout)
        self._session = session
        self._trace_config = trace_config or create_trace_config()
        self._semaphore = asyncio.Semaphore(self._config.max_concurrent_requests)
        self._limiter = self._create_limiter(self._config)

    @staticmethod
    def _create_limiter(config: ArxivConfig) -> AsyncLimiter | None:
        """Build the rate limiter gate from configuration.

        Args:
            config (ArxivConfig): Source of ``rate_limit_calls`` and
                ``rate_limit_period``.

        Returns:
            Optional[AsyncLimiter]: A strict-spacing limiter, or None when rate
            limiting is disabled.

        Note:
            ``rate_limit_calls <= 0`` or ``rate_limit_period <= 0`` cannot
            express a meaningful rate (the spacing ``period / calls`` would be
            zero or undefined), so such configurations disable rate limiting
            entirely and requests are gated only by the concurrency semaphore.

            ``AsyncLimiter(1, spacing)`` is aiolimiter's documented no-burst
            configuration: the first acquisition is immediate and subsequent
            ones are spaced by exactly ``spacing`` seconds. Normalizing the
            spacing to ``period / calls`` keeps a steady pace for any
            calls/period pair instead of allowing an initial burst of ``calls``
            requests.
        """
        if config.rate_limit_calls <= 0 or config.rate_limit_period <= 0:
            return None
        return AsyncLimiter(1, config.rate_limit_period / config.rate_limit_calls)

    async def _get_session(self) -> ClientSession:
        """Get or create an aiohttp session.

        Returns:
            ClientSession: The active aiohttp session.

        Note:
            Creates a new session if one doesn't exist or if the existing
            session is closed.
        """
        if self._session is None or self._session.closed:
            self._session = ClientSession(
                timeout=self._timeout,
                trace_configs=[self._trace_config],
                connector=TCPConnector(
                    ssl=ssl.create_default_context(cafile=certifi.where())
                ),
            )
        return self._session

    async def request(self, method: str, url: str, **kwargs: Any) -> ClientResponse:
        """Send a rate-limited HTTP request.

        Args:
            method (str): HTTP method to use (e.g., 'GET', 'POST').
            url (str): Target URL for the request.
            **kwargs: Additional arguments to pass to session.request.

        Returns:
            ClientResponse: The aiohttp response object.

        Raises:
            aiohttp.ClientError: If the request fails.
        """
        if self._config.proxy:
            logger.debug(
                "Using proxy for request",
                extra={"proxy": self._config.proxy, "url": url},
            )
            kwargs["proxy"] = self._config.proxy

        rate_gate = nullcontext() if self._limiter is None else self._limiter
        async with self._semaphore, rate_gate:
            session = await self._get_session()
            return await session.request(method, url, **kwargs)

    async def close(self) -> None:
        """Close the session and cleanup resources.

        This method ensures that the underlying aiohttp session is properly closed
        and resources are released.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> Self:
        """Enter the session manager context.

        Returns:
            Self: The session manager instance.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the session manager context and cleanup resources.

        Args:
            exc_type: Exception type if an error occurred.
            exc_val: Exception value if an error occurred.
            exc_tb: Exception traceback if an error occurred.
        """
        await self.close()
