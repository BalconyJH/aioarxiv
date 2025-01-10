from collections.abc import AsyncGenerator
from typing import Any

import pytest
from pytest_mock import MockerFixture

from aioarxiv.client.downloader import ArxivDownloader
from aioarxiv.models import Paper


class MockResponse:
    """模拟HTTP响应对象"""

    def __init__(self, status: int = 200, content: bytes = b"mock_pdf_content") -> None:
        """
        初始化mock响应

        Args:
            status: HTTP状态码
            content: 响应内容
        """
        self.status = status
        self._content = content

    @property
    def content(self) -> Any:
        """
        模拟响应内容流

        Returns:
            Any: 异步内容生成器
        """
        outer_content = self._content

        class MockStreamReader:
            @staticmethod
            async def iter_chunked(size: int) -> AsyncGenerator[bytes, None]:
                yield outer_content

        return MockStreamReader()


@pytest.mark.asyncio
async def test_single_download(
    mock_downloader: ArxivDownloader,
    sample_paper: Paper,
    mocker: MockerFixture,
) -> None:
    mock_content = b"mock_pdf_content"
    mock_response = MockResponse(status=200, content=mock_content)
    request_mock = mocker.patch.object(
        mock_downloader.session_manager, "request", new_callable=mocker.AsyncMock
    )
    request_mock.return_value = mock_response

    filename = "test_paper.pdf"
    await mock_downloader.download_paper(sample_paper, filename)

    expected_path = mock_downloader.download_dir / filename
    assert expected_path.exists(), "Downloaded file should exist"

    content = expected_path.read_bytes()
    assert content == mock_content, "File content should match mock content"

    request_mock.assert_called_once_with("GET", str(sample_paper.pdf_url))
