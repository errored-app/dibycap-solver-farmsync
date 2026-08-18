"""The worker body: one account in, one named outcome out.

Spec 9.8 folds today's `roblox.py` in here. This module will grow the round loop
and the Engine class; for now it holds the part that runs 16 to 65 times at once.

Two rules shape it:

- A failed account is normal operation, not an alarm: 28.6% of attempts fail
  (spec 2), so a failure is an outcome, not an exception.
- A terminal error is about the key, so it is raised at once and never retried
  (spec 5.5). The round loop acts on it; this module only names it.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from ..errors import AppError, is_terminal
from .dibycap import HOPELESS_CODES, Dibycap

# One gap per retry. The count follows from the schedule, so there is no cap
# constant that never binds.
BACKOFF_SECONDS = (1.0, 2.0)
MAX_ATTEMPTS = len(BACKOFF_SECONDS) + 1

_log = logging.getLogger(__name__)


class Result(str, Enum):
    """What one attempt came to."""

    JOINED = "joined"  # got in with no captcha to crack
    SOLVED = "solved"  # a captcha was cracked; only these are billed
    FAILED = "failed"  # could not be checked, after every attempt


@dataclass(frozen=True)
class Outcome:
    """One account's result. Holds a farmsync id and a code — never a cookie."""

    account_id: str
    result: Result
    detail: str = ""


def solve_account(
    client: Dibycap,
    account: dict[str, Any],
    sleep: Callable[[float], None] = time.sleep,
) -> Outcome:
    """Send one account to the solver and name what happened.

    Tries up to `MAX_ATTEMPTS` times. The retry is deliberately invisible: the UI
    is never told an attempt is a second try (spec 5.6). Two answers end it
    early — a terminal error, which the round loop must see at once, and a
    hopeless account, which a second attempt cannot change.

    Raises `AppError` for a terminal fault, and for nothing else.
    """
    account_id = str(account.get("id", ""))
    cookie = str(account.get("cookie") or "")
    detail = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _named(account_id, _read(client.solve(cookie)))
        except AppError as error:
            if is_terminal(error):
                _log.info("account %s terminal %s", account_id, error.detail)
                raise
            detail = error.detail
            if detail in HOPELESS_CODES:
                break

        if attempt < MAX_ATTEMPTS:
            sleep(BACKOFF_SECONDS[attempt - 1])

    return _named(account_id, Result.FAILED, detail)


def _read(timings: dict[str, Any]) -> Result:
    """A solve is billed, a join is not, and the timings are what tell them apart."""
    solve_ms = timings.get("solve_ms") or 0
    return Result.SOLVED if solve_ms > 0 else Result.JOINED


def _named(account_id: str, result: Result, detail: str = "") -> Outcome:
    _log.info("account %s %s %s", account_id, result.value, detail)
    return Outcome(account_id=account_id, result=result, detail=detail)
