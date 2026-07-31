import sys

from loguru import logger
import pytest

from aioarxiv.utils.log import default_filter, default_format


@pytest.fixture(scope="session", autouse=True)
def configure_logging():
    """Route loguru output through the library defaults during the test run."""
    logger.remove()
    handler_id = logger.add(
        sys.stdout,
        level=0,
        diagnose=False,
        filter=default_filter,
        format=default_format,
    )
    yield
    logger.remove(handler_id)
