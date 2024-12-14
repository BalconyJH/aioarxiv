from pathlib import Path
from types import TracebackType
from typing import Optional

import aiofiles
from platformdirs import user_cache_path, user_documents_path

from aioarxiv.utils import get_project_root
from aioarxiv.utils.log import logger
from aioarxiv.utils.session import SessionManager


def cache_path() -> Path:
    """
    获取缓存目录

    Returns:
        Path: 缓存目录
    """
    return user_cache_path(
        "aioarxiv",
        ensure_exists=True,
    )


def documents_path() -> Path:
    """
    获取下载目录

    Returns:
        Path: 下载目录
    """
    path = user_documents_path() / "aioarxiv"
    path.mkdir(parents=True, exist_ok=True)
    return path


class ArxivDownloader:
    """arXiv论文下载器"""

    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        download_dir: Optional[Path] = None,
    ) -> None:
        """
        初始化下载器

        Args:
            session_manager: 会话管理器,可选
            download_dir: 下载目录,可选
        """
        project_root = get_project_root()
        self._session_manager = session_manager
        self._own_session = False
        self.download_dir = (
            Path(download_dir) if download_dir else project_root / "downloads"
        )
        self.download_dir.mkdir(parents=True, exist_ok=True)

    @property
    def session_manager(self) -> SessionManager:
        """懒加载会话管理器"""
        if self._session_manager is None:
            self._session_manager = SessionManager()
            self._own_session = True
        return self._session_manager

    async def download_paper(
        self,
        pdf_url: str,
        filename: Optional[str] = None,
    ) -> Path:
        """下载论文PDF文件"""
        if not filename:
            filename = pdf_url.split("/")[-1]
            if not filename.endswith(".pdf"):
                filename += ".pdf"

        file_path = self.download_dir / filename
        temp_path = file_path.with_suffix(f"{file_path.suffix}.tmp")

        logger.info(f"开始下载论文: {pdf_url}")
        try:
            async with self.session_manager.rate_limited_context():
                # 先获取响应
                response = await self.session_manager.request("GET", pdf_url)
                # 然后使用 async with 管理响应生命周期
                async with response:
                    response.raise_for_status()

                    async with aiofiles.open(temp_path, "wb") as f:
                        total_size = int(response.headers.get("content-length", 0))
                        downloaded_size = 0

                        async for chunk, _ in response.content.iter_chunks():
                            if chunk:
                                await f.write(chunk)
                                downloaded_size += len(chunk)

                    if 0 < total_size != downloaded_size:
                        msg = (
                            f"下载不完整: 预期 {total_size} 字节, "
                            f"实际下载 {downloaded_size} 字节"
                        )
                        raise RuntimeError(msg)

                temp_path.rename(file_path)

            logger.info(f"下载完成: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"下载失败: {e!s}")
            # 清理临时文件和目标文件
            if temp_path.exists():
                temp_path.unlink()
            if file_path.exists():
                file_path.unlink()
            raise

    async def __aenter__(self) -> "ArxivDownloader":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if self._own_session and self._session_manager:
            await self._session_manager.close()
