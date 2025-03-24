import asyncio
import math
from typing import NoReturn

import pytest
from pytest_mock import MockerFixture

from aioarxiv.utils.rate_limiter import RateLimiter


@pytest.fixture
def limiter() -> RateLimiter:
    """Create a RateLimiter instance for testing.

    Returns:
        RateLimiter: A fresh RateLimiter instance with test settings.
    """
    return RateLimiter(calls=2, period=1.0)  # 使用较小的值便于测试


@pytest.mark.asyncio
async def test_basic_rate_limiting(mocker: MockerFixture, limiter: RateLimiter) -> None:
    """Test basic rate limiting functionality.

    Args:
        mocker: pytest-mock fixture
        limiter: The rate limiter fixture
    """
    current_time = 0.0
    sleep_calls: list[float] = []

    # 模拟时间和睡眠函数
    def mock_time() -> float:
        return current_time

    async def mock_sleep(duration: float) -> None:
        nonlocal current_time
        sleep_calls.append(duration)
        current_time += duration

    mocker.patch("time.time", mock_time)
    mocker.patch("asyncio.sleep", mock_sleep)

    call_order: list[int] = []

    @limiter.limit()
    async def test_func() -> int:
        call_number = len(call_order) + 1
        call_order.append(call_number)
        return call_number

    # 执行测试
    results = await asyncio.gather(*(test_func() for _ in range(3)))

    # 验证结果
    assert results == [1, 2, 3], "函数调用应该按顺序执行"
    assert len(sleep_calls) == 1, (
        f"应该只有一次速率限制延迟, 实际有 {len(sleep_calls)} 次"
    )
    if sleep_calls:
        assert math.isclose(sleep_calls[0], 1.0, rel_tol=0.05), (
            f"延迟时间应接近 1.0 秒, 实际为 {sleep_calls[0]:.2f} 秒"
        )


@pytest.mark.asyncio
async def test_window_sliding(mocker: MockerFixture, limiter: RateLimiter) -> None:
    """Test time window sliding behavior.

    Args:
        mocker: pytest-mock fixture
        limiter: The rate limiter fixture
    """
    current_time = 0.0
    sleep_calls: list[float] = []

    async def mock_sleep(duration: float) -> None:
        nonlocal current_time
        sleep_calls.append(duration)
        current_time += duration

    def mock_time() -> float:
        return current_time

    mocker.patch("time.time", mock_time)
    mocker.patch("asyncio.sleep", mock_sleep)

    @limiter.limit()
    async def test_func() -> None:
        pass

    # 执行测试
    await test_func()  # 第一次调用
    await test_func()  # 第二次调用（应该立即执行）
    await test_func()  # 第三次调用（应该被限制）

    assert len(sleep_calls) == 1, "应该只有一次速率限制延迟"
    if sleep_calls:
        assert math.isclose(sleep_calls[0], 1.0, rel_tol=0.05), (
            f"延迟时间应接近 1.0 秒, 实际为 {sleep_calls[0]:.2f} 秒"
        )


@pytest.mark.asyncio
async def test_concurrent_requests():
    limiter = RateLimiter(calls=3, period=0.5)

    semaphore = asyncio.Semaphore(2)
    active_count = 0
    max_active = 0

    @limiter.limit()
    async def test_func() -> None:
        nonlocal active_count, max_active
        async with semaphore:
            active_count += 1
            max_active = max(max_active, active_count)
            await asyncio.sleep(0.01)
            active_count -= 1

    tasks = [test_func() for _ in range(5)]
    await asyncio.gather(*tasks)

    assert max_active <= 2


@pytest.mark.asyncio
async def test_error_handling(limiter: RateLimiter) -> None:
    """Test error propagation.

    Args:
        limiter: The rate limiter fixture
    """

    @limiter.limit()
    async def failing_func() -> NoReturn:
        raise ValueError("测试错误")

    with pytest.raises(ValueError, match="测试错误"):
        await failing_func()


@pytest.mark.asyncio
async def test_multiple_limiters() -> None:
    """Test independent rate limiters.

    This test verifies that:
    1. Different rate limiter instances are independent
    2. Each limiter maintains its own state
    """
    limiter_a = RateLimiter(calls=2, period=1.0)
    limiter_b = RateLimiter(calls=2, period=1.0)

    calls_a = []
    calls_b = []

    @limiter_a.limit()
    async def func_a() -> None:
        calls_a.append(asyncio.get_event_loop().time())
        await asyncio.sleep(0.1)

    @limiter_b.limit()
    async def func_b() -> None:
        calls_b.append(asyncio.get_event_loop().time())
        await asyncio.sleep(0.1)

    # Test interleaved execution
    await func_a()
    await func_b()
    await asyncio.sleep(1.1)  # Wait for window to reset
    await func_a()
    await func_b()

    assert len(calls_a) == 2, "Should complete two calls to func_a"
    assert len(calls_b) == 2, "Should complete two calls to func_b"

    # Verify timing between calls
    timestamps = sorted(calls_a + calls_b)
    assert timestamps[2] - timestamps[0] >= 1.0
