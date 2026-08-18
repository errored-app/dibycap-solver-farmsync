"""§6 and ADR 0001: the blocklist, as one pure function over plain dicts."""
from __future__ import annotations

from typing import Any

import pytest

from farmsync_solver.engine import eligibility

LIVE_DEVICE: dict[str, Any] = {"id": 8, "active_accounts": 12}
DEAD_DEVICE: dict[str, Any] = {"id": 15, "active_accounts": 0}


def account(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "username": "someone",
        "device_id": 8,
        "enabled": True,
        "running": False,
        "error": "CAPTCHA",
        "dead_cookie": False,
        "cookie": "_|WARNING:-cookie|_",
    }
    return {**base, **changes}


def test_a_plain_solvable_account_passes() -> None:
    assert eligibility.is_eligible(account(), LIVE_DEVICE)


def test_a_captcha_flag_and_no_error_at_all_both_pass() -> None:
    """The rule is a blocklist: `CAPTCHA` is stale by design, so neither is trusted."""
    assert eligibility.is_eligible(account(error="CAPTCHA"), LIVE_DEVICE)
    assert eligibility.is_eligible(account(error=None), LIVE_DEVICE)
    assert eligibility.is_eligible(account(error=""), LIVE_DEVICE)


def test_a_disabled_account_is_skipped() -> None:
    assert not eligibility.is_eligible(account(enabled=False), LIVE_DEVICE)


def test_an_account_already_running_is_skipped() -> None:
    assert not eligibility.is_eligible(account(running=True), LIVE_DEVICE)


@pytest.mark.parametrize("error", ["FACEVERIFICATION", "MODERATED", "DEAD"])
def test_the_three_blocked_errors_are_skipped(error: str) -> None:
    assert not eligibility.is_eligible(account(error=error), LIVE_DEVICE)


def test_a_blocked_error_is_read_whatever_its_case() -> None:
    assert not eligibility.is_eligible(account(error="moderated"), LIVE_DEVICE)


def test_a_dead_cookie_is_skipped() -> None:
    assert not eligibility.is_eligible(account(dead_cookie=True), LIVE_DEVICE)


@pytest.mark.parametrize("cookie", ["", None])
def test_an_empty_cookie_is_skipped(cookie: Any) -> None:
    assert not eligibility.is_eligible(account(cookie=cookie), LIVE_DEVICE)


def test_an_account_on_a_device_with_nothing_running_is_skipped() -> None:
    assert not eligibility.is_eligible(account(device_id=15), DEAD_DEVICE)


def test_an_account_with_no_device_is_skipped() -> None:
    """The 3,915 device-less accounts are out of scope (spec §14)."""
    assert not eligibility.is_eligible(account(device_id=None), None)


def test_the_rule_never_touches_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("eligibility opened a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    assert eligibility.is_eligible(account(), LIVE_DEVICE)


def test_selection_keeps_only_the_eligible_accounts() -> None:
    accounts = [
        account(username="keep", device_id=8),
        account(username="dead-device", device_id=15),
        account(username="no-device", device_id=None),
        account(username="unknown-device", device_id=999),
        account(username="disabled", device_id=8, enabled=False),
    ]

    picked = eligibility.eligible_accounts(accounts, [LIVE_DEVICE, DEAD_DEVICE])

    assert [item["username"] for item in picked] == ["keep"]


def test_selection_survives_junk_in_the_payload() -> None:
    accounts = [account(username="keep"), {"nonsense": True}]

    picked = eligibility.eligible_accounts(accounts, [LIVE_DEVICE, {"no_id": True}])

    assert [item["username"] for item in picked] == ["keep"]
