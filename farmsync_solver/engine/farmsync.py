"""Farmsync client: accounts(), devices(), discover().

One of the three files allowed to touch the network (spec 9.4).

Two rules from spec 9.5 shape it: gzip is asserted, never assumed, and a body is
never assumed to be JSON — a call with a bad token answers with a Cloudflare
HTML challenge page.
"""
from __future__ import annotations

import logging
from typing import Any

from ..errors import REFUSED_STATUS, AppError, ErrorCode
from .eligibility import eligible_accounts

BASE_URL = "https://api.farmsync.cloud"
TIMEOUT_SECONDS = 30

_log = logging.getLogger(__name__)


class Farmsync:
    """The farmsync API, for one token."""

    def __init__(self, token: str, session: Any | None = None) -> None:
        self._session = session if session is not None else _new_session()
        self._session.headers["Authorization"] = f"Bearer {token}"
        self._session.headers["Accept-Encoding"] = "gzip"
        self._session.trust_env = False

    def accounts(self) -> list[dict[str, Any]]:
        """Every account on the token, in one call. Raises `AppError` on trouble."""
        self._assert_gzip()
        response = self._get("/api/self/accounts")

        if response.status_code in REFUSED_STATUS:
            raise AppError(ErrorCode.BAD_FARM_TOKEN, f"accounts http {response.status_code}")

        accounts = _as_list(response)
        _log.info("accounts ok count=%d", len(accounts))
        return accounts

    def discover(self) -> list[dict[str, Any]]:
        """The eligible accounts for one round: two calls, then the blocklist.

        Nothing is cached. The two calls cost about 12 s inside a ~72 s round,
        and the payload goes stale quickly (spec 9.5).
        """
        accounts = self.accounts()
        devices = self.devices()

        eligible = eligible_accounts(accounts, devices)
        _log.info(
            "discovery eligible=%d of=%d devices=%d",
            len(eligible),
            len(accounts),
            len(devices),
        )
        return eligible

    def devices(self) -> list[dict[str, Any]]:
        """Every device on the account. Raises `AppError` on any trouble."""
        response = self._get("/api/devices/")

        if response.status_code in REFUSED_STATUS:
            raise AppError(ErrorCode.BAD_FARM_TOKEN, f"devices http {response.status_code}")

        devices = _as_list(response)
        _log.info("devices ok count=%d", len(devices))
        return devices

    def _assert_gzip(self) -> None:
        """Asserted, never assumed: uncompressed the body is 103 MB (spec 9.5).

        The constructor sets the header, so this guards a later edit of the
        session rather than today's code, and it refuses before sending: an
        ungzipped accounts call does not finish. `UNKNOWN` because the fault is
        ours, not the token's.
        """
        if "gzip" not in self._session.headers.get("Accept-Encoding", ""):
            raise AppError(ErrorCode.UNKNOWN, "accounts call is not gzipped")

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
