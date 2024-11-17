import asyncio
from dataclasses import dataclass
from types import TracebackType
from typing import ClassVar, Optional

from ..config import default_config
from .log import logger


@dataclass
class RateLimitState:
    """速率限制状态"""

    remaining: int
    reset_at: float
    window_start: float


class RateLimiter:
    """
    速率限制器

    用于限制请求速率，防止过多请求导致服务器拒绝服务。

    Attributes:
        DEFAULT_CALLS: ClassVar[int]: 默认窗口期内的最大请求数
        DEFAULT_PERIOD: ClassVar[float]: 默认窗口期
        calls: int: 窗口期内的最大请求数
        period: float: 窗口期
        timestamps: list[float]: 请求时间戳列表
        _lock: asyncio.Lock: 锁
        _last_check: Optional[float]: 上次检查时间
        _logger: logging.Logger: 日志记录器
    """

    # 从配置获取默认值
    DEFAULT_CALLS: ClassVar[int] = default_config.rate_limit_calls
    DEFAULT_PERIOD: ClassVar[float] = default_config.rate_limit_period

    def __init__(self, calls: int = DEFAULT_CALLS, period: float = DEFAULT_PERIOD):
        """
        初始化速率限制器

        Args:
            calls: 窗口期内的最大请求数，默认从配置获取
            period: 窗口期，默认从配置获取
        """
        if calls <= 0:
            raise ValueError("calls must be positive")
        if period <= 0:
            raise ValueError("period must be positive")
        self.calls = calls
        self.period = period
        self.timestamps: list[float] = []
        self._lock = asyncio.Lock()
        self._last_check: Optional[float] = None
        self._logger = logger

    @property
    def is_limited(self) -> bool:
        """当前是否处于限制状态"""
        # 使用当前时间作为参考点
        loop = asyncio.get_running_loop()
        now = loop.time()

        # 获取有效时间戳并更新
        valid_stamps = [t for t in self.timestamps if (now - t) < self.period]
        self.timestamps = valid_stamps

        return len(valid_stamps) >= self.calls

    def _get_valid_timestamps(self, now: float) -> list[float]:
        """获取有效的时间戳列表"""
        return [t for t in self.timestamps if now - t <= self.period]

    @property
    async def state(self) -> RateLimitState:
        """获取当前速率限制状态"""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            valid_timestamps = self._get_valid_timestamps(now)

            return RateLimitState(
                remaining=max(0, self.calls - len(valid_timestamps)),
                reset_at=min(self.timestamps, default=now) + self.period
                if self.timestamps
                else now,
                window_start=now,
            )

    async def acquire(self) -> None:
        """获取访问许可"""
        async with self._lock:
            now = asyncio.get_event_loop().time()

            self.timestamps = self._get_valid_timestamps(now)

            # 检查是否需要等待
            if len(self.timestamps) >= self.calls:
                sleep_time = self.timestamps[0] + self.period - now
                if sleep_time > 0:
                    self._logger.debug(
                        "触发速率限制",
                        extra={
                            "wait_time": f"{sleep_time:.2f}s",
                            "current_calls": len(self.timestamps),
                            "max_calls": self.calls,
                        },
                    )
                    await asyncio.sleep(sleep_time)

            self.timestamps.append(now)
            self._last_check = now

            self._logger.debug(
                "获取访问许可",
                extra={
                    "remaining_calls": self.calls - len(self.timestamps),
                    "window_reset_in": f"{(self.timestamps[0] + self.period - now):.2f}s"
                    if self.timestamps
                    else "0s",
                },
            )

    async def __aenter__(self) -> "RateLimiter":
        """进入速率限制上下文"""
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """退出速率限制上下文"""
        pass
