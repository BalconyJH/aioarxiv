from dataclasses import dataclass
from http import HTTPStatus
from typing import Any


class ArxivException(Exception):
    """Base exception class for arXiv operations."""

    def __str__(self) -> str:
        return super().__repr__()


class HTTPException(ArxivException):
    """Exception for HTTP request-related errors.

    Args:
        status_code: HTTP status code.
        message: Optional error message (defaults to HTTP status description).
    """

    status_code: int
    message: str

    def __init__(self, status_code: int, message: str | None = None) -> None:
        self.status_code = status_code
        if message is None:
            # Nonstandard codes (e.g. CDN 520/530) are not HTTPStatus members.
            try:
                message = HTTPStatus(status_code).description
            except ValueError:
                message = f"HTTP {status_code}"
        self.message = message
        super().__init__(self.message)


class RateLimitException(HTTPException):
    """Exception raised when the API rate limit is reached (HTTP 429).

    Args:
        retry_after: Optional number of seconds to wait before retrying,
            parsed from the ``Retry-After`` response header if present.
    """

    def __init__(self, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(429, "Too Many Requests")


class TimeoutException(ArxivException):
    """Exception for request timeouts.

    Args:
        timeout: Timeout duration in seconds.
        message: Optional error message.
        proxy: Optional proxy URL used.
        link: Optional target URL.
    """

    timeout: float
    message: str
    proxy: str | None
    link: str | None

    def __init__(
        self,
        timeout: float,
        message: str | None = None,
        proxy: str | None = None,
        link: str | None = None,
    ) -> None:
        self.timeout = timeout
        self.proxy = proxy
        self.link = link
        self.message = message or f"Request timed out after {timeout} seconds"
        super().__init__(self.message)

    def __str__(self) -> str:
        error_msg = [
            f"Request timed out after {self.timeout} seconds",
            self.message,
        ]

        if self.proxy:
            error_msg.append(f"Proxy: {self.proxy}")

        if self.link:
            error_msg.append(f"Link: {self.link}")

        return "\n".join(error_msg)


@dataclass
class QueryContext:
    """Context for query building operations.

    Attributes:
        params: Query parameters.
        field_name: Name of the problematic field.
        value: Problematic value.
        constraint: Violated constraint.
    """

    params: dict[str, Any]
    field_name: str | None = None
    value: Any | None = None
    constraint: str | None = None


class QueryBuildError(ArxivException):
    """Exception for query building errors.

    Also raised when the arXiv API itself rejects the query and reports the
    error through its Atom error entry.

    Args:
        message: Error message.
        context: Optional query context.
        original_error: Optional original exception.
    """

    def __init__(
        self,
        message: str,
        context: QueryContext | None = None,
        original_error: Exception | None = None,
    ) -> None:
        self.message = message
        self.context = context
        self.original_error = original_error
        super().__init__(message)

    def __str__(self) -> str:
        error_parts = [f"Query build error: {self.message}"]

        if self.context:
            if self.context.params:
                error_parts.append("Parameters:")
                error_parts.extend(
                    f"  • {k}: {v!r}" for k, v in self.context.params.items()
                )

            if self.context.field_name:
                error_parts.append(f"Problem field: {self.context.field_name}")

            if self.context.value is not None:
                error_parts.append(f"Problem value: {self.context.value!r}")

            if self.context.constraint:
                error_parts.append(f"Constraint: {self.context.constraint}")

        if self.original_error:
            error_parts.extend(
                [
                    f"Original error: {self.original_error!s}",
                    f"Original error type: {type(self.original_error).__name__}",
                ],
            )

        return "\n".join(error_parts)


@dataclass
class ParseErrorContext:
    """Context for parsing errors.

    Attributes:
        raw_content: Raw content being parsed.
        position: Error position in content.
        element_name: Name of problematic element.
        namespace: XML namespace.
    """

    raw_content: str | None = None
    position: int | None = None
    element_name: str | None = None
    namespace: str | None = None


class ParserException(ArxivException):
    """Exception for XML parsing errors.

    Args:
        url: URL being parsed.
        message: Error message.
        context: Optional parsing context.
        original_error: Optional original exception.
    """

    def __init__(
        self,
        url: str,
        message: str,
        context: ParseErrorContext | None = None,
        original_error: Exception | None = None,
    ) -> None:
        self.url = url
        self.message = message
        self.context = context
        self.original_error = original_error
        super().__init__(self.message)

    def __str__(self) -> str:
        parts = [f"Parse error: {self.message}", f"URL: {self.url}"]

        if self.context:
            if self.context.element_name:
                parts.append(f"Element: {self.context.element_name}")
            if self.context.namespace:
                parts.append(f"Namespace: {self.context.namespace}")
            if self.context.position is not None:
                parts.append(f"Position: {self.context.position}")
            if self.context.raw_content:
                parts.append(f"Raw content: \n{self.context.raw_content[:200]}...")

        if self.original_error:
            parts.append(f"Original error: {self.original_error!s}")

        return "\n".join(parts)


class PaperDownloadException(ArxivException):
    """Exception for paper download failures.

    Args:
        message: Error message describing the failure.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return f"Paper download error: {self.message}"
