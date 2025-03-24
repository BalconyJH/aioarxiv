import asyncio
from datetime import datetime
from io import StringIO
import math
from time import monotonic
from types import SimpleNamespace
from typing import cast
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import aiohttp
from aiohttp import ClientResponse, TraceRequestEndParams, TraceRequestStartParams
from loguru import logger
from multidict import CIMultiDict
import pytest
from tenacity import RetryCallState
from yarl import URL

from aioarxiv.utils import (
    calculate_page_size,
    create_parser_exception,
    create_trace_config,
    format_datetime,
    log_retry_attempt,
    sanitize_title,
)

TOLERANCE = 0.25


@pytest.fixture
def sample_xml_element():
    """创建示例 XML 元素用于测试"""
    root = ET.Element("root")
    child = ET.SubElement(root, "child")
    child.text = "test content"
    return root


@pytest.fixture
def mock_retry_state():
    """创建模拟的 RetryCallState"""

    class MockRetryState:
        def __init__(self):
            self.attempt_number = 1

    return MockRetryState()


@pytest.fixture
def capture_debug_logs():
    """捕获 loguru 的 DEBUG 日志"""
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
    """创建模拟的 aiohttp session"""
    return mocker.create_autospec(aiohttp.ClientSession)


@pytest.fixture
def mock_response(mocker):
    """创建模拟的 ClientResponse"""
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
    """测试请求生命周期的追踪配置"""
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
        f"请求耗时不在预期范围内: 期望约为{expected_delay}秒, "
        f"实际为{elapsed_time:.4f}秒"
    )


@pytest.mark.asyncio
async def test_create_trace_config_error_case(
    mock_session, mock_response, mocker, capture_debug_logs
):
    """测试错误情况下的追踪配置"""
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


@pytest.mark.asyncio
async def test_create_trace_config_multiple_requests(mock_session, mock_response):
    """
    测试多个连续请求的追踪配置
    """
    trace_config = create_trace_config()
    ctx = SimpleNamespace()

    async def make_request(delay: float):
        start_params = TraceRequestStartParams(
            method="GET", url=URL("http://test.com/api"), headers=CIMultiDict()
        )

        await trace_config.on_request_start[0](mock_session, ctx, start_params)
        start_time = ctx.start_time

        await asyncio.sleep(delay)

        end_params = TraceRequestEndParams(
            method="GET",
            url=URL("http://test.com/api"),
            headers=CIMultiDict(),
            response=mock_response,
        )

        await trace_config.on_request_end[0](mock_session, ctx, end_params)

        return monotonic() - start_time

    delays = [0.1, 0.2, 0.3]
    elapsed_times = []

    for delay in delays:
        elapsed_time = await make_request(delay)
        elapsed_times.append(elapsed_time)

    for expected, actual in zip(delays, elapsed_times):
        assert math.isclose(actual, expected, rel_tol=TOLERANCE), (
            f"请求耗时不在预期范围内: 期望约为{expected}秒, 实际为{actual:.4f}秒"
        )


def test_create_parser_exception_basic(sample_xml_element):
    """
    测试创建基本的解析异常

    验证:
    1. 使用最基本的参数创建异常
    2. 检查默认消息
    """
    exception = create_parser_exception(data=sample_xml_element)

    assert exception.url == ""
    assert exception.message == "解析响应失败"
    assert exception.context is not None
    assert exception.context.element_name == "root"
    assert exception.context.raw_content is not None
    assert "<root><child>test content</child></root>" in exception.context.raw_content
    assert exception.context.namespace is None
    assert exception.original_error is None


def test_create_parser_exception_with_url(sample_xml_element):
    """
    测试创建带 URL 的解析异常

    验证:
    1. URL 被正确设置
    2. 其他参数保持默认值
    """
    test_url = "http://test.com/api"
    exception = create_parser_exception(data=sample_xml_element, url=test_url)

    assert exception.url == test_url
    assert exception.message == "解析响应失败"


def test_create_parser_exception_with_custom_message(sample_xml_element):
    """
    测试创建带自定义消息的解析异常

    验证:
    1. 自定义消息被正确设置
    2. 其他参数保持默认值
    """
    custom_message = "自定义错误消息"
    exception = create_parser_exception(data=sample_xml_element, message=custom_message)

    assert exception.url == ""
    assert exception.message == custom_message


