"""check_api_key(key) and check_farm_token(token).

Spec 9.3: plain functions, not Engine methods, so the Setup screen can test a
string without building an Engine. Both raise `AppError`; neither returns a
boolean, and neither holds user-facing copy.
"""
from __future__ import annotations

from typing import Any, Protocol

from .engine.dibycap import Dibycap
from .engine.farmsync import Farmsync
from .errors import AppError, ErrorCode


class KeyCheck(Protocol):
    """The shape of `check_api_key`, so a screen can be tested with a stand-in."""

    def __call__(self, key: str, session: Any | None = ...) -> dict[str, Any]: ...


class TokenCheck(Protocol):
    """The shape of `check_farm_token`."""

    def __call__(self, token: str, session: Any | None = ...) -> None: ...


def check_api_key(key: str, session: Any | None = None) -> dict[str, Any]:
    """The whole `/balance` payload: Setup, Speed and the header all read it.

    A key with no credit left is refused here, not in `Dibycap.balance`: spec 7
    treats `estimated_solves == 0` as out of credit rather than trusting
    `success`, while the header still has to be able to show the figure 0.
    """
    balance = Dibycap(key, session=session).balance()

    solves = balance.get("estimated_solves")
    if not isinstance(solves, int) or isinstance(solves, bool) or solves <= 0:
        raise AppError(ErrorCode.NO_CREDIT, f"estimated_solves={solves!r}")

    return balance


def check_farm_token(token: str, session: Any | None = None) -> None:
    """Returns nothing. Raises `AppError` when the token is not accepted."""
    Farmsync(token, session=session).devices()
