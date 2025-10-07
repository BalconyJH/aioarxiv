import ssl
from types import TracebackType
from typing import Optional
from typing_extensions import Self

from aiohttp import (
    ClientResponse,
    ClientSession,
    ClientTimeout,
    TCPConnector,
    TraceConfig,
)
import certifi

from aioarxiv.config import ArxivConfig, default_config
from aioarxiv.utils import create_trace_config

from .log import logger
from .rate_limiter import RateLimiter


class SessionManager:
    """A session manager that handles HTTP requests with rate limiting and connection
    management.

    This class provides a convenient way to manage HTTP sessions with built-in rate
    limiting, timeout configuration, and proxy support. It ensures proper resource
    cleanup and provides an async context manager interface.

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
        async with SessionManager() as session:
            response = await session.request('GET', 'http://api.example.com/data')
            data = await response.json()

        # Custom configuration with rate limiting
        config = ArxivConfig(
            rate_limit_calls=5,
            rate_limit_period=1.0,
            timeout=30.0,
            proxy='http://proxy.example.com'
        )

        async with SessionManager(config=config) as session:
            # Makes rate-limited requests
            responses = await asyncio.gather(*(
                session.request('GET', f'http://api.example.com/item/{i}')
                for i in range(10)
            ))

        # Error handling
        async with SessionManager() as session:
            try:
                response = await session.request('GET', 'http://api.example.com/data')
                if response.status == 429:  # Too Many Requests
                    logger.warning("Rate limit exceeded")
            except Exception as e:
                logger.error(f"Request failed: {e}")
        ```
    """

    def __init__(
        self,
        config: Optional[ArxivConfig] = None,
        session: Optional[ClientSession] = None,
        trace_config: Optional[TraceConfig] = None,
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
        self._rate_limiter = RateLimiter(
            calls=self._config.rate_limit_calls,
            period=self._config.rate_limit_period,
        )

    @property
    async def session(self) -> ClientSession:
        """Get or create an aiohttp session.

        Returns:
            ClientSession: The active aiohttp session.

        Note:
            Creates a new session if one doesn't exist or if the existing session is
            closed.
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

    @property
    def rate_limiter(self) -> RateLimiter:
        """Get the rate limiter instance.

        Returns:
            RateLimiter: The rate limiter configured for this session.
        """
        return self._rate_limiter

    async def request(self, method: str, url: str, **kwargs) -> ClientResponse:
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

        @self._rate_limiter.limit()
        async def _rate_limited_request() -> ClientResponse:
            if self._config.proxy:
                logger.debug(
                    "Using proxy for request",
                    extra={"proxy": self._config.proxy, "url": url},
                )
                kwargs["proxy"] = self._config.proxy

            client = await self.session
            return await client.request(method, url, **kwargs)

        return await _rate_limited_request()

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
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Exit the session manager context and cleanup resources.

        Args:
            exc_type: Exception type if an error occurred.
            exc_val: Exception value if an error occurred.
            exc_tb: Exception traceback if an error occurred.
        """
        await self.close()
