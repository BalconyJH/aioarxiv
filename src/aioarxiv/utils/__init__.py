from datetime import datetime
import re
from time import monotonic
from types import SimpleNamespace
from typing import Optional
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import aiohttp
from tenacity import RetryCallState

from aioarxiv.config import default_config
from aioarxiv.exception import ParseErrorContext, ParserException

from .log import logger


def create_trace_config() -> aiohttp.TraceConfig:
    """
    创建请求追踪配置。

    Returns:
        aiohttp.TraceConfig: 请求追踪配置
    """

    async def _on_request_start(
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceRequestStartParams,
    ) -> None:
        logger.debug(f"Starting request: {params.method} {params.url}")
        trace_config_ctx.start_time = monotonic()

    async def _on_request_end(
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceRequestEndParams,
    ) -> None:
        elapsed_time = monotonic() - trace_config_ctx.start_time
        logger.debug(
            f"Ending request: {params.response.status} {params.url} - Time elapsed: "
            f"{elapsed_time:.2f} seconds",
        )

    trace_config = aiohttp.TraceConfig()
    trace_config.on_request_start.append(_on_request_start)
    trace_config.on_request_end.append(_on_request_end)
    return trace_config


def create_parser_exception(
    data: ET.Element,
    url: Optional[str] = None,
    message: Optional[str] = None,
    namespace: Optional[str] = None,
    error: Optional[Exception] = None,
) -> ParserException:
    """
    创建解析异常, 用于解析xml数据时出现错误。

    Args:
        data (ET.Element): 解析失败的数据
        url (str): 请求url
        message (Optional[str], optional): 异常消息. Defaults to None.
        namespace (Optional[str], optional): 命名空间. Defaults to None.
        error (Optional[Exception], optional): 原始异常. Defaults to None.

    Returns:
        ParserException: 解析异常
    """
    return ParserException(
        url=url or "",
        message=message or "解析响应失败",
        context=ParseErrorContext(
            raw_content=ET.tostring(data, encoding="unicode"),
            element_name=data.tag,
            namespace=namespace,
        ),
        original_error=error,
    )


def calculate_page_size(
    config_page_size: int,
    start: int,
    max_results: Optional[int],
) -> int:
    """
    计算单页大小, 限制在配置的单页大小和最大结果数之间。

    Args:
        config_page_size (int): 配置的单页大小
        start (int): 起始位置
        max_results (Optional[int]): 最大结果数

    Returns:
        int: 单页大小
    """
    if max_results is None:
        return config_page_size

    return min(config_page_size, max_results - start)


def format_datetime(dt: datetime) -> str:
    """
    格式化日期时间。

    Args:
        dt (datetime): 日期时间

    Returns:
        str: 格式化后的日期时间, 格式为: %Y-%m-%d_%H-%M-%S_%Z (2024-03-21_15-30-00_CST)
    """
    local_dt = dt.astimezone(ZoneInfo(default_config.timezone))
    return local_dt.strftime("%Y-%m-%d_%H-%M-%S_%Z")


def sanitize_title(title: str, max_length: int = 50) -> str:
    """
    清理字符串，确保可安全用作文件名，并限制长度。

    Args:
        title (str): 原始文件名
        max_length (int): 文件名的最大长度

    Returns:
        str: 清理后的文件名, 如果超过最大长度, 则截断并添加省略号
    """
    sanitized = re.sub(r'[\\/*?:"<>|]', "-", title).strip()
    if len(sanitized) > max_length:
        sanitized = sanitized[: max_length - 3].rstrip("-") + "..."
    return sanitized


def log_retry_attempt(retry_state: RetryCallState) -> None:
    logger.warning(
        f"重试次数: {retry_state.attempt_number}/{default_config.max_retries}"
    )
