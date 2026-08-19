"""Typed errors with stable codes, shared by the engine, key checks and the updater.

The codes are stable strings. The UI maps them to sentences in `ui/messages.py`;
nothing here holds user-facing copy.
"""
from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """A stable code that identifies what went wrong."""

    BAD_API_KEY = "BAD_API_KEY"
    NO_CREDIT = "NO_CREDIT"
    SERVICE_PAUSED = "SERVICE_PAUSED"  # the key is fine; dibycap is not solving
    BAD_FARM_TOKEN = "BAD_FARM_TOKEN"
    NO_INTERNET = "NO_INTERNET"
    UNKNOWN = "UNKNOWN"


# A solver failure about the key, not the account (spec 5.5). The first one ends
# the run, because nothing but the user can fix it and every later account fails
# the same way. `SERVICE_PAUSED` was here until
# [ADR 0003](../docs/adr/0003-a-run-waits-out-a-down-solve-service.md): a paused
# service fixes itself, so the run waits it out instead.
TERMINAL_ERROR_CODES = frozenset({ErrorCode.BAD_API_KEY, ErrorCode.NO_CREDIT})


class AppError(Exception):
    """Any failure the app can name. Never carries a cookie or an API key.

    `service` marks the faults dibycap itself raised about dibycap — a paused
    service, a call that did not go through, a body that was not JSON. It is set
    by the client that made the call, never guessed from the text of an error,
    which is how a *service* `UNKNOWN` stays apart from the `UNKNOWN` an engine
    bug becomes (ADR 0003).
    """

    def __init__(self, code: ErrorCode, detail: str = "", *, service: bool = False) -> None:
        self.code = code
        self.detail = detail
        self.service = service
        super().__init__(f"{code.value}: {detail}" if detail else code.value)

    @classmethod
    def from_exception(cls, error: BaseException) -> "AppError":
        """Wrap any exception, keeping an AppError untouched.

        A wrapped exception is never a service fault: this is where an engine bug
        becomes an `AppError`, and a bug does not heal in a minute.
        """
        if isinstance(error, AppError):
            return error
        return cls(ErrorCode.UNKNOWN, f"{type(error).__name__}: {error}")


def is_terminal(error: AppError) -> bool:
    """True when a solve failure is about the key and must end the run."""
    return error.code in TERMINAL_ERROR_CODES


def is_waitable(error: AppError) -> bool:
    """True when the fault is the solve service's, so waiting it out can fix it.

    The run goes to `Waiting` on one of these rather than ending (ADR 0003).
    """
    return error.service
