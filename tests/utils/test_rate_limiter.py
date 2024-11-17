import asyncio

import pytest

from src.aioarxiv.utils.rate_limiter import RateLimiter


@pytest.fixture
def rate_limiter():
    return RateLimiter(calls=3, period=1.0)


class TestRateLimiter:
    def test_init_with_invalid_params(self):
        """测试无效的初始化参数"""
        with pytest.raises(ValueError, match="calls must be positive"):
            RateLimiter(calls=0)

        with pytest.raises(ValueError, match="period must be positive"):
            RateLimiter(period=0)

    @pytest.mark.asyncio
    async def test_acquire_within_limit(self, rate_limiter):
        """测试在限制范围内获取许可"""
        for _ in range(rate_limiter.calls):
            await rate_limiter.acquire()
        assert len(rate_limiter.timestamps) == rate_limiter.calls

    @pytest.mark.asyncio
    async def test_acquire_exceeds_limit(self, rate_limiter):
        """测试超出限制时的等待"""
        start_time = asyncio.get_event_loop().time()

        # 先用完配额
        for _ in range(rate_limiter.calls):
            await rate_limiter.acquire()

        # 下一次请求应该等待
        await rate_limiter.acquire()

        elapsed = asyncio.get_event_loop().time() - start_time
        assert elapsed >= rate_limiter.period

    @pytest.mark.asyncio
    async def test_state(self, rate_limiter):
        """测试速率限制状态"""
        # 初始状态
        state = await rate_limiter.state
        assert state.remaining == rate_limiter.calls

        # 使用一个许可后的状态
        await rate_limiter.acquire()
        state = await rate_limiter.state
        assert state.remaining == rate_limiter.calls - 1

    @pytest.mark.asyncio
    async def test_context_manager(self, rate_limiter):
        """测试上下文管理器"""
        async with rate_limiter as limiter:
            assert isinstance(limiter, RateLimiter)
            assert len(limiter.timestamps) == 1

    @pytest.mark.asyncio
    async def test_window_sliding(self, rate_limiter):
        """测试时间窗口滑动"""
        # 填满时间窗口
        for _ in range(rate_limiter.calls):
            await rate_limiter.acquire()

        # 等待窗口滑动
        await asyncio.sleep(rate_limiter.period)

        # 应该可以立即获取新的许可
        start = asyncio.get_event_loop().time()
        await rate_limiter.acquire()
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 0.1  # 不应该有明显延迟

    @pytest.mark.asyncio
    async def test_is_limited(self, rate_limiter):
        """测试是否处于限制状态"""
        # 初始状态未受限
        assert not rate_limiter.is_limited

        # 填满时间窗口
        for _ in range(rate_limiter.calls):
            await rate_limiter.acquire()
        assert rate_limiter.is_limited

        # 等待窗口滑动
        await asyncio.sleep(rate_limiter.period)
        assert not rate_limiter.is_limited
