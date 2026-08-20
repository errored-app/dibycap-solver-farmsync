"""What a `/balance` payload means, in solves and money.

Spec 7. The rules live here rather than in the screen, so the header, the Speed
control and the run all read the same payload the same way.

Four fields are read: `estimated_solves`, `price_per_1k`, `balance` and
`max_concurrent`. `active` and `type` are ignored on purpose (spec 7),
`price_per_1k` is never shown — it turns solves into money, and a run keeps
the last one it read in its history row (spec 10.2) — and `max_concurrent` is
never shown either: it only turns Speed into a thread count.
"""
from __future__ import annotations

from typing import Any

LOW_SOLVES = 1000
SOLVES_PER_PRICE_UNIT = 1000


def solves(balance: dict[str, Any]) -> int:
    """`estimated_solves` as a whole number. Missing or odd values read as 0."""
    value = balance.get("estimated_solves")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def price(balance: dict[str, Any]) -> float | None:
    """What a thousand solves cost, or None when the payload carries no price.

    None rather than zero, because a payload that names no price and one that
    names a price of nothing are different facts, and a caller keeping the last
    price a run read has to tell them apart (spec 10.2).
    """
    return _number(balance.get("price_per_1k"))


def money(balance: dict[str, Any]) -> float:
    """The money left, derived from the price of a thousand solves.

    The `balance` field is the fallback only: it is the money the key holds,
    while the figure beside the solves count must be the money those solves are
    worth. The two agree on every payload measured so far.
    """
    per_1k = price(balance)
    if per_1k is not None:
        return solves(balance) * per_1k / SOLVES_PER_PRICE_UNIT
    return _number(balance.get("balance")) or 0.0


def max_concurrent(balance: dict[str, Any]) -> int:
    """How many solves the key allows at once. Missing or odd values read as 0."""
    value = balance.get("max_concurrent")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def threads(max_at_once: int, speed_percent: int) -> int:
    """Spec 5.4: floor(max_concurrent x speed_percent / 100), minimum 1.

    The one place the formula lives. It takes the number, not the payload: a run
    with no `max_concurrent` does not start at all (spec 5.4), so the caller
    checks the payload before it asks for a thread count.
    """
    return max(1, max_at_once * speed_percent // 100)


def is_low(balance: dict[str, Any]) -> bool:
    """Under the fixed threshold. A warning only; it never blocks a run."""
    return solves(balance) < LOW_SOLVES


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
