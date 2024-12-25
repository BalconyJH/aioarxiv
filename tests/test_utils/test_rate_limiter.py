import asyncio
from time import time
from typing import NoReturn
from unittest.mock import patch

import pytest

from aioarxiv.utils.rate_limiter import RateLimiter


@pytest.fixture
def rate_limiter():
    # 重置类级别状态
    RateLimiter.timestamps.clear()
    RateLimiter._calls = 5
    RateLimiter._period = 1.0
    return RateLimiter


@pytest.fixture(autouse=True)
async def _setup_limiter():
    """设置和清理限制器状态"""
    RateLimiter.timestamps.clear()
    RateLimiter._calls = 0
    RateLimiter._period = 0.0
    RateLimiter._lock = asyncio.Lock()
    RateLimiter._semaphore = asyncio.Semaphore(1)
    yield
    # 清理
    RateLimiter.timestamps.clear()


@pytest.mark.asyncio
async def test_basic_rate_limiting(rate_limiter) -> None:
    """测试基本的速率限制功能"""
    calls = []

    @rate_limiter.limit(calls=2, period=1.0)
    async def test_func():
        calls.append(time())
        return len(calls)

    results = await asyncio.gather(test_func(), test_func(), test_func())

    assert results == [1, 2, 3]
    assert len(calls) == 3
    assert calls[1] - calls[0] < 1.0
    assert calls[2] - calls[1] >= 1.0


@pytest.mark.asyncio
async def test_concurrent_requests(rate_limiter) -> None:
    """测试并发请求控制"""
    concurrent_count = 0
    max_concurrent = 0

    @rate_limiter.limit(calls=3)
    async def test_func():
        nonlocal concurrent_count, max_concurrent
        concurrent_count += 1
        max_concurrent = max(max_concurrent, concurrent_count)
        await asyncio.sleep(0.1)
        concurrent_count -= 1
        return concurrent_count

    tasks = [test_func() for _ in range(10)]
    await asyncio.gather(*tasks)

    assert max_concurrent <= 3


@pytest.mark.asyncio
async def test_window_sliding(rate_limiter) -> None:
    """测试时间窗口滑动"""
    calls = []

    @rate_limiter.limit(calls=2, period=1.0)
    async def test_func():
        calls.append(time())
        return len(calls)

    with patch("asyncio.sleep") as mock_sleep:
        # 模拟时间流逝
        mock_sleep.side_effect = lambda _: None

        await test_func()
        await test_func()

        await test_func()

        mock_sleep.assert_called_once()
        args = mock_sleep.call_args[0]
        assert 0 < args[0] <= 1.0


@pytest.mark.asyncio
async def test_error_handling(rate_limiter) -> None:
    """测试错误处理"""

    @rate_limiter.limit(calls=1)
    async def failing_func() -> NoReturn:
        msg = "Test error"
        raise ValueError(msg)

    with pytest.raises(ValueError, match="Test error"):
        await failing_func()

    assert len(RateLimiter.timestamps) == 1


@pytest.mark.asyncio
async def test_state_sharing() -> None:
    """测试多个装饰器实例共享状态"""
    calls_a = []
    calls_b = []

    @RateLimiter.limit(calls=2, period=1.0)
    async def func_a() -> None:
        calls_a.append(time())
        await asyncio.sleep(0.1)

    @RateLimiter.limit(calls=2, period=1.0)
    async def func_b() -> None:
        calls_b.append(time())
        await asyncio.sleep(0.1)

    await func_a()
    await func_b()
    await asyncio.sleep(1.1)
    await func_a()
    await func_b()

    assert len(calls_a) == 2
    assert len(calls_b) == 2
    timestamps = sorted(calls_a + calls_b)
    assert timestamps[2] - timestamps[0] >= 1.0
