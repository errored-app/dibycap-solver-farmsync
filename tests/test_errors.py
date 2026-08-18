"""The stable error codes are part of the contract with the UI and the updater."""
from __future__ import annotations

import pytest

from farmsync_solver.errors import AppError, ErrorCode


def test_every_stable_code_exists() -> None:
    assert {code.value for code in ErrorCode} == {
        "BAD_API_KEY",
        "NO_CREDIT",
        "BAD_FARM_TOKEN",
        "NO_INTERNET",
        "UNKNOWN",
    }


def test_code_name_matches_its_value() -> None:
    for code in ErrorCode:
        assert code.name == code.value


def test_app_error_carries_its_code() -> None:
    error = AppError(ErrorCode.NO_CREDIT, "balance is 0")
    assert error.code is ErrorCode.NO_CREDIT
    assert "NO_CREDIT" in str(error)
    assert isinstance(error, Exception)


def test_app_error_defaults_to_unknown() -> None:
    assert AppError.from_exception(ValueError("boom")).code is ErrorCode.UNKNOWN


def test_app_error_from_exception_keeps_an_app_error_as_is() -> None:
    original = AppError(ErrorCode.BAD_API_KEY, "rejected")
    assert AppError.from_exception(original) is original


def test_raising_an_app_error_is_catchable_by_code() -> None:
    with pytest.raises(AppError) as caught:
        raise AppError(ErrorCode.BAD_FARM_TOKEN, "401 from farmsync")
    assert caught.value.code is ErrorCode.BAD_FARM_TOKEN
