# Starter

## 安装

<warning>
警告：该项目目前仍处于测试阶段，尚未进入稳定版本。请勿用于生产环境。
</warning>

使用 `pip` 安装: `pip install aioarxiv` 

## 基本概念

`aioarxiv` 是一个专为 arXiv API 构建的异步 Python 客户端，旨在简化高效的论文检索和下载操作。其主要功能包括：
- 异步 API 调用，提高高频请求的性能。
- 灵活的查询和下载功能。
- 自定义配置以满足特定需求。

## 主要类

* `ArxivClient`: 主要客户端类,用于执行搜索
* `Paper`: 论文数据模型
* `SearchParams`: 搜索参数配置模型

## 使用示例

<code-block lang="python">
import asyncio

from aioarxiv.client.arxiv_client import ArxivClient
from aioarxiv.config import ArxivConfig

async def search():
    config = ArxivConfig(
        log_level="DEBUG",
    )
    client = ArxivClient(config=config)

    query = "quantum computing"
    count = 0

    print(f"Searching for: {query}")
    print("-" * 50)

    async for paper in client.search(query=query, max_results=1):
        count += 1
        print(f"\nPaper {count}:")
        print(f"Title: {paper.title}")
        print(f"Authors: {paper.authors}")
        print(f"Summary: {paper.summary[:200]}...")
        print("-" * 50)
        file_path = await client.download_paper(paper)
        print(f"Downloaded to: {file_path}")

if __name__ == "__main__":
asyncio.run(search())
</code-block>

## 自定义配置

<code-block lang="python">
from aioarxiv import ArxivConfig

config = ArxivConfig(
    rate_limit_calls=3, # 请求频率限制
    max_concurrent_requests=3 # 最大并发数
)
client = ArxivClient(config=config)
</code-block>

## 错误处理

`ArxivClient.search()` 方法返回一个异步生成器, 依赖 `SearchCompleteException`
异常来判断搜索是否完成.

因此你应该使用以下结构来处理搜索:

<code-block lang="python">
from aioarxiv import ArxivClient, SearchCompleteException

async def search_and_handle_error():
    try:
        query = "quantum computing"
        async for paper in client.search(query=query, max_results=1):
            print(paper)
    except SearchCompleteException:
        print("Search complete.")
</code-block>

## 反馈
功能请求和错误报告请提交到 [GitHub Issue](https://github.com/BalconyJH/aioarxiv/issues/new)。

<seealso>
 <category ref="arxiv-api">
  <a href="https://info.arxiv.org/help/api/index.html">arXiv API</a>
 </category>
 <category ref="aioarxiv">
  <a href="https://github.com/BalconyJH/aioarxiv">aioarxiv</a>
 </category>
</seealso>
