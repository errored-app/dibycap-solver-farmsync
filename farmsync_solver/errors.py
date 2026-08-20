"""Typed errors with stable codes, shared by the engine, key checks and the updater.

The codes are stable strings. The UI maps them to sentences in `ui/messages.py`;
nothing here holds user-facing copy.

`REFUSED_STATUS` is here rather than beside either client because it is only
ever read on the way to a code below.
"""
from __future__ import annotations

from enum import Enum

# The two HTTP statuses that mean "your credential was refused". Each client
# turns them into its own code — `BAD_API_KEY` for dibycap, `BAD_FARM_TOKEN` for
# farmsync — but which statuses count is one fact, and it is written here once.
REFUSED_STATUS = (401, 403)


class ErrorCode(str, Enum):
    """A stable code that identifies what went wrong."""

    BAD_API_KEY = "BAD_API_KEY"
    NO_CREDIT = "NO_CREDIT"
    SERVICE_PAUSED = "SERVICE_PAUSED"  # the key is fine; dibycap is not solving
    BAD_FARM_TOKEN = "BAD_FARM_TOKEN"
    NO_INTERNET = "NO_INTERNET"
    UNKNOWN = "UNKNOWN"


class Severity(str, Enum):
    """How bad a failure is: what the run has to do about it.

    Named once, by the client that made the failing call, and never worked out
    again downstream from the code or the text of an error. That is what keeps a
    *service* `UNKNOWN` apart from the `UNKNOWN` an engine bug becomes (ADR 0003).
    """

    RETRY = "RETRY"  # ordinary; another attempt may well work
    ACCOUNT_DONE = "ACCOUNT_DONE"  # this account is finished, the run is not
    WAIT_IT_OUT = "WAIT_IT_OUT"  # the solve service's own fault; it heals in time
    ENDS_RUN = "ENDS_RUN"  # nothing but the user can fix it


class AppError(Exception):
    """Any failure the app can name. Never carries a cookie or an API key."""

    def __init__(
        self,
        code: ErrorCode,
        detail: str = "",
        *,
        severity: Severity = Severity.RETRY,
    ) -> None:
        self.code = code
        self.detail = detail
        self.severity = severity
        super().__init__(f"{code.value}: {detail}" if detail else code.value)

    @classmethod
    def from_exception(cls, error: BaseException) -> "AppError":
        """Wrap any exception, keeping an AppError untouched.

        A wrapped exception is only ever worth another try: this is where an
        engine bug becomes an `AppError`, and a bug does not heal in a minute.
        """
        if isinstance(error, AppError):
            return error
        return cls(ErrorCode.UNKNOWN, f"{type(error).__name__}: {error}")


def is_terminal(error: AppError) -> bool:
    """True when the first one of these must end the run (spec 5.5)."""
    return error.severity is Severity.ENDS_RUN


def is_waitable(error: AppError) -> bool:
    """True when the fault is the solve service's, so waiting it out can fix it.

    The run goes to `Waiting` on one of these rather than ending (ADR 0003).
    """
    return error.severity is Severity.WAIT_IT_OUT
