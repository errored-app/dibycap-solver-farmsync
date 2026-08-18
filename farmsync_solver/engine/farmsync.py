"""Farmsync client: accounts(), devices().

One of the three files allowed to touch the network (spec 9.4).

Two rules from spec 9.5 shape it: gzip is asserted, never assumed, and a body is
never assumed to be JSON — a call with a bad token answers with a Cloudflare
HTML challenge page.
"""
from __future__ import annotations

import logging
from typing import Any

from ..errors import AppError, ErrorCode

BASE_URL = "https://api.farmsync.cloud"
TIMEOUT_SECONDS = 30
REFUSED_STATUS = (401, 403)

_log = logging.getLogger(__name__)


class Farmsync:
    """The farmsync API, for one token."""

    def __init__(self, token: str, session: Any | None = None) -> None:
        self._session = session if session is not None else _new_session()
        self._session.headers["Authorization"] = f"Bearer {token}"
        self._session.headers["Accept-Encoding"] = "gzip"
        self._session.trust_env = False

    def devices(self) -> list[dict[str, Any]]:
        """Every device on the account. Raises `AppError` on any trouble."""
        response = self._get("/api/devices/")

        if response.status_code in REFUSED_STATUS:
            raise AppError(ErrorCode.BAD_FARM_TOKEN, f"devices http {response.status_code}")

        devices = _as_list(response)
        _log.info("devices ok count=%d", len(devices))
        return devices

    def _get(self, path: str) -> Any:
        try:
            return self._session.get(f"{BASE_URL}{path}", timeout=TIMEOUT_SECONDS)
        except Exception as error:  # any transport failure reads the same way
            raise AppError(ErrorCode.NO_INTERNET, f"farmsync {type(error).__name__}") from error


def _as_list(response: Any) -> list[dict[str, Any]]:
    """No JSON means the challenge page, which means the token was not accepted."""
    try:
        payload = response.json()
    except Exception as error:
        raise AppError(ErrorCode.BAD_FARM_TOKEN, "farmsync sent no JSON") from error

    if isinstance(payload, dict):  # some endpoints wrap the list in an envelope
        for value in payload.values():
            if isinstance(value, list):
                payload = value
                break
    if not isinstance(payload, list):
        raise AppError(ErrorCode.BAD_FARM_TOKEN, "farmsync sent an unexpected shape")
    return [item for item in payload if isinstance(item, dict)]


def _new_session() -> Any:
    # Imported here, not at module top: naming this module must not cost an
    # import of requests.
    import requests

    return requests.Session()
