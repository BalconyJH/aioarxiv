import asyncio
from collections.abc import Awaitable, Callable
from itertools import pairwise
from types import SimpleNamespace
from typing import Any, cast

from aiohttp import ClientSession
from pydantic import ValidationError
import pytest
from pytest_mock import MockerFixture

from aioarxiv.config import ArxivConfig
from aioarxiv.utils.session import SessionManager


class FakeClientSession:
    """Minimal stand-in for aiohttp.ClientSession.

    Records every request and optionally awaits a side-effect hook inside the
    request body, letting tests observe timing and in-flight concurrency
    without any network access.
    """

    def __init__(self, hook: Callable[[], Awaitable[None]] | None = None) -> None:
        self.closed = False
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self._hook = hook

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append((method, url, kwargs))
        if self._hook is not None:
            await self._hook()
        return SimpleNamespace(status=200)

    async def close(self) -> None:
        self.closed = True


def as_client_session(fake: FakeClientSession) -> ClientSession:
    """Cast a fake session to the ClientSession type expected by SessionManager."""
    return cast("ClientSession", fake)


@pytest.fixture
def proxy_config() -> ArxivConfig:
    """Create a test configuration with a proxy.

    Returns:
        ArxivConfig: Test configuration with custom timeout and proxy.
    """
    return ArxivConfig(
        timeout=30.0,
        proxy="http://proxy.example.com",
        rate_limit_calls=5,
        rate_limit_period=1.0,
    )


@pytest.mark.asyncio
async def test_basic_request() -> None:
    """Test that request() forwards method, url and returns the response."""
    fake = FakeClientSession()

    manager = SessionManager(session=as_client_session(fake))
    response = await manager.request("GET", "http://example.com")

    assert response.status == 200
    assert len(fake.calls) == 1
    method, url, _kwargs = fake.calls[0]
    assert method == "GET"
    assert url == "http://example.com"


@pytest.mark.asyncio
async def test_request_with_proxy(proxy_config: ArxivConfig) -> None:
    """Test that the configured proxy is injected into request kwargs.

    Args:
        proxy_config: Test configuration with a proxy set.
    """
    fake = FakeClientSession()

    manager = SessionManager(session=as_client_session(fake), config=proxy_config)
    await manager.request("GET", "http://example.com")

    assert len(fake.calls) == 1
    _method, _url, kwargs = fake.calls[0]
    assert kwargs.get("proxy") == "http://proxy.example.com"


@pytest.mark.asyncio
async def test_session_lifecycle() -> None:
    """Test that the context manager closes the underlying session on exit."""
    fake = FakeClientSession()

    async with SessionManager(session=as_client_session(fake)) as manager:
        await manager.request("GET", "http://example.com")
        assert not fake.closed

    assert fake.closed


@pytest.mark.asyncio
async def test_closed_session_recreated(mocker: MockerFixture) -> None:
    """Test lazy session creation and recreation after the session is closed.

    Args:
        mocker: pytest-mock fixture.
    """
    created: list[FakeClientSession] = []

    def factory(**kwargs: Any) -> FakeClientSession:  # noqa: ARG001
        fake = FakeClientSession()
        created.append(fake)
        return fake

    mocker.patch("aioarxiv.utils.session.ClientSession", side_effect=factory)
    mocker.patch("aioarxiv.utils.session.TCPConnector")

    # Rate limiting disabled so sequential requests do not wait out the
    # default 3 s spacing.
    config = ArxivConfig(rate_limit_period=0.0)
    manager = SessionManager(config=config)

    await manager.request("GET", "http://example.com")
    await manager.request("GET", "http://example.com")
    assert len(created) == 1, "Session should be created lazily and reused"
    assert len(created[0].calls) == 2

    created[0].closed = True
    await manager.request("GET", "http://example.com")
    assert len(created) == 2, "A closed session should be replaced"
    assert len(created[1].calls) == 1

    await manager.close()
    assert created[1].closed


@pytest.mark.asyncio
async def test_request_spacing() -> None:
    """Test strict spacing between request starts.

    With calls=1 and period=0.3, concurrent requests must start at least
    ~0.3 s apart (the first one immediately).
    """
    config = ArxivConfig(
        rate_limit_calls=1,
        rate_limit_period=0.3,
        max_concurrent_requests=5,
    )
    loop = asyncio.get_running_loop()
    start_times: list[float] = []

    async def record_start() -> None:
        start_times.append(loop.time())

    fake = FakeClientSession(hook=record_start)
    manager = SessionManager(session=as_client_session(fake), config=config)

    await asyncio.gather(
        *(manager.request("GET", "http://example.com") for _ in range(3))
    )

    assert len(start_times) == 3
    gaps = [later - earlier for earlier, later in pairwise(sorted(start_times))]
    assert all(gap >= 0.29 for gap in gaps), f"Requests too close together: {gaps}"


@pytest.mark.asyncio
async def test_concurrency_cap() -> None:
    """Test that in-flight requests never exceed max_concurrent_requests."""
    config = ArxivConfig(
        rate_limit_calls=1,
        rate_limit_period=0.0,  # disable rate limiting to isolate the semaphore
        max_concurrent_requests=2,
    )
    in_flight = 0
    peak = 0

    async def track_in_flight() -> None:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1

    fake = FakeClientSession(hook=track_in_flight)
    manager = SessionManager(session=as_client_session(fake), config=config)

    await asyncio.gather(
        *(manager.request("GET", "http://example.com") for _ in range(6))
    )

    assert peak <= 2, f"In-flight requests ({peak}) exceeded the limit (2)"
    assert peak == 2, "Semaphore should allow the full concurrency budget"


@pytest.mark.asyncio
@pytest.mark.parametrize(("calls", "period"), [(0, 3.0), (1, 0.0)])
async def test_degenerate_config_disables_rate_limiting(
    calls: int, period: float
) -> None:
    """Test that zero calls or zero period disables throttling entirely.

    Args:
        calls: Rate limit call budget under test.
        period: Rate limit window under test.
    """
    config = ArxivConfig(
        rate_limit_calls=calls,
        rate_limit_period=period,
        max_concurrent_requests=10,
    )
    fake = FakeClientSession()
    manager = SessionManager(session=as_client_session(fake), config=config)

    loop = asyncio.get_running_loop()
    start = loop.time()
    await asyncio.gather(
        *(manager.request("GET", "http://example.com") for _ in range(5))
    )
    elapsed = loop.time() - start

    assert len(fake.calls) == 5
    assert elapsed < 0.25, f"Requests should not be throttled, took {elapsed:.3f}s"


def test_max_concurrent_below_one_rejected() -> None:
    """Test that max_concurrent_requests < 1 is rejected at config validation."""
    with pytest.raises(ValidationError):
        ArxivConfig(max_concurrent_requests=0)
