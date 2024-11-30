from pathlib import Path
from time import monotonic
from typing import Optional
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import aiohttp

from .log import logger
from ..exception import ParserException, ParseErrorContext


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
            f"{elapsed_time:.2f} seconds"
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


def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent.parent


def calculate_page_size(
    config_page_size: int, start: int, max_results: Optional[int]
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
