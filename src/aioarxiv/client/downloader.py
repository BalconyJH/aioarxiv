import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import aiofiles
from platformdirs import user_documents_path
from tenacity import retry, stop_after_attempt, wait_exponential

from aioarxiv.config import ArxivConfig, default_config
from aioarxiv.exception import PaperDownloadException
from aioarxiv.models import Paper, SearchResult
from aioarxiv.utils import format_datetime, log_retry_attempt, sanitize_title
from aioarxiv.utils.log import logger
from aioarxiv.utils.session import SessionManager


class DownloadTracker:
    """批量下载上下文"""

    def __init__(self, total: int, start_time: Optional[datetime] = None) -> None:
        self.total = total
        self.completed = 0
        self.failed = 0
        self.start_time = start_time or datetime.now(ZoneInfo(default_config.timezone))
        self.end_time: Optional[datetime] = None
        self._failed_papers: list[tuple[Paper, Exception]] = []

    def add_failed(self, paper: Paper, error: Exception) -> None:
        """记录下载失败的论文"""
        self.failed += 1
        self._failed_papers.append((paper, error))

    def add_completed(self) -> None:
        """记录完成下载"""
        self.completed += 1

    @property
    def progress(self) -> float:
        """下载进度"""
        return (self.completed + self.failed) / self.total * 100

    @property
    def failed_papers(self) -> list[tuple[Paper, Exception]]:
        """获取下载失败的论文列表"""
        return self._failed_papers


class ArxivDownloader:
    """arXiv论文下载器"""

    def __init__(
        self,
        session_manager: Optional[SessionManager] = None,
        download_dir: Optional[Path] = None,
        # cache_dir: Optional[Path] = None,
        config: Optional[ArxivConfig] = None,
    ) -> None:
        self._session_manager = session_manager
        self._download_dir = download_dir
        # self._cache_dir = cache_dir
        self._config = config or default_config
        self._semaphore = asyncio.Semaphore(self._config.max_concurrent_requests)

    @property
    def session_manager(self) -> SessionManager:
        """懒加载会话管理器"""
        if self._session_manager is None:
            self._session_manager = SessionManager()
        return self._session_manager

    @property
    def download_dir(self) -> Path:
        """下载目录"""
        if self._download_dir is None:
            self._download_dir = user_documents_path() / "aioarxiv"
        self._download_dir.mkdir(parents=True, exist_ok=True)
        return self._download_dir

    # @property
    # def cache_dir(self) -> Path:
    #     """缓存目录"""
    #     if self._cache_dir is None:
    #         self._cache_dir = user_cache_path("aioarxiv")
    #     self._cache_dir.mkdir(parents=True, exist_ok=True)
    #     return self._cache_dir

    @staticmethod
    def file_name(paper: Paper) -> str:
        """生成文件名"""
        file_name = f"{paper.info.title} {format_datetime(paper.info.updated)}"
        return f"{sanitize_title(file_name)}.pdf"

    def _prepare_paths(
        self, paper: Paper, filename: Optional[str] = None
    ) -> tuple[Path, Path]:
        """准备下载和临时文件路径"""
        name = filename or self.file_name(paper)
        file_path = self.download_dir / name
        temp_path = file_path.with_suffix(".tmp")
        return file_path, temp_path

    async def _download_to_temp(self, url: str, temp_path: Path) -> None:
        """下载内容到临时文件"""
        async with self._semaphore:
            response = await self.session_manager.request("GET", url)
            if response.status != 200:
                raise PaperDownloadException(f"HTTP status {response.status}")

            async with aiofiles.open(temp_path, "wb") as f:
                async for chunk in response.content.iter_chunked(8192):
                    await f.write(chunk)  # type: ignore

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry_error_callback=log_retry_attempt,
    )
    async def download_paper(
        self, paper: Paper, filename: Optional[str] = None
    ) -> None:
        """
        下载单篇论文

        Args:
            paper: 论文对象
            filename: 文件名

        Raises:
            PaperDownloadException: 如果下载失败
        """
        file_path, temp_path = self._prepare_paths(paper, filename)
        logger.info(f"开始下载论文: {paper.pdf_url}")

        try:
            await self._download_to_temp(str(paper.pdf_url), temp_path)
            temp_path.rename(file_path)
            logger.info(f"下载完成: {file_path}")
        except Exception as e:
            logger.error(f"下载失败: {e}")
            temp_path.unlink(missing_ok=True)
            file_path.unlink(missing_ok=True)
            raise PaperDownloadException(f"下载失败: {e}") from e

    async def batch_download(
        self,
        search_result: SearchResult,
    ) -> DownloadTracker:
        """
        批量下载论文

        Args:
            search_result: 搜索结果

        Returns:
            DownloadTracker: 下载上下文
        """
        context = DownloadTracker(len(search_result.papers))
        tasks = []

        for paper in search_result.papers:
            if paper.pdf_url:
                tasks.append(
                    asyncio.create_task(self._download_with_context(paper, context))
                )
            else:
                context.add_failed(paper, ValueError("No PDF URL available"))

        await asyncio.gather(*tasks)
        context.end_time = datetime.now(ZoneInfo(default_config.timezone))
        return context

    async def _download_with_context(
        self, paper: Paper, context: DownloadTracker
    ) -> None:
        """
        下载单篇论文并更新上下文

        Args:
            paper: 论文对象
            context: 下载上下文
        """
        try:
            await self.download_paper(paper, f"{paper.info.id}.pdf")
            context.add_completed()
        except Exception as e:
            context.add_failed(paper, e)
            logger.error(
                f"论文 {paper.info.id} 下载失败: {e!s}",
                extra={"paper_id": paper.info.id},
            )
