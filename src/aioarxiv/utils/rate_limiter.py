import asyncio
from dataclasses import dataclass
from types import TracebackType
from typing import Optional

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
        calls: 窗口期内的最大请求数
        period: 窗口期 (秒)
        __timestamps: 请求时间戳列表
        __lock: 速率限制器锁
    """

    def __init__(self, calls: Optional[int] = None, period: Optional[float] = None):
        """
        初始化速率限制器

        Args:
            calls: 窗口期内的最大请求数，默认从配置获取
            period: 窗口期，默认从配置获取
        """
        self.calls = calls or default_config.rate_limit_calls
        self.period = period or default_config.rate_limit_period
        self.__timestamps: list[float] = []
        self.__lock = asyncio.Lock()

    @property
    async def is_limited(self) -> bool:
        """当前是否处于限制状态"""
        # 使用当前时间作为参考点
        async with self.__lock:
            now = asyncio.get_event_loop().time()
            valid_stamps = self._get_valid_timestamps(now)
            self.__timestamps = valid_stamps
            return len(valid_stamps) >= self.calls

    def _get_valid_timestamps(self, now: float) -> list[float]:
        """获取有效的时间戳列表"""
        return [t for t in self.__timestamps if now - t < self.period]

    @property
    async def state(self) -> RateLimitState:
        """获取当前速率限制状态"""
        async with self.__lock:
            now = asyncio.get_event_loop().time()
            valid_timestamps = self._get_valid_timestamps(now)
            self.__timestamps = valid_timestamps

            return RateLimitState(
                remaining=max(0, self.calls - len(valid_timestamps)),
                reset_at=min(valid_timestamps, default=now) + self.period
                if self.__timestamps
                else now,
                window_start=now,
            )

    async def acquire(self) -> None:
        """获取访问许可"""
        async with self.__lock:
            now = asyncio.get_event_loop().time()
            valid_stamps = self._get_valid_timestamps(now)
            self.__timestamps = valid_stamps

            if len(valid_stamps) >= self.calls:
                sleep_time = valid_stamps[0] + self.period - now
                if sleep_time > 0:
                    logger.debug(
                        "触发速率限制",
                        extra={
                            "wait_time": f"{sleep_time:.2f}s",
                            "current_calls": len(valid_stamps),
                            "max_calls": self.calls,
                        },
                    )
                    await asyncio.sleep(sleep_time)

            self.__timestamps.append(asyncio.get_event_loop().time())

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
