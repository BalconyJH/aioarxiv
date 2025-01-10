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
    Create request tracing configuration.

    Returns:
        aiohttp.TraceConfig: Request tracing configuration object.
    """

    async def _on_request_start(
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceRequestStartParams,
    ) -> None:
        """
        Callback executed when a request starts.

        Args:
            session (aiohttp.ClientSession): The client session.
            trace_config_ctx (SimpleNamespace): Trace configuration context.
            params (aiohttp.TraceRequestStartParams): Request start parameters.
        """
        logger.debug(f"Starting request: {params.method} {params.url}")
        trace_config_ctx.start_time = monotonic()

    async def _on_request_end(
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceRequestEndParams,
    ) -> None:
        """
        Callback executed when a request ends.

        Args:
            session (aiohttp.ClientSession): The client session.
            trace_config_ctx (SimpleNamespace): Trace configuration context.
            params (aiohttp.TraceRequestEndParams): Request end parameters.
        """
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
    Create a parsing exception for XML data parsing errors.

    Args:
        data (ET.Element): The data that failed to parse.
        url (Optional[str]): The request URL.
        message (Optional[str], optional): Exception message. Defaults to None.
        namespace (Optional[str], optional): XML namespace. Defaults to None.
        error (Optional[Exception], optional): Original exception. Defaults to None.

    Returns:
        ParserException: The created parsing exception.
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
    Calculate page size constrained by configuration page size and maximum results.

    Args:
        config_page_size (int): Configured page size.
        start (int): Starting position.
        max_results (Optional[int]): Maximum number of results.

    Returns:
        int: Calculated page size.
    """
    if max_results is None:
        return config_page_size

    return min(config_page_size, max_results - start)


def format_datetime(dt: datetime) -> str:
    """
    Format datetime to string.

    Args:
        dt (datetime): Datetime object to format.

    Returns:
        str: Formatted datetime string in format: %Y-%m-%d_%H-%M-%S_%Z
            (e.g., 2024-03-21_15-30-00_CST).

    Examples:
        >>> format_datetime(datetime(2024, 3, 21, 15, 30, 0))
        '2024-03-21_15-30-00_CST'
    """
    local_dt = dt.astimezone(ZoneInfo(default_config.timezone))
    return local_dt.strftime("%Y-%m-%d_%H-%M-%S_%Z")


def sanitize_title(title: str, max_length: int = 50) -> str:
    """
    Sanitize string to make it safe for use as a filename and limit its length.

    Sanitization rules:
    - Replace invalid characters with hyphens
    - Remove leading and trailing hyphens
    - Remove redundant hyphens
    - Truncate to max_length and append ellipsis if too long

    Args:
        title (str): The original title/filename to sanitize
        max_length (int, optional): Maximum length of the sanitized filename.
        Defaults to 50. If exceeded, the string will be truncated and '...' appended.

    Returns:
        str: The sanitized filename. If length exceeds max_length, returns truncated
        string with '...' appended.

    Examples:
        >>> sanitize_title("file/with*invalid:chars")
        'file-with-invalid-chars'
        >>> sanitize_title("very...long...title", max_length=10)
        'very-lo...'
    """
    # Strip whitespace and replace invalid chars with single hyphen
    sanitized = re.sub(r'[\\/*?:"<>|]+', "-", title.strip()).strip("-")

    # Truncate and append ellipsis if too long
    if len(sanitized) > max_length:
        sanitized = f"{sanitized[: max_length - 3].rstrip('-')}..."

    return sanitized


def log_retry_attempt(retry_state: RetryCallState) -> None:
    """
    Log retry attempt information.

    Args:
        retry_state (RetryCallState): Current retry state containing attempt
            information.

    Examples:
        >>> log_retry_attempt(RetryCallState(attempt_number=2))
        WARNING:root:retry times: 2/3
    """
    logger.warning(
        f"retry times: {retry_state.attempt_number}/{default_config.max_retries}"
    )
