from http import HTTPStatus

import pytest

from aioarxiv.exception import (
    ArxivException,
    HTTPException,
    PaperDownloadException,
    ParseErrorContext,
    ParserException,
    QueryBuildError,
    QueryContext,
    RateLimitException,
    TimeoutException,
)


def test_arxiv_exception_uses_exception_repr():
    error = ArxivException("boom")

    assert str(error) == "ArxivException('boom')"


@pytest.mark.parametrize(
    ("status_code", "expected_message"),
    [
        (HTTPStatus.NOT_FOUND, HTTPStatus.NOT_FOUND.description),
        (530, "HTTP 530"),
    ],
)
def test_http_exception_uses_default_message(status_code, expected_message):
    error = HTTPException(status_code)

    assert error.status_code == status_code
    assert error.message == expected_message
    assert error.args == (expected_message,)


def test_http_exception_preserves_explicit_message():
    error = HTTPException(503, "Upstream unavailable")

    assert error.message == "Upstream unavailable"
    assert str(error) == "HTTPException('Upstream unavailable')"


@pytest.mark.parametrize("retry_after", [None, 30])
def test_rate_limit_exception_carries_retry_delay(retry_after):
    error = RateLimitException(retry_after)

    assert error.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert error.message == "Too Many Requests"
    assert error.retry_after == retry_after


def test_timeout_exception_renders_request_context():
    error = TimeoutException(
        2.5,
        message="Upstream stalled",
        proxy="http://proxy.example",
        link="https://example.test/feed",
    )

    assert str(error) == (
        "Request timed out after 2.5 seconds\n"
        "Upstream stalled\n"
        "Proxy: http://proxy.example\n"
        "Link: https://example.test/feed"
    )


def test_timeout_exception_builds_default_message():
    error = TimeoutException(3)

    assert error.message == "Request timed out after 3 seconds"
    assert error.proxy is None
    assert error.link is None


def test_query_build_error_renders_full_context():
    original_error = ValueError("bad integer")
    context = QueryContext(
        params={"query": "all:electron", "start": 5},
        field_name="start",
        value=5,
        constraint="must be zero",
    )
    error = QueryBuildError("Invalid parameters", context, original_error)

    assert str(error) == (
        "Query build error: Invalid parameters\n"
        "Parameters:\n"
        "  • query: 'all:electron'\n"
        "  • start: 5\n"
        "Problem field: start\n"
        "Problem value: 5\n"
        "Constraint: must be zero\n"
        "Original error: bad integer\n"
        "Original error type: ValueError"
    )


def test_query_build_error_without_optional_context():
    error = QueryBuildError("Malformed query")

    assert str(error) == "Query build error: Malformed query"


def test_parser_exception_renders_context_and_truncates_raw_content():
    raw_content = "x" * 250
    original_error = ValueError("broken XML")
    context = ParseErrorContext(
        raw_content=raw_content,
        position=12,
        element_name="entry",
        namespace="atom",
    )
    error = ParserException(
        "https://example.test/feed",
        "Invalid feed",
        context,
        original_error,
    )

    assert str(error) == "\n".join(
        [
            "Parse error: Invalid feed",
            "URL: https://example.test/feed",
            "Element: entry",
            "Namespace: atom",
            "Position: 12",
            f"Raw content: \n{'x' * 200}...",
            "Original error: broken XML",
        ]
    )


def test_parser_exception_without_optional_context():
    error = ParserException("https://example.test/feed", "Invalid feed")

    assert str(error) == ("Parse error: Invalid feed\nURL: https://example.test/feed")


def test_paper_download_exception_renders_message():
    error = PaperDownloadException("HTTP status 503")

    assert str(error) == "Paper download error: HTTP status 503"
