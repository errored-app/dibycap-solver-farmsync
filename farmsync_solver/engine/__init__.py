"""The engine: the whole interface the UI gets.

Spec 9.2. Importing this name imports `run.py`, which owns the threads. A screen
that only reads a snapshot should import `engine.snapshot` instead and stay clear
of them.

`current()` is the one `Engine` the app runs. Spec 9.2 asks for one per app, not
one per run: the Home timer reads it while the app is Idle too, and Settings asks
it whether the keys are locked. It is built on first ask rather than at import,
because importing this package must not start anything.
"""
from __future__ import annotations

from . import run
from .run import Engine
from .snapshot import AccountRow, Result, RunSnapshot, RunState

__all__ = ["AccountRow", "Engine", "Result", "RunSnapshot", "RunState", "current", "run"]

_current: Engine | None = None


def current() -> Engine:
    """The one `Engine` this process runs."""
    global _current
    if _current is None:
        _current = Engine()
    return _current
