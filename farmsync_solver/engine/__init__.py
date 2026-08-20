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

__all__ = [
    "AccountRow",
    "Engine",
    "Result",
    "RunSnapshot",
    "RunState",
    "a_run_is_going",
    "current",
    "run",
]

_current: Engine | None = None


def current() -> Engine:
    """The one `Engine` this process runs."""
    global _current
    if _current is None:
        _current = Engine()
    return _current


def a_run_is_going() -> bool:
    """Whether there is a run on right now, for the parts of the UI that only care.

    A bool, not a snapshot: the close question and the update offer have no
    business knowing what a run is made of. The rule itself is
    `RunSnapshot.is_running`; this only asks the engine on the app's behalf.

    Two ways to put something else behind it, and they are not interchangeable.
    `CloseQuestion` and `UpdateOffer` bind it as a default argument at import,
    so a test hands them `is_running=lambda: True` instead. Settings calls it
    through this module every time it draws, so a test patches it here.
    """
    return current().snapshot().is_running
