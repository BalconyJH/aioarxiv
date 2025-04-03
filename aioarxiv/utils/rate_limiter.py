import asyncio
from collections import deque
from dataclasses import dataclass
import functools
from typing import Any, Callable, TypeVar, cast

from .log import logger

T = TypeVar("T", bound=Callable[..., Any])


@dataclass
class RateLimitState:
    """Data class to represent the current rate limit state.

    Args:
        remaining (int): The number of remaining allowed requests in this window.
        reset_at (float): The timestamp (epoch) when the rate-limit window resets.
        window_start (float): The timestamp (epoch) when the current window starts.
    """

    remaining: int
    reset_at: float
    window_start: float


class RateLimiter:
    """A rate limiter that restricts the number of requests within a given time window
    and controls concurrent requests with a semaphore.

    This class uses instance-level locks and semaphores, ensuring each RateLimiter
    instance can manage its own concurrency and request timestamps without
    interfering with other instances or event loops.

    Args:
        calls (int): The maximum number of allowed requests in one time window.
        period (float): The time window length in seconds.

    Usage:
        ```python
        # Create a rate limiter allowing 3 calls every 10 seconds
        limiter = RateLimiter(calls=3, period=10.0)

        # Decorate your async function
        @limiter.limit()
        async def fetch_data(url: str) -> str:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    return await response.text()

        # Use in concurrent operations
        urls = ["http://example.com/1", "http://example.com/2", "http://example.com/3"]
        results = await asyncio.gather(*(fetch_data(url) for url in urls))

        # Use with custom error handling
        async def fetch_with_retry():
            try:
                return await fetch_data("http://example.com")
            except Exception as e:
                logger.error(f"Failed to fetch: {e}")
                return None
        ```
    """

    def __init__(self, calls: int, period: float):
        """Initialize the RateLimiter.

        Args:
            calls (int): The maximum number of allowed requests in one time window.
            period (float): The time window length in seconds.
        """
        self._calls: int = calls
        self._period: float = period
        self._timestamps: deque[float] = deque(maxlen=calls)
        self._lock: asyncio.Lock = asyncio.Lock()
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(calls)

    def _clean_expired(self, now: float) -> None:
        """Remove timestamps that are outside the current rate limit window.

        Args:
            now (float): The current time (epoch).
        """
        cutoff = now - self._period
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.popleft()

    async def _wait_if_needed(self, now: float) -> float:
        """If rate limit is reached, block until a request slot is free.

        Args:
            now (float): The current time (epoch).

        Returns:
            float: Updated current time (after waiting, if needed).
        """
        if len(self._timestamps) >= self._calls:
            wait_time = self._timestamps[0] + self._period - now
            if wait_time > 0:
                logger.debug(
                    f"Rate limit reached, waiting for {wait_time:.2f}s",
                    extra={
                        "wait_time": f"{wait_time:.2f}s",
                        "current_calls": len(self._timestamps),
                        "max_calls": self._calls,
                        "period": self._period,
                    },
                )
                await asyncio.sleep(wait_time)
                # After sleeping, the "now" might have changed
                return asyncio.get_event_loop().time()
        return now

    def limit(self) -> Callable[[T], T]:
        """Decorator for rate limiting an async function.

        This decorator ensures that:
        1. Concurrency does not exceed `calls`
        2. Requests are limited to `calls` within `period` seconds

        Returns:
            Callable[[T], T]: A decorator that wraps the original async function.

        Usage:
            ```python
            limiter = RateLimiter(calls=5, period=1.0)

            @limiter.limit()
            async def api_call(endpoint: str) -> dict:
                async with aiohttp.ClientSession() as session:
                    async with session.get(endpoint) as response:
                        return await response.json()

            # The decorated function will automatically respect rate limits
            result = await api_call("https://api.example.com/data")
            ```
        """

        def decorator(func: T) -> T:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                # Acquire semaphore and lock to limit concurrency and ensure timestamp
                # checks are atomic
                async with self._semaphore, self._lock:
                    now = asyncio.get_event_loop().time()
                    self._clean_expired(now)
                    now = await self._wait_if_needed(now)
                    self._timestamps.append(now)

                    logger.debug(
                        "Request rate limit invoked",
                        extra={
                            "current_calls": len(self._timestamps),
                            "max_calls": self._calls,
                            "remaining": self._calls - len(self._timestamps),
                        },
                    )

                # Proceed with the original function call
                return await func(*args, **kwargs)

            return cast("T", wrapper)

        return decorator
