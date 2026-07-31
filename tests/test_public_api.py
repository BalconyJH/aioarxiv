"""Tests for the package-level public API surface."""

import aioarxiv
from aioarxiv import (
    ArxivClient,
    ArxivConfig,
    ArxivDownloader,
    ArxivException,
    Paper,
    QueryBuildError,
    SearchResult,
    SortCriterion,
    SortOrder,
    default_config,
)


def test_public_imports() -> None:
    assert ArxivClient is not None
    assert ArxivConfig is not None
    assert ArxivDownloader is not None
    assert ArxivException is not None
    assert Paper is not None
    assert QueryBuildError is not None
    assert SearchResult is not None
    assert SortCriterion is not None
    assert SortOrder is not None
    assert isinstance(default_config, ArxivConfig)


def test_all_exports_resolve() -> None:
    for name in aioarxiv.__all__:
        assert hasattr(aioarxiv, name), f"__all__ entry {name!r} is not importable"


def test_version_is_set() -> None:
    assert isinstance(aioarxiv.__version__, str)
    assert aioarxiv.__version__
