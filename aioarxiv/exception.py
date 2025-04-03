from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Optional

from pydantic import BaseModel, HttpUrl


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

    def __init__(self, status_code: int, message: Optional[str] = None) -> None:
        self.status_code = status_code
        self.message = message or HTTPStatus(status_code).description
        super().__init__(self.message)


class RateLimitException(HTTPException):
    """Exception raised when API rate limit is reached.

    Args:
        retry_after: Optional number of seconds to wait before retrying.
    """

    def __init__(self, retry_after: Optional[int] = None) -> None:
        self.retry_after = retry_after
        super().__init__(429, "Too Many Requests")


class ValidationException(ArxivException):
    """Exception for data validation errors.

    Args:
        message: Error message.
        field_name: Name of the field that failed validation.
        input_value: Invalid input value.
        expected_type: Expected type for the field.
        model: Optional Pydantic model class.
        validation_errors: Optional dictionary of validation errors.
    """

    def __init__(
        self,
        message: str,
        field_name: str,
        input_value: Any,
        expected_type: type,
        model: Optional[type[BaseModel]] = None,
        validation_errors: Optional[dict] = None,
    ) -> None:
        self.field_name = field_name
        self.input_value = input_value
        self.expected_type = expected_type
        self.model = model
        self.validation_errors = validation_errors
        super().__init__(message)

    def __str__(self) -> str:
        error_msg = [
            f"Validation error for field '{self.field_name}':",
            f"Input value: {self.input_value!r}",
            f"Expected type: {self.expected_type.__name__}",
        ]

        if self.model:
            error_msg.append(f"Model: {self.model.__name__}")

        if self.validation_errors:
            error_msg.append("Detailed errors:")
            error_msg.extend(
                f"  - {key}: {err}" for key, err in self.validation_errors.items()
            )
        return "\n".join(error_msg)


class TimeoutException(ArxivException):
    """Exception for request timeouts.

    Args:
        timeout: Timeout duration in seconds.
        message: Optional error message.
        proxy: Optional proxy URL used.
        link: Optional target URL.
    """

    def __init__(
        self,
        timeout: float,
        message: Optional[str] = None,
        proxy: Optional[HttpUrl] = None,
        link: Optional[HttpUrl] = None,
    ) -> None:
        self.timeout = timeout
        self.proxy = proxy
        self.link = link
        self.message = message or f"Request timed out after {timeout} seconds"
        super().__init__(message)

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
class ConfigError:
    """Configuration error details.

    Attributes:
        property_name: Name of the problematic property.
        input_value: Invalid input value.
        expected_type: Expected type for the property.
        message: Error message.
    """

    property_name: str
    input_value: Any
    expected_type: type
    message: str


class ConfigurationError(ArxivException):
    """Exception for configuration errors.

    Args:
        message: Error message.
        property_name: Name of the problematic property.
        input_value: Invalid input value.
        expected_type: Expected type for the property.
        config_class: Optional configuration class.
    """

    def __init__(
        self,
        message: str,
        property_name: str,
        input_value: Any,
        expected_type: type,
        config_class: Optional[type] = None,
    ) -> None:
        self.property_name = property_name
        self.input_value = input_value
        self.expected_type = expected_type
        self.config_class = config_class
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        error_parts = [
            f"Configuration error for '{self.property_name}':",
            f"Input value: {self.input_value!r}",
            f"Expected type: {self.expected_type.__name__}",
            f"Message: {self.message}",
        ]

        if self.config_class:
            error_parts.append(f"Config class: {self.config_class.__name__}")

        return "\n".join(error_parts)


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
    field_name: Optional[str] = None
    value: Optional[Any] = None
    constraint: Optional[str] = None


class QueryBuildError(ArxivException):
    """Exception for query building errors.

    Args:
        message: Error message.
        context: Optional query context.
        original_error: Optional original exception.
    """

    def __init__(
        self,
        message: str,
        context: Optional[QueryContext] = None,
        original_error: Optional[Exception] = None,
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

    raw_content: Optional[str] = None
    position: Optional[int] = None
    element_name: Optional[str] = None
    namespace: Optional[str] = None


class ParserException(Exception):
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
        context: Optional[ParseErrorContext] = None,
        original_error: Optional[Exception] = None,
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


class SearchCompleteException(ArxivException):
    """Exception indicating search completion.

    Args:
        total_results: Total number of results found.
    """

    def __init__(self, total_results: int) -> None:
        self.total_results = total_results
        super().__init__(f"Search complete with {total_results} results")


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
