"""Shared fixtures. Logging is process-global, so every test must undo it."""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from farmsync_solver import logging_setup


@pytest.fixture(autouse=True)
def clean_logging() -> Iterator[None]:
    yield
    logging_setup.reset()
