"""The engine: the whole interface the UI gets.

Spec 9.2. Importing this name imports `run.py`, which owns the threads. A screen
that only reads a snapshot should import `engine.snapshot` instead and stay clear
of them.
"""
from __future__ import annotations

from . import run
from .run import Engine
from .snapshot import AccountRow, Result, RunSnapshot, RunState

__all__ = ["AccountRow", "Engine", "Result", "RunSnapshot", "RunState", "run"]
