import asyncio

from aiohttp import ClientResponse, ClientSession
import pytest

from aioarxiv.config import ArxivConfig
from aioarxiv.utils.rate_limiter import RateLimiter
from aioarxiv.utils.session import SessionManager


@pytest.fixture(scope="session")
def config() -> "ArxivConfig":
    from aioarxiv.config import ArxivConfig

    return ArxivConfig(timeout=30.0, proxy="http://proxy.example.com")


@pytest.fixture
def mock_session(mocker):
    """Mock ClientSession with configured request method"""
    session = mocker.AsyncMock(spec=ClientSession)
    session.request = mocker.AsyncMock()
    session.closed = False
    return session


@pytest.fixture
def mock_response(mocker):
    return mocker.AsyncMock(spec=ClientResponse)


@pytest.fixture(autouse=True)
async def _reset_rate_limiter() -> None:
    """重置速率限制器状态"""
    RateLimiter.timestamps.clear()
    RateLimiter._calls = 5
    RateLimiter._period = 1.0
    RateLimiter._semaphore = asyncio.Semaphore(5)
    RateLimiter._lock = asyncio.Lock()


@pytest.mark.asyncio
async def test_request(mock_session, mock_response):
    """Test request method"""
    mock_session.request.return_value = mock_response

    await SessionManager(session=mock_session).request("GET", "http://example.com")

    assert mock_session.request.call_count == 1
    args = mock_session.request.call_args.args
    assert args == ("GET", "http://example.com")


@pytest.mark.asyncio
async def test_request_with_proxy(mock_session, mock_response, config):
    """Test request with proxy configuration"""
    mock_session.request.return_value = mock_response

    await SessionManager(session=mock_session, config=config).request(
        "GET", "http://example.com"
    )
    await asyncio.sleep(0)

    assert mock_session.request.call_count == 1
    kwargs = mock_session.request.call_args.kwargs
    assert kwargs["proxy"] == "http://proxy.example.com"


@pytest.mark.asyncio
async def test_session_lifecycle(mock_session, mocker) -> None:
    """测试会话生命周期"""
    async with SessionManager(session=mock_session) as manager:
        assert not mock_session.closed
        await manager.request("GET", "http://example.com")

    mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_rate_limiting(mocker, mock_response) -> None:
    """测试速率限制"""
    RateLimiter.timestamps.clear()
    RateLimiter._calls = 2
    RateLimiter._period = 1.0
    RateLimiter._semaphore = asyncio.Semaphore(2)
    RateLimiter._lock = asyncio.Lock()

    mock_sleep = mocker.patch("asyncio.sleep", new_callable=mocker.AsyncMock)
    mock_request = mocker.patch(
        "aiohttp.ClientSession.request",
        new_callable=mocker.AsyncMock,
        return_value=mock_response,
    )

    async with SessionManager() as manager:
        await asyncio.gather(
            *(
                manager.request("GET", "http://export.arxiv.org/api/query")
                for _ in range(3)
            ),
        )

        assert mock_sleep.call_count >= 1
        assert mock_request.call_count == 3

        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert all(duration > 0 for duration in sleep_calls)
