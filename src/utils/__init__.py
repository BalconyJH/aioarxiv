from pathlib import Path
from time import monotonic
from types import SimpleNamespace

import aiohttp

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
            f"{elapsed_time:.2f} seconds"
        )

    trace_config = aiohttp.TraceConfig()
    trace_config.on_request_start.append(_on_request_start)
    trace_config.on_request_end.append(_on_request_end)
    return trace_config

def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent.parent
