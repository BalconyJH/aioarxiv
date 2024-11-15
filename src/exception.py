from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Optional

from pydantic import BaseModel, HttpUrl


class ArxivException(Exception):
    """基础异常类"""

    def __str__(self) -> str:
        return super().__repr__()


class HTTPException(ArxivException):
    """HTTP 请求相关异常"""

    def __init__(self, status_code: int, message: Optional[str] = None):
        self.status_code = status_code
        self.message = message or HTTPStatus(status_code).description
        super().__init__(self.message)


class RateLimitException(HTTPException):
    """达到 API 速率限制时的异常"""

    def __init__(self, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        super().__init__(429, "Too Many Requests")


class ValidationException(ArxivException):
    """数据验证异常"""

    def __init__(
        self,
        message: str,
        field_name: str,
        input_value: Any,
        expected_type: type,
        model: Optional[type[BaseModel]] = None,
        validation_errors: Optional[dict] = None,
    ):
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
            for key, err in self.validation_errors.items():
                error_msg.append(f"  - {key}: {err}")

        return "\n".join(error_msg)


class TimeoutException(ArxivException):
    """请求超时异常"""

    def __init__(
        self,
        timeout: float,
        message: Optional[str] = None,
        proxy: Optional[HttpUrl] = None,
        link: Optional[HttpUrl] = None,
    ):
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


class RetryError(ArxivException):
    """重试次数用尽异常"""

    def __init__(self, attempts: int, last_error: Exception):
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Failed after {attempts} attempts. Last error: {last_error}")


@dataclass
class ConfigError:
    """配置错误详情"""

    property_name: str
    input_value: Any
    expected_type: type
    message: str


class ConfigurationError(ArxivException):
    """配置错误异常"""

    def __init__(
        self,
        message: str,
        property_name: str,
        input_value: Any,
        expected_type: type,
        config_class: Optional[type] = None,
    ):
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
    """查询构建上下文"""

    params: dict[str, Any]  # 查询参数
    field_name: Optional[str] = None  # 出错的字段
    value: Optional[Any] = None  # 问题值
    constraint: Optional[str] = None  # 违反的约束


class QueryBuildError(ArxivException):
    """查询构建错误"""

    def __init__(
        self,
        message: str,
        context: Optional[QueryContext] = None,
        original_error: Optional[Exception] = None,
    ):
        self.message = message
        self.context = context
        self.original_error = original_error
        super().__init__(message)

    def __str__(self) -> str:
        parts = [f"查询构建错误: {self.message}"]

        if self.context:
            parts.append("查询参数:")
            for k, v in self.context.params.items():
                parts.append(f"  {k}: {v}")

            if self.context.field_name:
                parts.append(f"问题字段: {self.context.field_name}")
            if self.context.value is not None:
                parts.append(f"问题值: {self.context.value}")
            if self.context.constraint:
                parts.append(f"违反约束: {self.context.constraint}")

        if self.original_error:
            parts.append(f"原始错误: {self.original_error!s}")

        return "\n".join(parts)


@dataclass
class ParseErrorContext:
    """解析错误上下文"""

    raw_content: Optional[str] = None
    position: Optional[int] = None
    element_name: Optional[str] = None
    namespace: Optional[str] = None


class ParserException(Exception):
    """XML解析异常"""

    def __init__(
        self,
        url: str,
        message: str,
        context: Optional[ParseErrorContext] = None,
        original_error: Optional[Exception] = None,
    ):
        self.url = url
        self.message = message
        self.context = context
        self.original_error = original_error
        super().__init__(self.message)

    def __str__(self) -> str:
        parts = [f"解析错误: {self.message}", f"URL: {self.url}"]

        if self.context:
            if self.context.element_name:
                parts.append(f"元素: {self.context.element_name}")
            if self.context.namespace:
                parts.append(f"命名空间: {self.context.namespace}")
            if self.context.position is not None:
                parts.append(f"位置: {self.context.position}")
            if self.context.raw_content:
                parts.append(f"原始内容: \n{self.context.raw_content[:200]}...")

        if self.original_error:
            parts.append(f"原始错误: {self.original_error!s}")

        return "\n".join(parts)

class SearchCompleteException(ArxivException):
    """搜索完成异常"""
    def __init__(self, total_results: int):
        self.total_results = total_results
        super().__init__(f"搜索完成,共获取{total_results}条结果")
