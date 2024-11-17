from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Protocol

from aiohttp import ClientResponse

from ..config import ArxivConfig
from ..models import Paper, SearchParams


class ClientProtocol(Protocol):
    """客户端协议"""
    async def _fetch_page(self, params: SearchParams, start: int) -> ClientResponse:
        ...

    async def parse_response(
            self,
            response: ClientResponse
    ) -> tuple[list[Paper], int]:
        ...

    @property
    def _config(self) -> "ArxivConfig":
        ...

class BaseSearchManager(ABC):
    """搜索管理器基类"""
    @abstractmethod
    def __init__(self, client: ClientProtocol):
        pass

    @abstractmethod
    def execute_search(self, params: SearchParams) -> AsyncGenerator[Paper, None]:
        pass
