import asyncio

import pytest

from src.aioarxiv.utils.rate_limiter import RateLimiter


@pytest.fixture
def rate_limiter():
    return RateLimiter(calls=3, period=1.0)


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_within_limit(self, rate_limiter):
        """测试在限制范围内获取许可"""
        for _ in range(rate_limiter.calls):
            await rate_limiter.acquire()
        assert await rate_limiter.get_timestamp_count() == rate_limiter.calls

    @pytest.mark.asyncio
    async def test_acquire_exceeds_limit(self, rate_limiter):
        """测试超出限制时的等待"""
        start_time = asyncio.get_event_loop().time()

        for _ in range(rate_limiter.calls):
            await rate_limiter.acquire()

        await rate_limiter.acquire()

        elapsed = asyncio.get_event_loop().time() - start_time
        assert elapsed >= rate_limiter.period

    @pytest.mark.asyncio
    async def test_state(self, rate_limiter):
        """测试速率限制状态"""
        state = await rate_limiter.state
        assert state.remaining == rate_limiter.calls

        await rate_limiter.acquire()
        state = await rate_limiter.state
        assert state.remaining == rate_limiter.calls - 1

    @pytest.mark.asyncio
    async def test_context_manager(self, rate_limiter):
        """测试上下文管理器"""
        async with rate_limiter as limiter:
            assert isinstance(limiter, RateLimiter)
            assert await rate_limiter.get_timestamp_count() == 1

    @pytest.mark.asyncio
    async def test_window_sliding(self, rate_limiter):
        """测试时间窗口滑动"""
        for _ in range(rate_limiter.calls):
            await rate_limiter.acquire()

        await asyncio.sleep(rate_limiter.period)

        start = asyncio.get_event_loop().time()
        await rate_limiter.acquire()
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_is_limited(self, rate_limiter):
        """测试是否处于限制状态"""
        assert not await rate_limiter.is_limited

        for _ in range(rate_limiter.calls):
            await rate_limiter.acquire()
        assert await rate_limiter.is_limited

        await asyncio.sleep(rate_limiter.period)
        assert not await rate_limiter.is_limited
