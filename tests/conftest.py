"""Shared fixtures. Logging is process-global, so every test must undo it."""
from __future__ import annotations

import importlib
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest

from farmsync_solver import logging_setup, paths
from farmsync_solver.engine import Engine
from farmsync_solver.engine.snapshot import RunState


@pytest.fixture(autouse=True)
def clean_logging() -> Iterator[None]:
    yield
    logging_setup.reset()


@pytest.fixture(autouse=True)
def app_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    r"""`%APPDATA%` in a temporary folder, for every test in the suite.

    Autouse, because a run writes its history row the moment it starts (ADR
    0008): any test that drives a real `Engine` would otherwise put rows in the
    spending history of whoever is running the suite. A test that wants a
    different folder sets `APPDATA` again in its own body.
    """
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    return paths.app_data_dir()


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
