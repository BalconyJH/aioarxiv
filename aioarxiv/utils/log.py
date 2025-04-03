import inspect
import logging
from typing import TYPE_CHECKING, Optional

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
    _instance = None
    _config: Optional[ArxivConfig] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def set_config(cls, config: ArxivConfig) -> None:
        cls._config = config

    @classmethod
    def get_config(cls) -> ArxivConfig:
        return cls._config or default_config


# https://loguru.readthedocs.io/en/stable/overview.html#entirely-compatible-with-standard-logging
class LoguruHandler(logging.Handler):  # pragma: no cover
    """
    A handler class which allows the use of Loguru in Python's standard logging module.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level,
            record.getMessage(),
        )


def default_filter(record: "Record"):
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

# logger.remove()
# logger_id = logger.add(
#     sys.stdout,
#     level=0,
#     diagnose=False,
#     filter=default_filter,
#     format=default_format,
# )

__autodoc__ = {"logger_id": False}
