"""Dibycap client: balance(), solve(cookie).

One of the three files allowed to touch the network (spec 9.4).

`balance()` is both the key check and the live credit read (spec 7): one call,
114 bytes, cookie-free, so it can never spend solve credit.

`solve(cookie)` is one attempt on one account. It retries nothing: the 3-attempt
retry is the worker's, in `run.py`.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable

from ..errors import AppError, ErrorCode, Severity

API_URL = "https://api.dibycap.com"
TIMEOUT_SECONDS = 15
REFUSED_STATUS = (401, 403)
POLL_ATTEMPTS = 180
DEFAULT_RETRY_MS = 1000
MIN_POLL_SECONDS = 0.2
UNFINISHED_STATUS = ("pending", "solving", "processing")

# Every refusal dibycap has a stable code for, and how bad each one is. This is
# the only table: the severity travels on the `AppError`, so no caller has to
# look a code up again. Codes are matched whole, so nothing here reads the text
# of an exception (spec 9.7).
#
# The `ACCOUNT_DONE` codes end the run for nobody, but a second attempt cannot
# change them, so the worker stops trying. Today's `src/roblox.py` treats the
# same words this way.
REFUSALS: dict[str, tuple[ErrorCode, Severity]] = {
    "invalid_api_key": (ErrorCode.BAD_API_KEY, Severity.ENDS_RUN),
    "insufficient_balance": (ErrorCode.NO_CREDIT, Severity.ENDS_RUN),
    "key_disabled": (ErrorCode.BAD_API_KEY, Severity.ENDS_RUN),
    "key_expired": (ErrorCode.BAD_API_KEY, Severity.ENDS_RUN),
    "service_paused": (ErrorCode.SERVICE_PAUSED, Severity.WAIT_IT_OUT),
    "cookie_dead": (ErrorCode.UNKNOWN, Severity.ACCOUNT_DONE),
    "dead_cookie": (ErrorCode.UNKNOWN, Severity.ACCOUNT_DONE),
    "moderated": (ErrorCode.UNKNOWN, Severity.ACCOUNT_DONE),
    "banned": (ErrorCode.UNKNOWN, Severity.ACCOUNT_DONE),
}

# A dibycap code is one lower-case word. Anything else the server sends back is
# free text, and free text can hold a cookie, so it is dropped rather than
# repeated (spec 8.2).
CODE_SHAPE = re.compile(r"^[a-z0-9_]{1,40}$")
SPACES = re.compile(r"\s+")
NO_CODE = "solve refused"

COOKIE_FIELD = ".ROBLOSECURITY"

_log = logging.getLogger(__name__)


class Dibycap:
    """The dibycap solver API, for one key."""

    def __init__(
        self,
        api_key: str,
        session: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._session = session if session is not None else _new_session()
        self._sleep = sleep

    def balance(self) -> dict[str, Any]:
        """The whole `/balance` payload. Raises `AppError` on any trouble."""
        payload = self._accepted(self._post("/balance", {}), "balance")
        if not payload.get("success"):
            raise AppError(
                ErrorCode.BAD_API_KEY,
                str(payload.get("error") or "balance refused"),
                severity=Severity.ENDS_RUN,
            )

        _log.info("balance ok solves=%s", payload.get("estimated_solves"))
        return payload

    def solve(self, cookie: str) -> dict[str, Any]:
        """One attempt on one account. Returns the timings dict.

        Takes the bare cookie value; the `.ROBLOSECURITY=` wrapper dibycap wants
        is this client's business, not the worker's. The cookie goes into the
        request body and nowhere else: it is never logged and never copied into
        an error (spec 8.2).
        """
        body = {"cookie": f"{COOKIE_FIELD}={cookie}"}
        started = self._accepted(self._post("/createTask", body), "solve")

        task_id = started.get("task_id")
        if not task_id:
            raise _refusal(started)

        for _ in range(POLL_ATTEMPTS):
            result = self._accepted(self._post("/getTask", {"task_id": task_id}), "solve")

            if result.get("status") in UNFINISHED_STATUS:
                self._sleep(_wait_seconds(result))
                continue
            if not result.get("success"):
                raise _refusal(result)
            timings = result.get("timings")
            return timings if isinstance(timings, dict) else {}

        raise AppError(ErrorCode.UNKNOWN, "solve timeout", severity=Severity.RETRY)

    def _accepted(self, response: Any, call: str) -> dict[str, Any]:
        """The payload of a call the key was allowed to make."""
        if response.status_code in REFUSED_STATUS:
            raise AppError(
                ErrorCode.BAD_API_KEY,
                f"{call} http {response.status_code}",
                severity=Severity.ENDS_RUN,
            )

        return _as_object(response)

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        try:
            return self._session.post(
                f"{API_URL}{path}",
                json=body,
                headers={"X-API-Key": self._api_key},
                timeout=TIMEOUT_SECONDS,
            )
        except Exception as error:  # any transport failure reads the same way
            raise AppError(
                ErrorCode.NO_INTERNET,
                f"dibycap {type(error).__name__}",
                severity=Severity.WAIT_IT_OUT,
            ) from error


def _refusal(payload: dict[str, Any]) -> AppError:
    """The typed error a refused solve becomes, keeping the raw dibycap code.

    Only a paused service is waited out: every other refusal is about the key or
    about the account, and neither is fixed by waiting (ADR 0003).
    """
    code = _code_of(payload)
    # A refusal not in the table is an ordinary failed attempt: 28.6% of them
    # fail (spec 2), and the worker's job is to try again.
    mapped, severity = REFUSALS.get(code, (ErrorCode.UNKNOWN, Severity.RETRY))
    return AppError(mapped, code, severity=severity)


def _code_of(payload: dict[str, Any]) -> str:
    """The dibycap code in a refusal, or `NO_CODE` when it is free text.

    Case and spacing are levelled first, because the zero-balance answer shape
    has never been seen (spec 15) and `Insufficient balance` must read the same
    as `insufficient_balance`. The whole string is then matched: this is never a
    substring test (spec 9.7), so `invalid_api_key_format` stays its own code.
    """
    raw = str(payload.get("error") or payload.get("message") or "").strip().lower()
    code = SPACES.sub("_", raw)
    return code if CODE_SHAPE.match(code) else NO_CODE


def _wait_seconds(result: dict[str, Any]) -> float:
    """How long dibycap asked us to wait, with a floor under it."""
    asked = result.get("retry_after_ms")
    milliseconds = asked if isinstance(asked, (int, float)) and asked > 0 else DEFAULT_RETRY_MS
    return max(MIN_POLL_SECONDS, milliseconds / 1000)


def _as_object(response: Any) -> dict[str, Any]:
    """A body that is not a JSON object is a fault, not a crash."""
    try:
        payload = response.json()
    except Exception as error:
        raise AppError(
            ErrorCode.UNKNOWN, "dibycap sent no JSON", severity=Severity.WAIT_IT_OUT
        ) from error
    if not isinstance(payload, dict):
        raise AppError(
            ErrorCode.UNKNOWN,
            "dibycap sent an unexpected shape",
            severity=Severity.WAIT_IT_OUT,
        )
    return payload


def _new_session() -> Any:
    # Imported here, not at module top, so the tests and the UI never pay for
    # curl_cffi's binary import just to name this module.
    from curl_cffi import requests

    return requests.Session()
