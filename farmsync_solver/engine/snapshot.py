"""RunState, RunSnapshot, AccountRow: everything that crosses the engine/UI seam.

Spec 9.2. These live here rather than in `run.py` so the UI never imports the
file full of threads — this module imports nothing that starts one.

`RunSnapshot` is deliberately **flat and frozen**: the UI writes
`label.text = s.joined`, and a frozen value read from another thread cannot be
half-written. The engine replaces the whole snapshot on every change; nothing
mutates one in place.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Result(str, Enum):
    """What one attempt came to (CONTEXT.md, "Outcome").

    It lives beside the snapshot rather than beside the worker: `AccountRow`
    carries it, and a row is read by the UI.
    """

    JOINED = "joined"  # got in with no captcha to crack
    SOLVED = "solved"  # a captcha was cracked; only these are billed
    FAILED = "failed"  # could not be checked, after every attempt


class RunState(str, Enum):
    """The named phase a run is in (spec 5.1)."""

    IDLE = "idle"
    DISCOVERING = "discovering"
    SOLVING = "solving"
    RESTING = "resting"
    STOPPING = "stopping"


@dataclass(frozen=True)
class RunSnapshot:
    """The whole picture of a run at one moment. Never holds a cookie or a key.

    `credit_left` is money and `estimated_solves` is solves: spec 7 shows both,
    solves first. `done` and `total` count this round; every other counter counts
    the run, and `start` resets them all to zero.
    """

    state: RunState = RunState.IDLE
    headline: str = ""
    message: str = ""
    round_number: int = 0
    done: int = 0
    total: int = 0
    joined: int = 0
    solved: int = 0
    failed: int = 0
    credit_left: float = 0.0
    estimated_solves: int = 0


@dataclass(frozen=True)
class AccountRow:
    """One finished account, as one row of the live table.

    `at` is the epoch second the account finished; the screen turns it into an
    elapsed time.
    """

    username: str
    outcome: Result
    detail: str
    at: float


IDLE = RunSnapshot()
"""The snapshot before any run. `snapshot()` answers with this, never with None."""
