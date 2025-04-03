import sys

from loguru import logger

from aioarxiv.utils.log import default_filter, default_format

logger.remove()
logger_id = logger.add(
    sys.stdout,
    level=0,
    diagnose=False,
    filter=default_filter,
    format=default_format,
)
