from collections.abc import AsyncGenerator
from pathlib import Path
from types import TracebackType
from typing import Optional

from aiohttp import ClientResponse

from ..config import ArxivConfig, default_config
from ..exception import (
    HTTPException,
    ParseErrorContext,
    ParserException,
    QueryBuildError,
    QueryContext,
    SearchCompleteException,
)
from ..models import Paper, SearchParams
from ..utils import logger
from ..utils.parser import ArxivParser
from ..utils.session import SessionManager
from .base import BaseSearchManager
from .downloader import ArxivDownloader
from .search import ArxivSearchManager


class ArxivClient:
    def __init__(
        self,
        config: Optional[ArxivConfig] = None,
        session_manager: Optional[SessionManager] = None,
        *,
        search_manager_class: type[BaseSearchManager] = ArxivSearchManager,
    ):
        self._config = config or default_config
        self._session_manager = session_manager or SessionManager(config=self._config)
        self._search_manager = search_manager_class(self)
        self._downloader = ArxivDownloader(self._session_manager)

    async def search(
        self,
        query: str,
        max_results: Optional[int] = None,
    ) -> AsyncGenerator[Paper, None]:
        """执行搜索"""
        params = SearchParams(query=query, max_results=max_results)

        try:
            async with self._session_manager:
                async for paper in self._search_manager.execute_search(params):
                    yield paper
        except SearchCompleteException:
            return

    async def _fetch_page(self, params: SearchParams, start: int) -> ClientResponse:
        """
        获取单页结果

        Args:
            params: 搜索参数
            start: 起始位置

        Returns:
            响应对象

        Raises:
            QueryBuildError: 如果构建查询参数失败
        """
        try:
            query_params = self._build_query_params(params, start)
            response = await self._session_manager.request(
                "GET", str(self._config.base_url), params=query_params
            )

            if response.status != 200:
                logger.error("搜索请求失败", extra={"status_code": response.status})
                raise HTTPException(response.status)

            return response

        except QueryBuildError:
            raise
        except Exception as e:
            logger.error("未预期的错误", exc_info=True)
            raise QueryBuildError(
                message="构建查询参数失败",
                context=QueryContext(
                    params={"query": params.query, "start": start},
                    field_name="query_params",
                ),
                original_error=e,
            )

    def _build_query_params(self, params: SearchParams, start: int) -> dict:
        """
        构建查询参数

        Args:
            params: 搜索参数
            start: 起始位置

        Returns:
            dict: 查询参数

        Raises:
            QueryBuildError: 如果构建查询参数失败
        """
        try:
            page_size = min(
                self._config.page_size,
                params.max_results - start if params.max_results else float("inf"),
            )

            query_params = {
                "search_query": params.query,
                "start": start,
                "max_results": page_size,
            }

            if params.sort_by:
                query_params["sortBy"] = params.sort_by.value

            if params.sort_order:
                query_params["sortOrder"] = params.sort_order.value

            return query_params

        except Exception as e:
            raise QueryBuildError(
                message="计算页面大小失败",
                context=QueryContext(
                    params={
                        "page_size": self._config.page_size,
                        "max_results": params.max_results,
                        "start": start,
                    },
                    field_name="page_size",
                ),
                original_error=e,
            )

    async def parse_response(self, response: ClientResponse) -> tuple[list[Paper], int]:
        """
        解析API响应

        Args:
            response: 响应对象

        Returns:
            解析后的论文列表和总结果数

        Raises:
            ParserException: 如果解析失败
        """
        content = await response.text()
        try:
            return await ArxivParser.parse_feed(content=content, url=str(response.url))
        except ParserException:
            raise
        except Exception as e:
            raise ParserException(
                url=str(response.url),
                message="解析响应失败",
                context=ParseErrorContext(raw_content=content),
                original_error=e,
            )

    async def download_paper(
        self, paper: Paper, filename: Optional[str] = None
    ) -> Path:
        """
        下载论文

        Args:
            paper: 论文对象
            filename: 文件名

        Returns:
            下载文件的存放路径
        """
        return await self._downloader.download_paper(str(paper.pdf_url), filename)

    async def close(self) -> None:
        """关闭客户端"""
        await self._session_manager.close()

    async def __aenter__(self) -> "ArxivClient":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.close()
