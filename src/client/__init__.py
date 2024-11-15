# import sys
# from collections.abc import AsyncGenerator
# from dataclasses import dataclass
# from types import TracebackType
# from typing import Optional
#
# from aiohttp import ClientError, ClientResponse
# from anyio import create_memory_object_stream, create_task_group, sleep
# from tenacity import (
#     retry,
#     retry_if_exception_type,
#     stop_after_attempt,
#     wait_exponential,
# )
#
# from ..config import ArxivConfig, default_config
# from ..exception import (
#     HTTPException,
#     ParseErrorContext,
#     ParserException,
#     QueryBuildError,
#     QueryContext, SearchCompleteException,
# )
# from ..models import Paper, SearchParams
# from ..utils.log import logger
# from ..utils.parser import ArxivParser
# from ..utils.session import SessionManager
#
#
# class ArxivClient:
#     """
#     arXiv API异步客户端
#
#     用于执行arXiv API搜索请求。
#
#     Attributes:
#         _config: arXiv API配置
#         _session_manager: 会话管理器
#     """
#     def __init__(
#             self,
#             config: Optional[ArxivConfig] = None,
#             session_manager: Optional[SessionManager] = None,
#     ):
#         self._config = config or default_config
#         self._session_manager = session_manager or SessionManager()
#
#     async def search(
#             self,
#             query: str,
#             max_results: Optional[int] = None,
#     ) -> AsyncGenerator[Paper, None]:
#         """
#         执行搜索
#
#         Args:
#             query: 搜索查询
#             max_results: 最大结果数
#
#         Yields:
#             Paper: 论文对象
#         """
#         params = SearchParams(query=query, max_results=max_results)
#
#         async with self._session_manager:
#             async for paper in self._iter_papers(params):
#                 yield paper
#
#     def _calculate_page_size(self, start: int, max_results: Optional[int]) -> int:
#         """计算页面大小"""
#         if max_results is None:
#             return self._config.page_size
#         return min(self._config.page_size, max_results - start)
#
#     def _has_more_results(
#             self, start: int, total: float, max_results: Optional[int]
#     ) -> bool:
#         """检查是否有更多结果"""
#         max_total = int(total) if total != float("inf") else sys.maxsize
#         max_allowed = max_results or sys.maxsize
#         return start < min(max_total, max_allowed)
#
#     async def _iter_papers(self, params: SearchParams) -> AsyncGenerator[Paper, None]:
#         """迭代获取论文
#
#         Args:
#             params: 搜索参数
#
#         Yields:
#             Paper: 论文对象
#         """
#         start = 0
#         total_results = float("inf")
#         concurrent_limit = min(
#             self._config.max_concurrent_requests,
#             self._config.rate_limit_calls
#         )
#         results_count = 0
#         first_batch = True
#
#         logger.info("开始搜索", extra={
#             "query": params.query,
#             "max_results": params.max_results,
#             "concurrent_limit": concurrent_limit
#         })
#
#         send_stream, receive_stream = create_memory_object_stream[
#             tuple[list[Paper], int]
#         ](max_buffer_size=concurrent_limit)
#
#         @retry(
#             retry=retry_if_exception_type((ClientError, TimeoutError, OSError)),
#             stop=stop_after_attempt(self._config.max_retries),
#             wait=wait_exponential(
#                 multiplier=self._config.rate_limit_period,
#                 min=self._config.min_wait,
#                 max=self._config.timeout
#             ),
#         )
#         async def fetch_page(page_start: int):
#             """获取单页并发送结果"""
#             try:
#                 async with self._session_manager.rate_limited_context():
#                     response = await self._fetch_page(params, page_start)
#                     result = await self.parse_response(response)
#                     await send_stream.send(result)
#             except Exception as e:
#                 logger.error(f"获取页面失败: {e!s}", extra={"page": page_start})
#                 raise
#
#         async def fetch_batch(batch_start: int, size: int):
#             """批量获取论文"""
#             try:
#                 async with create_task_group() as batch_tg:
#                     # 计算这一批次应获取的数量
#                     batch_size = min(
#                         size,
#                         self._config.page_size,
#                         params.max_results - results_count if params.max_results else size
#                     )
#
#                     # 计算结束位置
#                     end = min(
#                         batch_start + batch_size,
#                         int(total_results) if total_results != float(
#                             "inf") else sys.maxsize
#                     )
#
#                     # 启动单页获取任务
#                     for offset in range(batch_start, end):
#                         if params.max_results and offset >= params.max_results:
#                             break
#                         batch_tg.start_soon(fetch_page, offset)
#             except Exception as e:
#                 logger.error(
#                     "批量获取失败",
#                     extra={
#                         "start": batch_start,
#                         "size": size,
#                         "error": str(e)
#                     }
#                 )
#                 raise
#
#         try:
#             async with create_task_group() as tg:
#                 tg.start_soon(
#                     fetch_batch,
#                     start,
#                     concurrent_limit * self._config.page_size
#                 )
#
#                 async for papers, total in receive_stream:
#                     total_results = total
#
#                     if first_batch and total == 0:
#                         logger.info("未找到结果", extra={"query": params.query})
#                         raise SearchCompleteException(0)
#                     first_batch = False
#
#                     for paper in papers:
#                         yield paper
#                         results_count += 1
#                         if params.max_results and results_count >= params.max_results:
#                             raise SearchCompleteException(results_count)
#
#                     start += len(papers)
#                     if start < min(
#                             int(total_results) if total_results != float(
#                                 "inf") else sys.maxsize,
#                             params.max_results or sys.maxsize
#                     ):
#                         await sleep(self._config.rate_limit_period)
#                         tg.start_soon(
#                             fetch_batch,
#                             start,
#                             concurrent_limit * self._config.page_size
#                         )
#         finally:
#             await receive_stream.aclose()
#             logger.info("搜索结束", extra={"total_results": results_count})
#
#     async def _fetch_page(self, params: SearchParams, start: int) -> ClientResponse:
#         """
#         获取单页结果
#
#         Args:
#             params: 搜索参数
#             start: 起始位置
#
#         Returns:
#             ClientResponse: API响应
#
#         Raises:
#             QueryBuildError: 如果构建查询参数失败
#             HTTPException: 如果请求失败
#         """
#         try:
#             # 构建查询参数
#             query_params = self._build_query_params(params, start)
#
#             # 发送请求
#             response = await self._session_manager.request(
#                 "GET", str(self._config.base_url), params=query_params
#             )
#
#             if response.status != 200:
#                 logger.error(
#                     "搜索请求失败", extra={"status_code": response.status}
#                 )
#                 raise HTTPException(response.status)
#
#             return response
#
#         except QueryBuildError as e:
#             logger.error("查询参数构建失败", extra={"error_context": e.context})
#             raise
#         except Exception as e:
#             logger.error("未预期的错误", exc_info=True)
#             raise QueryBuildError(
#                 message="构建查询参数失败",
#                 context=QueryContext(
#                     params={"query": params.query, "start": start},
#                     field_name="query_params",
#                 ),
#                 original_error=e,
#             )
#
#     def _build_query_params(self, params: SearchParams, start: int) -> dict:
#         """
#         构建查询参数
#
#         Args:
#             params: 搜索参数
#             start: 起始位置
#
#         Returns:
#             dict: 查询参数
#
#         Raises:
#             QueryBuildError: 如果构建查询参数失败
#         """
#         if not params.query:
#             raise QueryBuildError(
#                 message="搜索查询不能为空",
#                 context=QueryContext(
#                     params={"query": None}, field_name="query", constraint="required"
#                 ),
#             )
#
#         if start < 0:
#             raise QueryBuildError(
#                 message="起始位置不能为负数",
#                 context=QueryContext(
#                     params={"start": start},
#                     field_name="start",
#                     constraint="non_negative",
#                 ),
#             )
#
#         try:
#             page_size = min(
#                 self._config.page_size,
#                 params.max_results - start if params.max_results else float("inf"),
#             )
#         except Exception as e:
#             raise QueryBuildError(
#                 message="计算页面大小失败",
#                 context=QueryContext(
#                     params={
#                         "page_size": self._config.page_size,
#                         "max_results": params.max_results,
#                         "start": start,
#                     },
#                     field_name="page_size",
#                 ),
#                 original_error=e,
#             )
#
#         query_params = {
#             "search_query": params.query,
#             "start": start,
#             "max_results": page_size,
#         }
#
#         if params.sort_by:
#             query_params["sortBy"] = params.sort_by.value
#
#         if params.sort_order:
#             query_params["sortOrder"] = params.sort_order.value
#
#         return query_params
#
#     async def parse_response(
#             self,
#             response: ClientResponse
#     ) -> tuple[list[Paper], int]:
#         """解析API响应"""
#         content = await response.text()
#         try:
#             return await ArxivParser.parse_feed(
#                 content=content,
#                 url=str(response.url)
#             )
#         except ParserException:
#             raise
#         except Exception as e:
#             raise ParserException(
#                 url=str(response.url),
#                 message="解析响应失败",
#                 context=ParseErrorContext(raw_content=content),
#                 original_error=e,
#             )
#
#     async def __aenter__(self) -> "ArxivClient":
#         return self
#
#     async def __aexit__(
#             self,
#             exc_type: Optional[type[BaseException]],
#             exc_val: Optional[BaseException],
#             exc_tb: Optional[TracebackType]
#     ) -> None:
#         await self._session_manager.close()
#
#     async def close(self) -> None:
#         """关闭客户端并清理资源"""
#         await self._session_manager.close()
