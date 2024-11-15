import sys
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Optional

from anyio import create_memory_object_stream, create_task_group, sleep

from ..config import ArxivConfig
from ..exception import SearchCompleteException
from ..models import Paper, SearchParams
from ..utils.log import logger


@dataclass
class BatchContext:
    """批处理上下文"""
    start: int
    size: int
    total_results: float
    results_count: int
    max_results: Optional[int]

class ResultProcessor:
    """处理搜索结果的处理器类"""
    def __init__(self, concurrent_limit: int, config: ArxivConfig):
        self.concurrent_limit = concurrent_limit
        self.config = config

    async def create_streams(self):
        """创建内存流"""
        return create_memory_object_stream[tuple[list[Paper], int]](
            max_buffer_size=self.concurrent_limit
        )

    def calculate_batch_size(self, ctx: BatchContext) -> int:
        """计算批次大小"""
        return min(
            ctx.size,
            self.config.page_size,
            ctx.max_results - ctx.results_count if ctx.max_results else ctx.size
        )

    def calculate_batch_end(self, ctx: BatchContext, batch_size: int) -> int:
        """计算批次结束位置"""
        return min(
            ctx.start + batch_size,
            int(ctx.total_results) if ctx.total_results != float("inf") else sys.maxsize
        )

async def _iter_papers(self, params: SearchParams) -> AsyncGenerator[Paper, None]:
    """迭代获取论文"""
    # 初始化上下文
    concurrent_limit = min(
        self._config.max_concurrent_requests,
        self._config.rate_limit_calls
    )
    processor = ResultProcessor(concurrent_limit, self._config)
    ctx = BatchContext(
        start=0,
        size=concurrent_limit * self._config.page_size,
        total_results=float("inf"),
        results_count=0,
        max_results=params.max_results
    )

    logger.info("开始搜索", extra={
        "query": params.query,
        "max_results": params.max_results,
        "concurrent_limit": concurrent_limit
    })

    send_stream, receive_stream = await processor.create_streams()

    async def fetch_page(page_start: int):
        """获取单页数据"""
        try:
            async with self._session_manager.rate_limited_context():
                response = await self._fetch_page(params, page_start)
                result = await self.parse_response(response)
                await send_stream.send(result)
        except Exception as e:
            logger.error(f"获取页面失败: {e!s}", extra={"page": page_start})
            raise

    async def process_batch(batch_ctx: BatchContext):
        """处理单个批次"""
        try:
            async with create_task_group() as batch_tg:
                batch_size = processor.calculate_batch_size(batch_ctx)
                end = processor.calculate_batch_end(batch_ctx, batch_size)

                for offset in range(batch_ctx.start, end):
                    if batch_ctx.max_results and offset >= batch_ctx.max_results:
                        break
                    batch_tg.start_soon(fetch_page, offset)
        except Exception as e:
            logger.error("批量获取失败", extra={
                "start": batch_ctx.start,
                "size": batch_ctx.size,
                "error": str(e)
            })
            raise

    try:
        async with create_task_group() as tg:
            tg.start_soon(process_batch, ctx)

            async for papers, total in receive_stream:
                # 更新总结果数
                ctx.total_results = total

                # 检查首次批次是否有结果
                if ctx.results_count == 0 and total == 0:
                    logger.info("未找到结果", extra={"query": params.query})
                    raise SearchCompleteException(0)

                # 处理论文
                for paper in papers:
                    yield paper
                    ctx.results_count += 1
                    if ctx.max_results and ctx.results_count >= ctx.max_results:
                        raise SearchCompleteException(ctx.results_count)

                # 准备下一批次
                ctx.start += len(papers)
                if ctx.start < min(
                        int(ctx.total_results) if ctx.total_results != float("inf")
                        else sys.maxsize,
                        ctx.max_results or sys.maxsize
                ):
                    await sleep(self._config.rate_limit_period)
                    tg.start_soon(process_batch, ctx)

    finally:
        await receive_stream.aclose()
        logger.info("搜索结束", extra={"total_results": ctx.results_count})
