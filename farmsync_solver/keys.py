"""check_api_key(key) and check_farm_token(token).

Spec 9.3: plain functions, not Engine methods, so the Setup screen can test a
string without building an Engine. Both raise `AppError`; neither returns a
boolean, and neither holds user-facing copy.
"""
from __future__ import annotations

from typing import Any

from .engine.dibycap import Dibycap
from .engine.farmsync import Farmsync


def check_api_key(key: str, session: Any | None = None) -> dict[str, Any]:
    """The whole `/balance` payload: Setup, Speed and the header all read it."""
    return Dibycap(key, session=session).balance()


def check_farm_token(token: str, session: Any | None = None) -> None:
    """Returns nothing. Raises `AppError` when the token is not accepted."""
    Farmsync(token, session=session).devices()
