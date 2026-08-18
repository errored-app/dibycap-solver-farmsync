"""Shared fixtures. Logging is process-global, so every test must undo it."""
from __future__ import annotations

import importlib
from collections.abc import Iterator
from types import ModuleType

import pytest

from farmsync_solver import logging_setup


@pytest.fixture(autouse=True)
def clean_logging() -> Iterator[None]:
    yield
    logging_setup.reset()


@pytest.fixture
def ui_app() -> ModuleType:
    """The live `farmsync_solver.ui.app`.

    NiceGUI's user fixture drops every page module from `sys.modules` when it
    tidies up, so the copy a test file imported at collection time can be stale
    while the window serves a fresh one. Patch and read the module through this.
    """
    return importlib.import_module("farmsync_solver.ui.app")
