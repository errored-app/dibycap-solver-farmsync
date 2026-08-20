"""Shared fixtures. Logging is process-global, so every test must undo it."""
from __future__ import annotations

import importlib
import time
from collections.abc import Callable, Iterator
from types import ModuleType

import pytest

from farmsync_solver import logging_setup
from farmsync_solver.engine import Engine
from farmsync_solver.engine.snapshot import RunState


@pytest.fixture(autouse=True)
def clean_logging() -> Iterator[None]:
    yield
    logging_setup.reset()


@pytest.fixture(autouse=True)
def one_close_question() -> Iterator[None]:
    """The close question lives for the life of the process, so it must not leak.

    Imported here rather than at the top: NiceGUI's user fixture drops the ui
    modules from `sys.modules`, and a reference taken at collection time would
    reset a copy nothing else is holding.
    """
    importlib.import_module("farmsync_solver.ui.closing").forget()
    yield
    importlib.import_module("farmsync_solver.ui.closing").forget()


@pytest.fixture
def ui_app() -> ModuleType:
    """The live `farmsync_solver.ui.app`.

    NiceGUI's user fixture drops every page module from `sys.modules` when it
    tidies up, so the copy a test file imported at collection time can be stale
    while the window serves a fresh one. Patch and read the module through this.
    """
    return importlib.import_module("farmsync_solver.ui.app")


def wait_for(check: Callable[..., bool], timeout: float = 5.0) -> bool:
    """True as soon as `check` passes. Polls; never blocks on another thread."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.005)
    return check()


@pytest.fixture
def engines() -> Iterator[list[Engine]]:
    """Every engine a test starts, stopped before the test ends.

    Here rather than in one test file: two files drive a real engine, and a
    fixture imported from another test module reads as a redefinition.
    """
    started: list[Engine] = []
    yield started
    for engine in started:
        engine.stop()
        wait_for(lambda stopped=engine: stopped.snapshot().state is RunState.IDLE, timeout=10)
