import asyncio
import functools
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Optional, TypeVar, cast

from ..config import default_config
from .log import logger

T = TypeVar("T", bound=Callable[..., Any])


@dataclass
class RateLimitState:
    """速率限制状态

    Attributes:
        remaining: 剩余可用请求数
        reset_at: 下次重置时间
        window_start: 当前窗口开始时间
    """

    remaining: int
    reset_at: float
    window_start: float


class RateLimiter:
    """速率限制装饰器，使用类级别共享状态实现请求限流

    使用类级别变量确保所有实例共享同一个限流状态。支持并发控制和时间窗口限流。

    Attributes:
        timestamps: 请求时间戳队列
        _lock: 用于保护共享状态的锁
        _semaphore: 控制并发请求数的信号量
        _calls: 时间窗口内允许的最大请求数
        _period: 时间窗口大小(秒)
    """

    timestamps: ClassVar[deque[float]] = deque()
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _semaphore: ClassVar[asyncio.Semaphore] = asyncio.Semaphore(1)
    _calls: ClassVar[int] = 0
    _period: ClassVar[float] = 0.0

    @classmethod
    def _clean_expired(cls, now: float) -> None:
        """清理过期的时间戳

        Args:
            now: 当前时间戳
        """
        cutoff = now - cls._period
        while cls.timestamps and cls.timestamps[0] <= cutoff:
            cls.timestamps.popleft()

    @classmethod
    async def _wait_if_needed(cls, now: float) -> float:
        """根据需要等待并返回新的当前时间

        Args:
            now: 当前时间戳

        Returns:
            float: 等待后的新时间戳
        """
        if len(cls.timestamps) >= cls._calls:
            wait_time = cls.timestamps[0] + cls._period - now
            if wait_time > 0:
                logger.debug(
                    f"触发速率限制，等待{wait_time:.2f}秒",
                    extra={
                        "wait_time": f"{wait_time:.2f}s",
                        "current_calls": len(cls.timestamps),
                        "max_calls": cls._calls,
                        "period": cls._period,
                    },
                )
                await asyncio.sleep(wait_time)
                return asyncio.get_event_loop().time()
        return now

    @classmethod
    def limit(
        cls, calls: Optional[int] = None, period: Optional[float] = None
    ) -> Callable[[T], T]:
        """创建速率限制装饰器

        Args:
            calls: 时间窗口内最大请求数，默认使用配置值
            period: 时间窗口大小(秒)，默认使用配置值

        Returns:
            装饰器函数
        """
        cls._calls = calls or default_config.rate_limit_calls
        cls._period = period or default_config.rate_limit_period
        cls.timestamps = deque(maxlen=cls._calls)
        cls._semaphore = asyncio.Semaphore(cls._calls)

        def decorator(func: T) -> T:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                async with cls._semaphore, cls._lock:
                    now = asyncio.get_event_loop().time()
                    cls._clean_expired(now)
                    now = await cls._wait_if_needed(now)
                    cls.timestamps.append(now)

                    logger.debug(
                        "请求通过限制器",
                        extra={
                            "current_calls": len(cls.timestamps),
                            "max_calls": cls._calls,
                            "remaining": cls._calls - len(cls.timestamps),
                        },
                    )

                return await func(*args, **kwargs)

            return cast(T, wrapper)

        return decorator
