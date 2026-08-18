"""is_eligible(account, device) -> bool.

Spec 6 and [ADR 0001](../../docs/adr/0001-eligibility-is-a-blocklist.md): the one
business rule in the app, pure, and testable with plain dicts and no network.

It is a **blocklist**. `error == "CAPTCHA"` and no `error` at all both pass,
because farmsync never clears that flag when a captcha is solved, so it is stale
by design and worthless as a positive signal.
"""
from __future__ import annotations

from typing import Any

BLOCKED_ERRORS = frozenset({"FACEVERIFICATION", "MODERATED", "DEAD"})


def is_eligible(account: dict[str, Any], device: dict[str, Any] | None) -> bool:
    """True when the account is worth a solve. `device` is its device, or None.

    A None device is the 3,915 accounts that belong to no device at all. They are
    skipped on purpose, as a stated rule rather than a side effect of the
    liveness test: solving them is a different job with a different destination
    (spec 14).
    """
    if device is None:
        # The 3,915 accounts that belong to no device are skipped on purpose,
        # as a rule of its own rather than a side effect of the liveness test:
        # solving them is a different job with a different destination (spec 14).
        return False

    if not is_live(device):
        return False

    return (
        bool(account.get("enabled"))
        and not account.get("running")
        and _error_of(account) not in BLOCKED_ERRORS
        and not account.get("dead_cookie")
        and bool(account.get("cookie"))
    )


def is_live(device: dict[str, Any] | None) -> bool:
    """A device is live when it is running something.

    `active_accounts > 0` is the only trustworthy signal: `client_running` is the
    string "LDPlayer" on every device, `is_enabled` is true on every device, and a
    dead device keeps sending a fresh `last_updated` (ADR 0001).
    """
    if not isinstance(device, dict):
        return False
    active = device.get("active_accounts")
    return isinstance(active, int) and not isinstance(active, bool) and active > 0


def eligible_accounts(
    accounts: list[dict[str, Any]], devices: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The eligible accounts, paired with their device by `device_id`."""
    by_id = {device.get("id"): device for device in devices if isinstance(device, dict)}

    return [
        account
        for account in accounts
        if isinstance(account, dict)
        and is_eligible(account, by_id.get(account.get("device_id")))
    ]


def _error_of(account: dict[str, Any]) -> str:
    error = account.get("error")
    return error.strip().upper() if isinstance(error, str) else ""
