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
"""日志记录器对象。

default:

- 格式: `[%(asctime)s %(name)s] %(levelname)s: %(message)s`
- 等级: `INFO` ,  根据 `config.log_level` 配置改变
- 输出: 输出至 stdout

usage:
    ```python
    from log import logger
    ```
"""

_current_config: Optional[ArxivConfig] = None


def set_config(config: ArxivConfig) -> None:
    """设置当前全局配置"""
    global _current_config
    _current_config = config


def get_config() -> ArxivConfig:
    """获取当前配置或默认配置"""
    return _current_config or default_config


# https://loguru.readthedocs.io/en/stable/overview.html#entirely-compatible-with-standard-logging
class LoguruHandler(logging.Handler):  # pragma: no cover
    """logging 与 loguru 之间的桥梁,  将 logging 的日志转发到 loguru。"""

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
    """默认的日志过滤器,  根据 `config.log_level` 配置改变日志等级。"""
    log_level = record["extra"].get("arxiv_log_level")

    if log_level is None:
        config = get_config()
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
"""默认日志格式"""

# logger.remove()
# logger_id = logger.add(
#     sys.stdout,
#     level=0,
#     diagnose=False,
#     filter=default_filter,
#     format=default_format,
# )
# """默认日志处理器 id"""

__autodoc__ = {"logger_id": False}
