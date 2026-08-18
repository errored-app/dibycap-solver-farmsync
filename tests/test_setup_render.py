"""The Setup screen really draws: a smoke test against a running NiceGUI page."""
from __future__ import annotations

from pathlib import Path

import pytest
from nicegui.testing import User

from farmsync_solver import config, keys
from farmsync_solver.errors import AppError, ErrorCode
from farmsync_solver.ui import app, messages

BALANCE = {"success": True, "estimated_solves": 5662}


def _good_key(key: str, session: object | None = None) -> dict[str, object]:
    return BALANCE


def _good_token(token: str, session: object | None = None) -> None:
    return None


def _refusing_key(key: str, session: object | None = None) -> dict[str, object]:
    raise AppError(ErrorCode.BAD_API_KEY, "refused")

pytest_plugins = ["nicegui.testing.user_plugin"]


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_setup_is_drawn_when_no_keys_are_saved(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "default_path", lambda: tmp_path / "config.json")
    app.load_config()

    await user.open("/")
    await user.should_see(messages.SETUP_BUTTON)
    await user.should_see(messages.SETUP_API_KEY_LABEL)
    await user.should_see(messages.SETUP_FARM_TOKEN_LABEL)


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_a_refused_key_is_reported_under_its_own_box(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "default_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(keys, "check_api_key", _refusing_key)
    monkeypatch.setattr(keys, "check_farm_token", _good_token)
    app.load_config()

    await user.open("/")
    user.find(messages.SETUP_API_KEY_LABEL).type("wrong")
    user.find(messages.SETUP_FARM_TOKEN_LABEL).type("xyz")
    user.find(messages.SETUP_BUTTON).click()

    await user.should_see(messages.for_code(ErrorCode.BAD_API_KEY))
    assert (tmp_path / "config.json").exists() is False


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_two_good_keys_are_saved_and_the_screen_moves_on(
    user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    monkeypatch.setattr(config, "default_path", lambda: path)
    monkeypatch.setattr(keys, "check_api_key", _good_key)
    monkeypatch.setattr(keys, "check_farm_token", _good_token)
    app.load_config()

    await user.open("/")
    user.find(messages.SETUP_API_KEY_LABEL).type("abc")
    user.find(messages.SETUP_FARM_TOKEN_LABEL).type("xyz")
    user.find(messages.SETUP_BUTTON).click()

    await user.should_see(messages.key_works(BALANCE))
    await user.should_not_see(messages.SETUP_BUTTON, retries=100)
    assert config.load(path).api_key == "abc"
