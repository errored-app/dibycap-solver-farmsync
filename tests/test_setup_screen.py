"""§4.1: check both keys live, report per box, save only when both pass."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from farmsync_solver import config
from farmsync_solver.errors import AppError, ErrorCode
from farmsync_solver.ui import messages, setup

BALANCE = {"success": True, "estimated_solves": 5662, "balance": 8.4938, "max_concurrent": 65}


def good_key(key: str, session: Any | None = None) -> dict[str, Any]:
    return BALANCE


def good_token(token: str, session: Any | None = None) -> None:
    return None


def refusing_key(code: ErrorCode) -> Callable[..., dict[str, Any]]:
    def check(key: str, session: Any | None = None) -> dict[str, Any]:
        raise AppError(code, "refused")

    return check


def refusing_token(code: ErrorCode) -> Callable[..., None]:
    def check(token: str, session: Any | None = None) -> None:
        raise AppError(code, "refused")

    return check


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    return tmp_path / "config.json"


def test_two_good_keys_are_saved(config_file: Path) -> None:
    result = setup.verify_and_save(
        "abc", "xyz", path=config_file, check_key=good_key, check_token=good_token
    )

    assert result.saved is True
    assert result.note == "Key works — 5,662 captchas left"
    assert config.load(config_file).api_key == "abc"


def test_a_bad_api_key_lands_on_its_own_box(config_file: Path) -> None:
    result = setup.verify_and_save(
        "wrong",
        "xyz",
        path=config_file,
        check_key=refusing_key(ErrorCode.BAD_API_KEY),
        check_token=good_token,
    )

    assert result.saved is False
    assert result.api_key_error == messages.for_code(ErrorCode.BAD_API_KEY)
    assert result.farm_token_error == ""
    assert config_file.exists() is False


def test_a_bad_token_lands_on_its_own_box(config_file: Path) -> None:
    result = setup.verify_and_save(
        "abc",
        "wrong",
        path=config_file,
        check_key=good_key,
        check_token=refusing_token(ErrorCode.BAD_FARM_TOKEN),
    )

    assert result.saved is False
    assert result.farm_token_error == messages.for_code(ErrorCode.BAD_FARM_TOKEN)
    assert result.api_key_error == ""


def test_both_boxes_report_at_once(config_file: Path) -> None:
    result = setup.verify_and_save(
        "wrong",
        "wrong",
        path=config_file,
        check_key=refusing_key(ErrorCode.BAD_API_KEY),
        check_token=refusing_token(ErrorCode.BAD_FARM_TOKEN),
    )

    assert result.api_key_error and result.farm_token_error


def test_an_empty_box_is_asked_for_without_a_network_call(config_file: Path) -> None:
    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("an empty box must not be sent anywhere")

    result = setup.verify_and_save(
        "  ", "", path=config_file, check_key=never, check_token=never
    )

    assert result.saved is False
    assert result.api_key_error == messages.NEEDS_API_KEY
    assert result.farm_token_error == messages.NEEDS_FARM_TOKEN


def test_surrounding_spaces_are_trimmed_before_saving(config_file: Path) -> None:
    setup.verify_and_save(
        "  abc  ", " xyz ", path=config_file, check_key=good_key, check_token=good_token
    )

    assert config.load(config_file).api_key == "abc"


def test_no_internet_is_explained_on_both_boxes(config_file: Path) -> None:
    result = setup.verify_and_save(
        "abc",
        "xyz",
        path=config_file,
        check_key=refusing_key(ErrorCode.NO_INTERNET),
        check_token=refusing_token(ErrorCode.NO_INTERNET),
    )

    assert result.api_key_error == messages.for_code(ErrorCode.NO_INTERNET)
    assert result.farm_token_error == messages.for_code(ErrorCode.NO_INTERNET)


def test_a_saved_speed_is_kept(config_file: Path) -> None:
    config.save(config.Config(api_key="old", farm_token="old", speed_percent=50), config_file)

    setup.verify_and_save(
        "abc", "xyz", path=config_file, check_key=good_key, check_token=good_token
    )

    assert config.load(config_file).speed_percent == 50


def test_a_key_with_no_credit_left_is_refused(config_file: Path) -> None:
    result = setup.verify_and_save(
        "abc",
        "xyz",
        path=config_file,
        check_key=refusing_key(ErrorCode.NO_CREDIT),
        check_token=good_token,
    )

    assert result.saved is False
    assert result.api_key_error == messages.for_code(ErrorCode.NO_CREDIT)
    assert config_file.exists() is False
