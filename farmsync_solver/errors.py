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
    BAD_FARM_TOKEN = "BAD_FARM_TOKEN"
    NO_INTERNET = "NO_INTERNET"
    UNKNOWN = "UNKNOWN"


# A solver failure about the key, not the account (spec 5.5). The first one ends
# the run, because every later account fails the same way.
TERMINAL_ERROR_CODES = frozenset({ErrorCode.BAD_API_KEY, ErrorCode.NO_CREDIT})


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
