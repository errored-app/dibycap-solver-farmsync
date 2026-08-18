"""Dibycap client: balance(), solve(cookie).

One of the three files allowed to touch the network (spec 9.4).

`balance()` is both the key check and the live credit read (spec 7): one call,
114 bytes, cookie-free, so it can never spend solve credit.
"""
from __future__ import annotations

import logging
from typing import Any

from ..errors import AppError, ErrorCode

API_URL = "https://api.dibycap.com"
TIMEOUT_SECONDS = 15
REFUSED_STATUS = (401, 403)

_log = logging.getLogger(__name__)


class Dibycap:
    """The dibycap solver API, for one key."""

    def __init__(self, api_key: str, session: Any | None = None) -> None:
        self._api_key = api_key
        self._session = session if session is not None else _new_session()

    def balance(self) -> dict[str, Any]:
        """The whole `/balance` payload. Raises `AppError` on any trouble."""
        response = self._post("/balance")

        if response.status_code in REFUSED_STATUS:
            raise AppError(ErrorCode.BAD_API_KEY, f"balance http {response.status_code}")

        payload = _as_object(response)
        if not payload.get("success"):
            raise AppError(ErrorCode.BAD_API_KEY, str(payload.get("error") or "balance refused"))

        _log.info("balance ok solves=%s", payload.get("estimated_solves"))
        return payload

    def _post(self, path: str) -> Any:
        try:
            return self._session.post(
                f"{API_URL}{path}",
                json={},
                headers={"X-API-Key": self._api_key},
                timeout=TIMEOUT_SECONDS,
            )
        except Exception as error:  # any transport failure reads the same way
            raise AppError(ErrorCode.NO_INTERNET, f"dibycap {type(error).__name__}") from error


def _as_object(response: Any) -> dict[str, Any]:
    """A body that is not a JSON object is a fault, not a crash."""
    try:
        payload = response.json()
    except Exception as error:
        raise AppError(ErrorCode.UNKNOWN, "dibycap sent no JSON") from error
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.UNKNOWN, "dibycap sent an unexpected shape")
    return payload


def _new_session() -> Any:
    # Imported here, not at module top, so the tests and the UI never pay for
    # curl_cffi's binary import just to name this module.
    from curl_cffi import requests

    return requests.Session()
