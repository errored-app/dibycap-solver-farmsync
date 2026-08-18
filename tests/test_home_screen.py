"""§4.2 and §7: the Home credit read, without a window."""
from __future__ import annotations

from typing import Any

import pytest

from farmsync_solver.errors import AppError, ErrorCode
from farmsync_solver.ui import home, messages

LIVE = {"success": True, "estimated_solves": 5662, "price_per_1k": 1.5}


def _good(key: str, session: Any | None = None) -> dict[str, Any]:
    return LIVE


def _low(key: str, session: Any | None = None) -> dict[str, Any]:
    return {"success": True, "estimated_solves": 999, "price_per_1k": 1.5}


def _refused(code: ErrorCode) -> Any:
    def check(key: str, session: Any | None = None) -> dict[str, Any]:
        raise AppError(code, "refused")

    return check


def _explodes(key: str, session: Any | None = None) -> dict[str, Any]:
    raise RuntimeError("boom")


def test_a_good_key_gives_the_header_solves_first_money_second() -> None:
    state = home.read_credit("abc", check_key=_good)

    assert state.header == "5,662 captchas left ($8.49)"
    assert state.low is False
    assert state.error == ""
    assert state.can_start is True


def test_credit_under_the_threshold_is_low_but_still_starts() -> None:
    state = home.read_credit("abc", check_key=_low)

    assert state.low is True
    assert state.error == ""
    assert state.can_start is True


def test_a_refused_key_disables_start_and_explains_itself() -> None:
    state = home.read_credit("abc", check_key=_refused(ErrorCode.BAD_API_KEY))

    assert state.error == messages.for_code(ErrorCode.BAD_API_KEY)
    assert state.can_start is False
    assert state.header == messages.CREDIT_UNKNOWN


def test_no_credit_shows_a_zero_header_and_blocks_the_start() -> None:
    state = home.read_credit("abc", check_key=_refused(ErrorCode.NO_CREDIT))

    assert state.header == "0 captchas left ($0.00)"
    assert state.low is True
    assert state.error == messages.for_code(ErrorCode.NO_CREDIT)
    assert state.can_start is False


def test_a_surprise_failure_still_reads_as_a_plain_sentence() -> None:
    state = home.read_credit("abc", check_key=_explodes)

    assert state.error == messages.for_code(ErrorCode.UNKNOWN)
    assert state.can_start is False


@pytest.mark.parametrize("code", list(ErrorCode))
def test_no_error_line_ever_carries_the_key(code: ErrorCode) -> None:
    state = home.read_credit("secret-key", check_key=_refused(code))

    assert "secret-key" not in state.error
    assert "secret-key" not in state.header
