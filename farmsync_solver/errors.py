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
# the run, because every later account fails the same way.
#
# `SERVICE_PAUSED` is here because it was measured: on 2026-08-18 `/balance`
# answered normally while every `/createTask` was refused with `service_paused`.
# It ends a run like a bad key, but it is not a bad key, so it gets its own code
# rather than sending the user to re-paste a key that works.
TERMINAL_ERROR_CODES = frozenset(
    {ErrorCode.BAD_API_KEY, ErrorCode.NO_CREDIT, ErrorCode.SERVICE_PAUSED}
)


class AppError(Exception):
    """Any failure the app can name. Never carries a cookie or an API key."""

    def __init__(self, code: ErrorCode, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}" if detail else code.value)

    @classmethod
    def from_exception(cls, error: BaseException) -> "AppError":
        """Wrap any exception, keeping an AppError untouched."""
        if isinstance(error, AppError):
            return error
        return cls(ErrorCode.UNKNOWN, f"{type(error).__name__}: {error}")


def is_terminal(error: AppError) -> bool:
    """True when a solve failure is about the key and must end the run."""
    return error.code in TERMINAL_ERROR_CODES
