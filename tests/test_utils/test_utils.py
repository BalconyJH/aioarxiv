import asyncio
from datetime import datetime
from io import StringIO
import math
from time import monotonic
from types import SimpleNamespace
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import aiohttp
from aiohttp import ClientResponse, TraceRequestEndParams, TraceRequestStartParams
from loguru import logger
from multidict import CIMultiDict
import pytest
from yarl import URL

from aioarxiv.config import ArxivConfig
from aioarxiv.utils import (
    create_parser_exception,
    create_trace_config,
    format_datetime,
    sanitize_title,
)
from aioarxiv.utils.log import ConfigManager

TOLERANCE = 0.25


def test_config_manager_is_singleton():
    assert ConfigManager() is ConfigManager()


@pytest.fixture
def sample_xml_element():
    """Create a sample XML element for testing."""
    root = ET.Element("root")
    child = ET.SubElement(root, "child")
    child.text = "test content"
    return root


@pytest.fixture
def capture_debug_logs():
    """Capture loguru DEBUG output."""
    string_io = StringIO()

    handler_id = logger.add(
        string_io,
        format="{message}",
        level="DEBUG",
        catch=False,
    )

    yield string_io

    logger.remove(handler_id)


@pytest.fixture
def mock_session(mocker):
    """Create a mocked aiohttp session."""
    return mocker.create_autospec(aiohttp.ClientSession)


@pytest.fixture
def mock_response(mocker):
    """Create a mocked ClientResponse."""
    response = mocker.create_autospec(ClientResponse, instance=True)

    response.status = 200
    response.url = URL("http://test.com/api")
    response.read = b""
    response.close = mocker.AsyncMock()

    return response


@pytest.mark.asyncio
async def test_create_trace_config_request_lifecycle(
    mock_session, mock_response, capture_debug_logs
):
    """Trace config logs the request lifecycle and measures elapsed time."""
    trace_config = create_trace_config()
    assert isinstance(trace_config, aiohttp.TraceConfig)

    ctx = SimpleNamespace()

    start_params = TraceRequestStartParams(
        method="GET", url=URL("http://test.com/api"), headers=CIMultiDict()
    )

    await trace_config.on_request_start[0](mock_session, ctx, start_params)

    start_log = capture_debug_logs.getvalue()
    assert "Starting request: GET http://test.com/api" in start_log

    start_time = ctx.start_time

    expected_delay = 0.1
    await asyncio.sleep(expected_delay)

    end_params = TraceRequestEndParams(
        method="GET",
        url=URL("http://test.com/api"),
        headers=CIMultiDict(),
        response=mock_response,
    )

    await trace_config.on_request_end[0](mock_session, ctx, end_params)

    full_log = capture_debug_logs.getvalue()

    assert "Ending request: 200 http://test.com/api" in full_log
    assert "Time elapsed:" in full_log
    assert "seconds" in full_log

    elapsed_time = monotonic() - start_time
    assert math.isclose(elapsed_time, expected_delay, rel_tol=TOLERANCE), (
        f"Elapsed time out of expected range: expected about {expected_delay}s, "
        f"got {elapsed_time:.4f}s"
    )


@pytest.mark.asyncio
async def test_create_trace_config_error_case(
    mock_session, mock_response, mocker, capture_debug_logs
):
    """Trace config logs non-200 responses as well."""
    trace_config = create_trace_config()
    ctx = SimpleNamespace()

    mocker.patch.object(mock_response, "status", 404)
    mocker.patch.object(mock_response, "url", URL("invalid://url"))

    start_params = TraceRequestStartParams(
        method="GET", url=URL("invalid://url"), headers=CIMultiDict()
    )

    await trace_config.on_request_start[0](mock_session, ctx, start_params)

    end_params = TraceRequestEndParams(
        method="GET",
        url=URL("invalid://url"),
        headers=CIMultiDict(),
        response=mock_response,
    )

    await trace_config.on_request_end[0](mock_session, ctx, end_params)

    log_output = capture_debug_logs.getvalue()

    assert "Starting request: GET invalid://url" in log_output
    assert "Ending request: 404 invalid://url" in log_output


def test_create_parser_exception_basic(sample_xml_element):
    """Exception factory fills defaults when given only the XML element."""
    exception = create_parser_exception(data=sample_xml_element)

    assert exception.url == ""
    assert exception.message == "Failed to parse response"
    assert exception.context is not None
    assert exception.context.element_name == "root"
    assert exception.context.raw_content is not None
    assert "<root><child>test content</child></root>" in exception.context.raw_content
    assert exception.context.namespace is None
    assert exception.original_error is None


def test_create_parser_exception_with_all_params(sample_xml_element):
    """Exception factory carries through all provided parameters."""
    test_url = "http://test.com/api"
    custom_message = "Custom error message"
    namespace = "http://test.namespace"
    original_error = ValueError("test error")

    exception = create_parser_exception(
        data=sample_xml_element,
        url=test_url,
        message=custom_message,
        namespace=namespace,
        error=original_error,
    )

    assert exception.url == test_url
    assert exception.message == custom_message
    assert exception.context is not None
    assert exception.context.namespace == namespace
    assert exception.original_error == original_error
    assert exception.context.raw_content is not None
    assert "<root><child>test content</child></root>" in exception.context.raw_content
    assert exception.context.element_name == "root"


def test_format_datetime():
    """format_datetime renders in the configured timezone."""
    dt = datetime(2024, 12, 31, 22, 27, 42, tzinfo=ZoneInfo("UTC"))
    formatted = format_datetime(dt)

    assert isinstance(formatted, str)
    assert "_" in formatted
    assert formatted.endswith("CST")  # default timezone is Asia/Shanghai


def test_format_datetime_honors_active_config_timezone():
    """A custom active config timezone flows into format_datetime output."""
    original = ConfigManager.get_config()
    ConfigManager.set_config(ArxivConfig(timezone="UTC"))
    try:
        dt = datetime(2024, 12, 31, 22, 27, 42, tzinfo=ZoneInfo("UTC"))
        assert format_datetime(dt).endswith("UTC")
    finally:
        ConfigManager.set_config(original)


def test_sanitize_title():
    test_cases = [
        ("normal title", "normal title"),
        ("file/with*/invalid:chars", "file-with-invalid-chars"),
        ("a" * 100, "a" * 47 + "..."),
        ("  spaces  ", "spaces"),
        ('test"quote"test', "test-quote-test"),
    ]

    for input_title, expected in test_cases:
        result = sanitize_title(input_title)
        assert result == expected


def test_sanitize_title_custom_length():
    result = sanitize_title("very long title", max_length=10)
    assert len(result) <= 10
    assert result.endswith("...")


def test_sanitize_title_edge_cases():
    assert sanitize_title("") == ""
    assert sanitize_title("***:::///") == ""
