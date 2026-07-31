from typing import TYPE_CHECKING, cast
from typing_extensions import Self

import loguru

from aioarxiv.config import ArxivConfig, default_config

if TYPE_CHECKING:
    # avoid sphinx autodoc resolve annotation failed
    # because loguru module do not have `Logger` class actually
    from loguru import Logger, Record

logger: "Logger" = loguru.logger
"""loguru logger instance

default:

- format: `<g>{time:MM-DD HH:mm:ss}</g> [<lvl>{level}</lvl>] <c><u>{name}</u></c> | <c>{function}:{line}</c>| {message}`
- level: `INFO` , depends on `config.log_level` configuration
- output: stdout

usage:
    ```python
    from log import logger
    ```
"""


class ConfigManager:
    _instance: "ConfigManager | None" = None
    _config: ArxivConfig | None = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cast("Self", cls._instance)

    @classmethod
    def set_config(cls, config: ArxivConfig) -> None:
        cls._config = config

    @classmethod
    def get_config(cls) -> ArxivConfig:
        return cls._config or default_config


def default_filter(record: "Record") -> bool:
    """default loguru filter function, change log level by config.log_level"""
    log_level = record["extra"].get("arxiv_log_level")

    if log_level is None:
        config = ConfigManager.get_config()
        log_level = config.log_level if config else default_config.log_level

    levelno = logger.level(log_level).no if isinstance(log_level, str) else log_level
    return record["level"].no >= levelno


default_format: str = (
    "<g>{time:MM-DD HH:mm:ss}</g> "
    "[<lvl>{level}</lvl>] "
    "<c><u>{name}</u></c> | "
    "<c>{function}:{line}</c>| "
    "{message}"
)