def test_create_parser_exception_with_namespace(sample_xml_element):
    """
    测试创建带命名空间的解析异常

    验证:
    1. 命名空间被正确设置
    2. 其他参数保持默认值
    """
    namespace = "http://test.namespace"
    exception = create_parser_exception(data=sample_xml_element, namespace=namespace)

    assert exception.context is not None
    assert exception.context.namespace == namespace
    assert exception.url == ""
    assert exception.message == "解析响应失败"


def test_create_parser_exception_with_error(sample_xml_element):
    """
    测试创建带原始异常的解析异常

    验证:
    1. 原始异常被正确设置
    2. 其他参数保持默认值
    """
    original_error = ValueError("测试错误")
    exception = create_parser_exception(data=sample_xml_element, error=original_error)

    assert exception.original_error == original_error
    assert exception.url == ""
    assert exception.message == "解析响应失败"


def test_create_parser_exception_with_all_params(sample_xml_element):
    """
    测试创建包含所有参数的解析异常

    验证:
    1. 所有参数都被正确设置
    2. XML内容被正确转换为字符串
    """
    test_url = "http://test.com/api"
    custom_message = "自定义错误消息"
    namespace = "http://test.namespace"
    original_error = ValueError("测试错误")

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


def test_create_parser_exception_with_complex_xml(sample_xml_element):
    """
    测试使用复杂XML创建解析异常

    验证:
    1. 复杂XML结构被正确处理
    2. 异常包含完整的XML内容
    """
    # 创建更复杂的XML结构
    sub_element = ET.SubElement(sample_xml_element, "nested")
    sub_element.set("attr", "value")
    sub_element.text = "nested content"

    exception = create_parser_exception(data=sample_xml_element)

    assert exception.context is not None
    assert exception.context.element_name == "root"
    assert exception.context.raw_content is not None
    assert 'attr="value"' in exception.context.raw_content
    assert "nested content" in exception.context.raw_content


# 测试 calculate_page_size
@pytest.mark.asyncio
async def test_calculate_page_size():
    test_cases = [
        (100, 0, None, 100),  # 无最大结果限制
        (100, 0, 50, 50),  # 最大结果小于页面大小
        (100, 30, 50, 20),  # 考虑起始位置
        (100, 0, 150, 100),  # 最大结果大于页面大小
    ]

    for config_size, start, max_results, expected in test_cases:
        result = calculate_page_size(config_size, start, max_results)
        assert result == expected


# 测试 format_datetime
@pytest.mark.asyncio
async def test_format_datetime():
    # 创建一个固定的UTC时间
    dt = datetime(2024, 12, 31, 22, 27, 42, tzinfo=ZoneInfo("UTC"))
    formatted = format_datetime(dt)

    # 验证格式
    assert isinstance(formatted, str)
    assert "_" in formatted
    assert formatted.endswith("CST")  # 假设默认时区为 CST


# 测试 sanitize_title
@pytest.mark.asyncio
async def test_sanitize_title():
    test_cases = [
        ("normal title", "normal title"),
        ("file/with*/invalid:chars", "file-with-invalid-chars"),
        ("a" * 100, "a" * 47 + "..."),  # 测试长度限制
        ("  spaces  ", "spaces"),  # 测试空格处理
        ('test"quote"test', "test-quote-test"),  # 测试引号处理
    ]

    for input_title, expected in test_cases:
        result = sanitize_title(input_title)
        assert result == expected


# 测试自定义长度限制
@pytest.mark.asyncio
async def test_sanitize_title_custom_length():
    result = sanitize_title("very long title", max_length=10)
    assert len(result) <= 10
    assert result.endswith("...")


@pytest.mark.asyncio
async def test_log_retry_attempt(mock_retry_state, capture_debug_logs):
    """测试重试日志记录功能"""
    # 执行日志记录
    log_retry_attempt(cast(RetryCallState, mock_retry_state))

    # 获取日志内容
    log_output = capture_debug_logs.getvalue()

    # 验证日志内容
    assert "retry times:" in log_output


# 测试边界情况
@pytest.mark.asyncio
async def test_edge_cases():
    # 测试空标题
    assert sanitize_title("") == ""

    # 测试全特殊字符的标题
    assert sanitize_title("***:::///") == ""

    # 测试计算页面大小的边界情况
    assert calculate_page_size(100, 999, 1000) == 1
    assert calculate_page_size(100, 1000, 1000) == 0


# 测试异常情况
@pytest.mark.asyncio
async def test_exception_cases(sample_xml_element):
    # 测试无参数创建解析异常
    exception = create_parser_exception(sample_xml_element)
    assert exception.url == ""
    assert exception.message == "解析响应失败"
