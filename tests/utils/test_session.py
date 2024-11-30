import asyncio

import pytest
from aiohttp import ClientSession, ClientResponse


@pytest.fixture(scope="session")
def config():
    from aioarxiv.config import ArxivConfig

    return ArxivConfig(timeout=30.0, proxy="http://proxy.example.com")


@pytest.fixture
def mock_session(mocker):
    """模拟会话"""
    session = mocker.AsyncMock(spec=ClientSession)
    session.closed = False
    return session


@pytest.fixture(autouse=True)
async def _reset_rate_limiter():
    """重置速率限制器状态"""
    from aioarxiv.utils.rate_limiter import RateLimiter

    RateLimiter.timestamps.clear()
    RateLimiter._calls = 5
    RateLimiter._period = 1.0
    RateLimiter._semaphore = asyncio.Semaphore(5)
    RateLimiter._lock = asyncio.Lock()
    return


@pytest.mark.asyncio
async def test_request(mock_session, mocker):
    """测试请求方法"""
    from aioarxiv.utils.session import SessionManager

    mock_response = mocker.AsyncMock(spec=ClientResponse)

    async def mock_request(*args, **kwargs):
        return mock_response

    mock_session.request = mocker.AsyncMock(side_effect=mock_request)

    async with SessionManager(session=mock_session) as manager:
        response = await manager.request("GET", "http://example.com")
        mock_session.request.assert_called_once_with("GET", "http://example.com")
        assert response == mock_response


@pytest.mark.asyncio
async def test_request_with_proxy(mock_session, mocker, config):
    """测试代理请求"""
    from aioarxiv.utils.session import SessionManager

    mock_response = mocker.AsyncMock(spec=ClientResponse)

    async def mock_request(*args, **kwargs):
        return mock_response

    mock_session.request = mocker.AsyncMock(side_effect=mock_request)

    async with SessionManager(config=config, session=mock_session) as manager:
        await manager.request("GET", "http://example.com")
        mock_session.request.assert_called_once_with(
            "GET", "http://example.com", proxy="http://proxy.example.com"
        )


@pytest.mark.asyncio
async def test_rate_limiting(mocker):
    """测试速率限制"""
    from aioarxiv.utils.session import SessionManager
    from aioarxiv.utils.rate_limiter import RateLimiter

    RateLimiter.timestamps.clear()
    RateLimiter._calls = 2
    RateLimiter._period = 1.0
    RateLimiter._semaphore = asyncio.Semaphore(2)
    RateLimiter._lock = asyncio.Lock()

    mock_response = mocker.AsyncMock(spec=ClientResponse)
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
            )
        )

        assert mock_sleep.call_count >= 1
        assert mock_request.call_count == 3

        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert all(duration > 0 for duration in sleep_calls)
