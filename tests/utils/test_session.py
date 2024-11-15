# tests/utils/test_session.py

import pytest
from aiohttp import ClientResponse, ClientSession, ClientTimeout
from pytest_mock import MockerFixture

from src.config import ArxivConfig
from src.utils.rate_limiter import RateLimiter
from src.utils.session import SessionManager


@pytest.fixture
def config():
    return ArxivConfig(
        timeout=30,
        rate_limit_calls=3,
        rate_limit_period=1,
    )


@pytest.fixture
def rate_limiter():
    return RateLimiter(calls=3, period=1)


@pytest.fixture
async def session_manager(config, rate_limiter):
    manager = SessionManager(config=config, rate_limiter=rate_limiter)
    yield manager
    await manager.close()


@pytest.mark.asyncio
async def test_init_with_config(config):
    """测试使用配置初始化"""
    manager = SessionManager(config=config)
    assert manager._config == config
    assert isinstance(manager._timeout, ClientTimeout)
    assert manager._timeout.total == config.timeout


@pytest.mark.asyncio
async def test_get_session(session_manager):
    """测试获取会话"""
    session = await session_manager.get_session()
    assert isinstance(session, ClientSession)
    assert not session.closed


@pytest.mark.asyncio
async def test_reuse_existing_session(session_manager):
    """测试复用现有会话"""
    session1 = await session_manager.get_session()
    session2 = await session_manager.get_session()
    assert session1 is session2


@pytest.mark.asyncio
async def test_rate_limited_context(session_manager, mocker: MockerFixture):
    """测试速率限制上下文"""
    mock_limiter = mocker.patch.object(RateLimiter, "acquire")

    async with session_manager.rate_limited_context():
        pass

    mock_limiter.assert_awaited_once()


@pytest.mark.asyncio
async def test_close(session_manager):
    """测试关闭会话"""
    session = await session_manager.get_session()
    assert not session.closed

    await session_manager.close()
    assert session.closed
    assert session_manager._session is None


@pytest.mark.asyncio
async def test_context_manager(session_manager):
    """测试上下文管理器"""
    async with session_manager as manager:
        session = await manager.get_session()
        assert not session.closed

    assert session.closed


@pytest.mark.asyncio
async def test_request(session_manager, mocker: MockerFixture):
    """测试请求方法(包含速率限制)"""
    # 1. 模拟响应
    mock_response = mocker.AsyncMock(spec=ClientResponse)

    # 2. 模拟会话
    mock_session = mocker.AsyncMock(spec=ClientSession)
    mock_session.request = mocker.AsyncMock(return_value=mock_response)

    # 3. 模拟 get_session
    async def mock_get_session():
        return mock_session

    session_manager.get_session = mock_get_session

    # 4. 模拟速率限制器
    mock_acquire = mocker.AsyncMock()
    session_manager._rate_limiter.acquire = mock_acquire

    # 5. 执行请求
    response = await session_manager.request("GET", "http://example.com")

    # 6. 验证
    assert response == mock_response
    mock_acquire.assert_awaited_once()
    mock_session.request.assert_called_once_with(
        "GET", "http://example.com", proxy=None
    )


@pytest.mark.asyncio
async def test_request_creates_new_session_if_closed(session_manager):
    """测试请求时如果会话已关闭则创建新会话"""
    session1 = await session_manager.get_session()
    await session1.close()

    session2 = await session_manager.get_session()
    assert session2 is not session1
    assert not session2.closed


@pytest.mark.asyncio
async def test_request_with_proxy(session_manager, mocker: MockerFixture):
    """测试请求方法(包含代理)"""
    mock_response = mocker.AsyncMock(spec=ClientResponse)
    mock_session = mocker.AsyncMock(spec=ClientSession)
    mock_session.request = mocker.AsyncMock(return_value=mock_response)

    async def mock_get_session():
        return mock_session

    session_manager.get_session = mock_get_session

    mock_acquire = mocker.AsyncMock()
    session_manager._rate_limiter.acquire = mock_acquire

    session_manager._config.proxy = "http://proxy.com"
    response = await session_manager.request("GET", "http://example.com")

    assert response == mock_response
    mock_acquire.assert_awaited_once()
    mock_session.request.assert_called_once_with(
        "GET", "http://example.com", proxy="http://proxy.com"
    )
