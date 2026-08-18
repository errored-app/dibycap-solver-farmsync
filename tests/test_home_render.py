"""The Home screen really draws: a smoke test against a running NiceGUI page."""
from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from nicegui.testing import User

from farmsync_solver import config, keys
from farmsync_solver.errors import AppError, ErrorCode
from farmsync_solver.ui import home, messages

pytest_plugins = ["nicegui.testing.user_plugin"]


def _good(key: str, session: Any | None = None) -> dict[str, Any]:
    return {"success": True, "estimated_solves": 5662, "price_per_1k": 1.5}


def _low(key: str, session: Any | None = None) -> dict[str, Any]:
    return {"success": True, "estimated_solves": 999, "price_per_1k": 1.5}


def _refused(key: str, session: Any | None = None) -> dict[str, Any]:
    raise AppError(ErrorCode.BAD_API_KEY, "refused")


@pytest.fixture
def saved_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ui_app: ModuleType) -> None:
    path = tmp_path / "config.json"
    monkeypatch.setattr(config, "default_path", lambda: path)
    config.save(config.Config(api_key="abc", farm_token="xyz"), path)
    ui_app.load_config()


def _start_button(user: User) -> Any:
    return next(iter(user.find(messages.HOME_START).elements))


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_home_shows_the_credit_header_and_a_start_button(
    user: User, saved_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keys, "check_api_key", _good)

    await user.open("/")
    await user.should_see("5,662 captchas left ($8.49)")
    await user.should_see(messages.HOME_START)
    assert _start_button(user).enabled is True


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_low_credit_turns_the_header_orange_and_still_starts(
    user: User, saved_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keys, "check_api_key", _low)

    await user.open("/")
    await user.should_see("999 captchas left ($1.50)")
    header = next(iter(user.find(marker="credit-header").elements))
    assert home.LOW_COLOUR in header.classes
    assert _start_button(user).enabled is True


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_a_failed_re_check_shows_a_red_line_and_disables_start(
    user: User, saved_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keys, "check_api_key", _refused)

    await user.open("/")
    await user.should_see(messages.for_code(ErrorCode.BAD_API_KEY))
    assert _start_button(user).enabled is False
    tooltip: Any = next(iter(user.find(marker="start-tooltip").elements))
    assert tooltip.text == messages.for_code(ErrorCode.BAD_API_KEY)
