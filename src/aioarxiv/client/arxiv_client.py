from pathlib import Path
from typing import Optional
from datetime import datetime
from types import TracebackType
from collections.abc import AsyncGenerator

from aiohttp import ClientResponse

from .downloader import ArxivDownloader
from ..utils.session import SessionManager
from ..utils import logger, calculate_page_size
from ..config import ArxivConfig, default_config
from ..utils.parser import RootParser, ArxivParser
from ..exception import QueryContext, HTTPException, QueryBuildError
from ..models import Paper, SortOrder, SearchParams, SearchResult, SortCriterion


class ArxivClient:
    def __init__(
        self,
        config: Optional[ArxivConfig] = None,
        session_manager: Optional[SessionManager] = None,
    ):
        self._config = config or default_config
        self._session_manager = session_manager or SessionManager(config=self._config)
        self._downloader = ArxivDownloader(self._session_manager)

    def _build_search_metadata(
        self,
        searchresult: SearchResult,
        page: int,
        batch_size: int,
        papers: list[Paper],
    ) -> SearchResult:
        """更新搜索结果元数据"""
        has_next = searchresult.total_result > (page * batch_size)
        return searchresult.model_copy(
            update={
                "papers": papers,
                "page": page,
                "has_next": has_next,
                "metadata": searchresult.metadata.model_copy(
                    update={
                        "end_time": datetime.now(),
                        "pagesize": self._config.page_size,
                        "source": "arxiv",
                    }
                ),
            }
        )

    @staticmethod
    def _should_continue(
        total_yielded: int,
        max_results: Optional[int],
        total_result: int,
        page: int,
        batch_size: int,
    ) -> bool:
        """检查是否继续获取下一页"""
        if max_results and total_yielded >= max_results:
            return False
        return total_result > page * batch_size

    async def search(
        self,
        query: str,
        id_list: Optional[list[str]] = None,
        max_results: Optional[int] = None,
        sort_by: Optional[SortCriterion] = None,
        sort_order: Optional[SortOrder] = None,
    ) -> AsyncGenerator[SearchResult, None]:
        """执行arxiv搜索并返回结构化结果"""
        params = SearchParams(
            query=query,
            id_list=id_list,
            max_results=max_results,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        total_yielded = 0
        page = 1

        while True:
            batch_size = calculate_page_size(
                self._config.page_size, params.start, params.max_results
            )
            params.start = (page - 1) * batch_size

            response = await self._fetch_page(params)
            searchresult = RootParser(await response.text()).build_search_result(
                query_params=params,
            )
            papers = await self.parse_response(response)

            if not papers:
                break

            yield self._build_search_metadata(searchresult, page, batch_size, papers)

            total_yielded += len(papers)
            if not self._should_continue(
                total_yielded, max_results, searchresult.total_result, page, batch_size
            ):
                break

            page += 1

    async def _fetch_page(self, params: SearchParams) -> ClientResponse:
        """
        获取单页结果

        Args:
            params: 搜索参数

        Returns:
            响应对象

        Raises:
            QueryBuildError: 如果构建查询参数失败
        """
        query_params = self._build_query_params(params)
        response = await self._session_manager.request(
            "GET", str(self._config.base_url), params=query_params
        )

        if response.status != 200:
            logger.error(f"搜索请求失败, HTTP状态码: {response.status}")
            raise HTTPException(response.status)

        return response

    def _build_query_params(self, params: SearchParams) -> dict:
        """
        构建查询参数

        Args:
            params: 搜索参数模型

        Returns:
            dict: 查询参数

        Raises:
            QueryBuildError: 如果构建查询参数失败
        """
        try:
            page_size = calculate_page_size(
                self._config.page_size, params.start, params.max_results
            )

            query_params = {
                "search_query": params.query,
                "start": params.start,
                "max_results": page_size,
            }

            if params.id_list:
                query_params["id_list"] = ",".join(params.id_list)

            if params.sort_by:
                query_params["sortBy"] = params.sort_by.value

            if params.sort_order:
                query_params["sortOrder"] = params.sort_order.value

            return query_params

        except Exception as e:
            raise QueryBuildError(
                message="构建查询参数失败",
                context=QueryContext(
                    params={
                        "page_size": self._config.page_size,
                        "max_results": params.max_results,
                        "start": params.start,
                        "id_list": params.id_list,
                    },
                    field_name="query_params",
                ),
                original_error=e,
            ) from e

    async def parse_response(self, response: ClientResponse) -> list[Paper]:
        """
        解析API响应

        Args:
            response: 响应对象

        Returns:
            解析后的论文列表和总结果数

        Raises:
            ParserException: 如果解析失败
        """
        text = await response.text()
        return ArxivParser(text, response).parse_feed()

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
