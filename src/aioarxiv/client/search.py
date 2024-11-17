import sys
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from anyio import create_memory_object_stream, create_task_group, sleep

from ..exception import SearchCompleteException
from ..models import Paper, SearchParams
from ..utils.log import logger
from .base import BaseSearchManager, ClientProtocol


@dataclass
class SearchContext:
    """搜索上下文"""

    params: SearchParams
    start: int = 0
    total_results: float = float("inf")
    results_count: int = 0
    first_batch: bool = True

    def update_with_papers(self, papers: list[Paper]) -> None:
        """更新处理进度"""
        self.start += len(papers)
        self.results_count += len(papers)

    def should_continue(self) -> bool:
        """检查是否应继续处理"""
        max_total = (
            int(self.total_results)
            if self.total_results != float("inf")
            else sys.maxsize
        )
        max_allowed = self.params.max_results or sys.maxsize
        return self.start < min(max_total, max_allowed)

    def reached_limit(self) -> bool:
        """检查是否达到最大结果限制"""
        return (
            self.params.max_results is not None
            and self.results_count >= self.params.max_results
        )


class ArxivSearchManager(BaseSearchManager):
    def __init__(self, client: ClientProtocol):
        self.client = client
        self.config = client._config
        self.concurrent_limit = min(
            self.config.max_concurrent_requests, self.config.rate_limit_calls
        )

    def execute_search(self, params: SearchParams) -> AsyncGenerator[Paper, None]:
        """执行搜索"""

        async def search_implementation():
            ctx = SearchContext(params=params)
            send_stream, receive_stream = create_memory_object_stream[
                tuple[list[Paper], int]
            ](max_buffer_size=self.concurrent_limit)

            try:
                async with create_task_group() as tg:
                    await self._start_batch(tg, ctx, send_stream)
                    try:
                        async for paper in self._process_results(
                            ctx, tg, receive_stream
                        ):
                            yield paper
                    except SearchCompleteException:
                        # 正常的搜索完成,记录日志后继续传播
                        logger.info(f"搜索完成,共获取{ctx.results_count}条结果")
                        raise
            finally:
                # 确保资源清理
                await send_stream.aclose()
                await receive_stream.aclose()

        # 返回异步生成器
        return search_implementation()

    async def _start_batch(self, tg: Any, ctx: SearchContext, send_stream: Any) -> None:
        """启动批量获取"""
        tg.start_soon(
            self._fetch_batch,
            ctx,
            self.concurrent_limit * self.config.page_size,
            send_stream,
        )

    async def _fetch_batch(
        self, ctx: SearchContext, size: int, send_stream: Any
    ) -> None:
        """获取一批论文"""
        try:
            async with create_task_group() as batch_tg:
                batch_size = self._calculate_batch_size(ctx, size)
                end = self._calculate_batch_end(ctx, batch_size)

                for offset in range(ctx.start, end):
                    if ctx.params.max_results and offset >= ctx.params.max_results:
                        break
                    batch_tg.start_soon(self._fetch_page, offset, ctx, send_stream)
        except Exception as e:
            logger.error(
                "批量获取失败",
                extra={"start": ctx.start, "size": size, "error": str(e)},
            )
            raise

    def _calculate_batch_size(self, ctx: SearchContext, size: int) -> int:
        """计算批次大小"""
        return min(
            size,
            self.config.page_size,
            ctx.params.max_results - ctx.results_count
            if ctx.params.max_results
            else size,
        )

    def _calculate_batch_end(self, ctx: SearchContext, batch_size: int) -> int:
        """计算批次结束位置"""
        return min(
            ctx.start + batch_size,
            int(ctx.total_results)
            if ctx.total_results != float("inf")
            else sys.maxsize,
        )

    async def _fetch_page(
        self, offset: int, ctx: SearchContext, send_stream: Any
    ) -> None:
        """获取并发送单页数据"""
        try:
            response = await self.client._fetch_page(ctx.params, offset)
            result = await self.client.parse_response(response)
            await send_stream.send(result)
        except Exception as e:
            logger.error(f"获取页面失败: {e!s}", extra={"page": offset})
            raise

    async def _process_results(
        self, ctx: SearchContext, tg: Any, receive_stream: Any
    ) -> AsyncGenerator[Paper, None]:
        """处理搜索结果"""
        async for papers, total in receive_stream:
            # 更新总结果数
            ctx.total_results = total

            # 检查首次批次是否有结果
            if ctx.first_batch and total == 0:
                logger.info("未找到结果", extra={"query": ctx.params.query})
                raise SearchCompleteException(0)
            ctx.first_batch = False

            # 处理论文
            for paper in papers:
                yield paper
                ctx.results_count += 1
                if ctx.reached_limit():
                    raise SearchCompleteException(ctx.results_count)

            # 更新进度并启动下一批次
            ctx.start += len(papers)
            if ctx.should_continue():
                await sleep(self.config.rate_limit_period)
                await self._start_batch(tg, ctx, receive_stream)
