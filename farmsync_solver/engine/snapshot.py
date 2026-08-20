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
from enum import Enum, auto

from ..errors import ErrorCode


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
    # The solve service is down and the run is sitting it out (ADR 0003). It is a
    # run like any other: Stop works, the close question is asked, no update is
    # offered — every "is a run on?" test in the UI reads `is not IDLE`.
    WAITING = "waiting"
    STOPPING = "stopping"


class Headline(Enum):
    """The named line at the top of the left panel (spec 4.2).

    A member, never the sentence itself. The engine says *which* line the user is
    reading and `ui/messages.py` says what it reads, which is what keeps every
    word in one module and the engine clear of the UI package (ADR 0005).

    A run that ended on a fault has no member here: its headline is the
    `ErrorCode` that ended it, and the error table already holds that sentence.

    A plain `Enum`, unlike `RunState` and `Result` beside it: a member is only
    ever compared and logged by name, so a value would be a second identity
    nobody reads — the very thing this enum was written to take away.
    """

    STARTING = auto()
    DISCOVERING = auto()
    SOLVING = auto()
    RESTING = auto()
    NO_ACCOUNTS = auto()  # the round found nothing to check
    NO_FARMSYNC = auto()  # farmsync was not reached; the next round tries again
    WAITING_PAUSED = auto()
    WAITING_UNREACHABLE = auto()
    STOPPING = auto()
    STOPPED = auto()
    CRASHED = auto()  # an engine bug, which reads as its own sentence (spec 5.6)


@dataclass(frozen=True)
class RunSnapshot:
    """The whole picture of a run at one moment. Never holds a cookie or a key.

    Every field is a fact, never a sentence: the words for one are the UI's to
    pick (ADR 0005). `headline` names the line the panel shows, `seconds_left`
    and `seconds_waited` are what the moving line under it counts, and `detail`
    is the raw text of the fault that ended the run — the one string here the
    user reads as it stands, behind the **Details** link of spec 5.6.

    `credit_left` is money and `estimated_solves` is solves: spec 7 shows both,
    solves first. `done` and `total` count this round; every other counter counts
    the run, and `start` resets them all to zero.
    """

    state: RunState = RunState.IDLE
    headline: Headline | ErrorCode | None = None
    detail: str = ""
    round_number: int = 0
    done: int = 0
    total: int = 0
    joined: int = 0
    solved: int = 0
    failed: int = 0
    credit_left: float = 0.0
    estimated_solves: int = 0
    # The countdown of the Resting and Waiting lines. `None` while a waiting run
    # has a knock out: that is the one moment with nothing to count down to.
    seconds_left: int | None = None
    seconds_waited: float = 0.0


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
