"""§9.3: two plain functions, outside the Engine, that Setup and Home call."""
from __future__ import annotations

import pytest

from farmsync_solver import keys
from farmsync_solver.engine import dibycap, farmsync
from farmsync_solver.errors import AppError, ErrorCode

from fakes import FakeResponse, FakeSession

BALANCE = {
    "success": True,
    "balance": 8.4938,
    "estimated_solves": 5662,
    "price_per_1k": 1.5,
    "max_concurrent": 65,
    "active": 0,
    "type": "limited",
}


def test_the_key_check_asks_dibycap_for_the_balance() -> None:
    session = FakeSession(FakeResponse(payload=BALANCE))
    payload = dibycap.Dibycap("secret", session=session).balance()

    assert session.urls == ["https://api.dibycap.com/balance"]
    assert session.sent_headers["X-API-Key"] == "secret"
    assert payload == BALANCE


def test_the_key_check_returns_the_whole_payload() -> None:
    session = FakeSession(FakeResponse(payload=BALANCE))

    assert keys.check_api_key("secret", session=session)["max_concurrent"] == 65


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_key_is_a_bad_key(status: int) -> None:
    session = FakeSession(FakeResponse(status_code=status, payload={"error": "nope"}))

    with pytest.raises(AppError) as caught:
        keys.check_api_key("wrong", session=session)
    assert caught.value.code is ErrorCode.BAD_API_KEY


def test_a_success_false_payload_is_a_bad_key() -> None:
    session = FakeSession(FakeResponse(payload={"success": False, "error": "invalid_api_key"}))

    with pytest.raises(AppError) as caught:
        keys.check_api_key("wrong", session=session)
    assert caught.value.code is ErrorCode.BAD_API_KEY


def test_a_non_json_answer_from_dibycap_does_not_crash() -> None:
    session = FakeSession(FakeResponse(text="<html>maintenance</html>"))

    with pytest.raises(AppError) as caught:
        keys.check_api_key("secret", session=session)
    assert caught.value.code is ErrorCode.UNKNOWN


def test_a_dead_network_reads_as_no_internet() -> None:
    session = FakeSession(OSError("connection refused"))

    with pytest.raises(AppError) as caught:
        keys.check_api_key("secret", session=session)
    assert caught.value.code is ErrorCode.NO_INTERNET


def test_the_key_never_appears_in_the_error_text() -> None:
    session = FakeSession(FakeResponse(status_code=401, payload={"error": "bad"}))

    with pytest.raises(AppError) as caught:
        keys.check_api_key("super-secret-key", session=session)
    assert "super-secret-key" not in str(caught.value)


def test_the_token_check_asks_farmsync_for_the_devices() -> None:
    session = FakeSession(FakeResponse(payload=[{"id": 1}]))
    devices = farmsync.Farmsync("token", session=session).devices()

    assert session.urls == ["https://api.farmsync.cloud/api/devices/"]
    assert session.headers["Authorization"] == "Bearer token"
    assert devices == [{"id": 1}]


def test_the_token_check_passes_on_a_good_token() -> None:
    session = FakeSession(FakeResponse(payload=[{"id": 1}]))

    keys.check_farm_token("token", session=session)  # no raise


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_token_is_a_bad_token(status: int) -> None:
    session = FakeSession(FakeResponse(status_code=status, payload={"detail": "nope"}))

    with pytest.raises(AppError) as caught:
        keys.check_farm_token("wrong", session=session)
    assert caught.value.code is ErrorCode.BAD_FARM_TOKEN


def test_a_cloudflare_html_page_is_a_bad_token_not_a_crash() -> None:
    session = FakeSession(FakeResponse(text="<!DOCTYPE html><title>Just a moment...</title>"))

    with pytest.raises(AppError) as caught:
        keys.check_farm_token("wrong", session=session)
    assert caught.value.code is ErrorCode.BAD_FARM_TOKEN


def test_a_dead_network_reading_farmsync_is_no_internet() -> None:
    session = FakeSession(OSError("connection refused"))

    with pytest.raises(AppError) as caught:
        keys.check_farm_token("token", session=session)
    assert caught.value.code is ErrorCode.NO_INTERNET


def test_the_devices_call_asks_for_gzip() -> None:
    session = FakeSession(FakeResponse(payload=[]))
    farmsync.Farmsync("token", session=session).devices()

    assert "gzip" in session.headers.get("Accept-Encoding", "")


def test_a_key_with_no_credit_left_is_refused() -> None:
    session = FakeSession(FakeResponse(payload={**BALANCE, "estimated_solves": 0}))

    with pytest.raises(AppError) as caught:
        keys.check_api_key("empty", session=session)
    assert caught.value.code is ErrorCode.NO_CREDIT


def test_a_missing_credit_figure_is_read_as_no_credit() -> None:
    session = FakeSession(FakeResponse(payload={"success": True}))

    with pytest.raises(AppError) as caught:
        keys.check_api_key("odd", session=session)
    assert caught.value.code is ErrorCode.NO_CREDIT


def test_the_raw_balance_call_still_reports_zero_credit() -> None:
    """The header must be able to show 0; only the key check refuses it."""
    session = FakeSession(FakeResponse(payload={**BALANCE, "estimated_solves": 0}))

    assert dibycap.Dibycap("empty", session=session).balance()["estimated_solves"] == 0
