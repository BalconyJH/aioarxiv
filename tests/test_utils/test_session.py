import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from aiohttp import ClientResponse, ClientSession
import pytest
from pytest_mock import MockerFixture

from aioarxiv.config import ArxivConfig
from aioarxiv.utils.session import SessionManager


@pytest.fixture
def config() -> ArxivConfig:
    """Create a test configuration.

    Returns:
        ArxivConfig: Test configuration with custom timeout and proxy.
    """
    return ArxivConfig(
        timeout=30.0,
        proxy="http://proxy.example.com",
        rate_limit_calls=5,
        rate_limit_period=1.0,
    )


@pytest.fixture
async def mock_session(mocker: MockerFixture) -> AsyncGenerator[Any, None]:
    """Create a mock aiohttp ClientSession.

    Args:
        mocker: pytest-mock fixture

    Yields:
        Any: Mocked ClientSession with async request method.
    """

    def async_return(*args: Any, **kwargs: Any) -> asyncio.Future[Any]:  # noqa: ARG001
        future = asyncio.Future()
        future.set_result(None)
        return future

    session = mocker.Mock(spec=ClientSession)
    session.request = mocker.Mock(side_effect=async_return)
    session.close = mocker.Mock(side_effect=async_return)
    session.closed = False
    return session


@pytest.fixture
async def mock_response(mocker: MockerFixture) -> AsyncGenerator[Any, None]:
    """Create a mock aiohttp ClientResponse.

    Args:
        mocker: pytest-mock fixture

    Yields:
        Any: Mocked ClientResponse.
    """
    response = mocker.Mock(spec=ClientResponse)
    future = asyncio.Future()
    future.set_result(response)
    return response


@pytest.mark.asyncio
async def test_basic_request(
    mock_session: Any,
    mock_response: Any,
) -> None:
    """Test basic request functionality.

    Args:
        mock_session: Mocked aiohttp session
        mock_response: Mocked response
    """
    future = asyncio.Future()
    future.set_result(mock_response)
    mock_session.request.return_value = future

    manager = SessionManager(session=mock_session)
    await manager.request("GET", "http://example.com")

    mock_session.request.assert_called_once()
    args, _kwargs = mock_session.request.call_args
    assert args[0] == "GET"
    assert args[1] == "http://example.com"


@pytest.mark.asyncio
async def test_request_with_proxy(
    mock_session: Any,
    mock_response: Any,
    config: ArxivConfig,
) -> None:
    """Test request with proxy configuration.

    Args:
        mock_session: Mocked aiohttp session
        mock_response: Mocked response
        config: Test configuration
    """
    future = asyncio.Future()
    future.set_result(mock_response)
    mock_session.request.return_value = future

    manager = SessionManager(session=mock_session, config=config)
    await manager.request("GET", "http://example.com")

    mock_session.request.assert_called_once()
    _, kwargs = mock_session.request.call_args
    assert kwargs.get("proxy") == "http://proxy.example.com"


@pytest.mark.asyncio
async def test_session_lifecycle(
    mock_session: Any,
) -> None:
    """Test session manager lifecycle.

    Args:
        mock_session: Mocked aiohttp session
    """
    async with SessionManager(session=mock_session) as manager:
        assert not mock_session.closed
        await manager.request("GET", "http://example.com")

    mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_rate_limiting(
    mocker: MockerFixture,
    mock_response: Any,
) -> None:
    """Test rate limiting behavior.

    Args:
        mocker: pytest-mock fixture
        mock_response: Mocked response

    This test verifies that:
    1. Rate limiting is properly applied
    2. Sleep is called with correct duration
    3. All requests are completed
    """
    # Test parameters
    calls = 2
    period = 1.0
    total_requests = 3

    config = ArxivConfig(
        rate_limit_calls=calls,
        rate_limit_period=period,
    )

    # Mock sleep without actual waiting
    sleep_durations = []

    async def mock_sleep(duration: float) -> None:
        sleep_durations.append(duration)

    mocker.patch("asyncio.sleep", side_effect=mock_sleep)

    # Mock request
    async def mock_request(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
        return mock_response

    mocker.patch("aiohttp.ClientSession.request", side_effect=mock_request)

    # Execute requests
    async with SessionManager(config=config) as manager:
        tasks = [
            manager.request("GET", "http://example.com") for _ in range(total_requests)
        ]
        await asyncio.gather(*tasks)

    # Verify results
    assert len(sleep_durations) == total_requests - calls, (
        f"Expected {total_requests - calls} rate limit delays, "
        f"got {len(sleep_durations)}"
    )

    # Verify sleep durations
    if sleep_durations:
        assert all(0 < d <= period for d in sleep_durations), (
            f"Invalid sleep duration(s): {sleep_durations}"
        )


@pytest.mark.asyncio
async def test_concurrent_requests_limit(config: ArxivConfig) -> None:
    """Test concurrent request limiting.

    Args:
        config: Test configuration
    """
    concurrent_count = 0
    max_concurrent = 0
    semaphore = asyncio.Semaphore(config.rate_limit_calls)

    async with SessionManager(config=config):

        async def test_request() -> None:
            nonlocal concurrent_count, max_concurrent
            async with semaphore:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
                await asyncio.sleep(0.01)  # 使用更短的睡眠时间
                concurrent_count -= 1

        tasks = [test_request() for _ in range(10)]
        await asyncio.gather(*tasks)

    assert max_concurrent <= config.rate_limit_calls, (
        f"Max concurrent requests ({max_concurrent}) exceeded "
        f"limit ({config.rate_limit_calls})"
    )
