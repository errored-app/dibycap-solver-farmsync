"""§9.5: two bulk calls per round, gzip asserted, and only eligible accounts back."""
from __future__ import annotations

from typing import Any

import pytest

from farmsync_solver.engine.farmsync import Farmsync
from farmsync_solver.errors import AppError, ErrorCode

from fakes import FakeResponse, FakeSession

DEVICES = [{"id": 8, "active_accounts": 12}, {"id": 15, "active_accounts": 0}]
ACCOUNTS = [
    {
        "username": "keep",
        "device_id": 8,
        "enabled": True,
        "running": False,
        "error": "CAPTCHA",
        "dead_cookie": False,
        "cookie": "cookie-1",
    },
    {
        "username": "dead-device",
        "device_id": 15,
        "enabled": True,
        "running": False,
        "error": "",
        "dead_cookie": False,
        "cookie": "cookie-2",
    },
    {
        "username": "no-device",
        "device_id": None,
        "enabled": True,
        "running": False,
        "error": "",
        "dead_cookie": False,
        "cookie": "cookie-3",
    },
]


def healthy_session() -> FakeSession:
    return FakeSession(
        {
            "https://api.farmsync.cloud/api/self/accounts": FakeResponse(payload=ACCOUNTS),
            "https://api.farmsync.cloud/api/devices/": FakeResponse(payload=DEVICES),
        }
    )


def test_the_accounts_call_is_one_bulk_request() -> None:
    session = healthy_session()

    accounts = Farmsync("token", session=session).accounts()

    assert session.urls == ["https://api.farmsync.cloud/api/self/accounts"]
    assert accounts == ACCOUNTS


def test_the_accounts_call_asks_for_gzip() -> None:
    """Uncompressed the body is 103 MB and the call never finishes."""
    session = healthy_session()

    Farmsync("token", session=session).accounts()

    assert "gzip" in session.headers.get("Accept-Encoding", "")


def test_an_accounts_call_without_gzip_is_refused_before_it_is_sent() -> None:
    session = healthy_session()
    client = Farmsync("token", session=session)
    session.headers["Accept-Encoding"] = "identity"

    with pytest.raises(AppError) as caught:
        client.accounts()
    assert caught.value.code is ErrorCode.UNKNOWN
    assert session.urls == []


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_accounts_call_is_a_bad_token(status: int) -> None:
    session = FakeSession(
        {
            "https://api.farmsync.cloud/api/self/accounts": FakeResponse(
                status_code=status, payload={"detail": "nope"}
            )
        }
    )

    with pytest.raises(AppError) as caught:
        Farmsync("wrong", session=session).accounts()
    assert caught.value.code is ErrorCode.BAD_FARM_TOKEN


def test_a_cloudflare_html_page_does_not_crash_the_accounts_call() -> None:
    session = FakeSession(
        {
            "https://api.farmsync.cloud/api/self/accounts": FakeResponse(
                text="<!DOCTYPE html><title>Just a moment...</title>"
            )
        }
    )

    with pytest.raises(AppError) as caught:
        Farmsync("wrong", session=session).accounts()
    assert caught.value.code is ErrorCode.BAD_FARM_TOKEN


def test_a_dead_network_reads_as_no_internet() -> None:
    session = FakeSession({"https://api.farmsync.cloud/api/self/accounts": OSError("down")})

    with pytest.raises(AppError) as caught:
        Farmsync("token", session=session).accounts()
    assert caught.value.code is ErrorCode.NO_INTERNET


def test_discovery_makes_exactly_two_calls() -> None:
    session = healthy_session()

    Farmsync("token", session=session).discover()

    assert session.urls == [
        "https://api.farmsync.cloud/api/self/accounts",
        "https://api.farmsync.cloud/api/devices/",
    ]


def test_discovery_returns_only_eligible_accounts() -> None:
    """Callers never re-filter."""
    picked = Farmsync("token", session=healthy_session()).discover()

    assert [item["username"] for item in picked] == ["keep"]
