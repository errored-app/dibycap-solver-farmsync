"""§7: how a `/balance` payload becomes the header figures."""
from __future__ import annotations

import pytest

from farmsync_solver import credit

LIVE = {
    "success": True,
    "balance": 8.4938,
    "estimated_solves": 5662,
    "price_per_1k": 1.5,
    "max_concurrent": 65,
    "active": 0,
    "type": "limited",
}


def test_the_measured_payload_reads_as_solves_and_money() -> None:
    assert credit.solves(LIVE) == 5662
    assert credit.money(LIVE) == pytest.approx(8.493)


def test_money_is_derived_from_price_per_1k_not_from_balance() -> None:
    payload = {"estimated_solves": 2000, "price_per_1k": 1.5, "balance": 999.0}

    assert credit.money(payload) == pytest.approx(3.0)


def test_money_falls_back_to_the_balance_field_without_a_price() -> None:
    assert credit.money({"estimated_solves": 10, "balance": 2.5}) == pytest.approx(2.5)


def test_an_empty_payload_reads_as_no_credit() -> None:
    assert credit.solves({}) == 0
    assert credit.money({}) == 0.0


@pytest.mark.parametrize("odd", [None, True, "5662", 12.5])
def test_an_odd_solves_value_reads_as_zero(odd: object) -> None:
    assert credit.solves({"estimated_solves": odd}) == 0


def test_below_the_threshold_is_low() -> None:
    assert credit.is_low({"estimated_solves": 999}) is True


def test_the_threshold_itself_is_not_low() -> None:
    assert credit.is_low({"estimated_solves": credit.LOW_SOLVES}) is False


# --- the thread count (spec 5.4) --------------------------------------------


def test_max_concurrent_is_read_from_the_payload() -> None:
    assert credit.max_concurrent(LIVE) == 65


@pytest.mark.parametrize("odd", [{}, {"max_concurrent": None}, {"max_concurrent": True}])
def test_a_payload_with_no_max_concurrent_reads_as_zero(odd: dict[str, object]) -> None:
    """Zero is not a thread count; it is what makes the run refuse to start."""
    assert credit.max_concurrent(odd) == 0


@pytest.mark.parametrize(("speed", "expected"), [(25, 16), (50, 32), (75, 48), (100, 65)])
def test_the_thread_count_is_derived_from_the_observed_65(speed: int, expected: int) -> None:
    assert credit.threads(credit.max_concurrent(LIVE), speed) == expected


def test_the_thread_count_is_never_below_one() -> None:
    assert credit.threads(1, 25) == 1
