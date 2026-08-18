"""The Settings screen really draws, and the gear/back path works."""
from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from nicegui.testing import User

from farmsync_solver import config, keys
from farmsync_solver._version import VERSION
from farmsync_solver.ui import messages, settings

pytest_plugins = ["nicegui.testing.user_plugin"]

BALANCE = {"success": True, "estimated_solves": 5662, "price_per_1k": 1.5}


def _good_key(key: str, session: Any | None = None) -> dict[str, Any]:
    return BALANCE


@pytest.fixture
def saved_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ui_app: ModuleType) -> Path:
    path = tmp_path / "config.json"
    monkeypatch.setattr(config, "default_path", lambda: path)
    monkeypatch.setattr(keys, "check_api_key", _good_key)
    config.save(config.Config(api_key="abc", farm_token="xyz"), path)
    ui_app.load_config()
    return path


async def _open_settings(user: User) -> None:
    await user.open("/")
    await user.should_see(marker="settings-gear")
    user.find(marker="settings-gear").click()
    await user.should_see(messages.SETTINGS_TITLE)


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_the_gear_opens_settings_and_the_back_arrow_returns_home(
    user: User, saved_keys: Path
) -> None:
    await _open_settings(user)
    await user.should_see(messages.SETTINGS_SPEED_LABEL)

    user.find(marker="settings-back").click()
    await user.should_see(messages.HOME_START)


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_settings_shows_the_version_and_no_about_screen(
    user: User, saved_keys: Path
) -> None:
    await _open_settings(user)

    await user.should_see(VERSION)


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_speed_offers_the_four_choices_and_saves_the_pick(
    user: User, saved_keys: Path
) -> None:
    await _open_settings(user)
    toggle: Any = next(iter(user.find(marker="speed-toggle").elements))

    assert list(toggle.options) == list(config.SPEED_CHOICES)
    assert toggle.value == 100

    toggle.set_value(50)
    await user.should_see(messages.SETTINGS_SAVED)
    assert config.load(saved_keys).speed_percent == 50


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_forget_my_keys_asks_first_then_returns_to_setup(
    user: User, saved_keys: Path, ui_app: ModuleType
) -> None:
    await _open_settings(user)
    user.find(messages.SETTINGS_FORGET).click()
    await user.should_see(messages.SETTINGS_FORGET_QUESTION)

    user.find(messages.SETTINGS_FORGET_YES).click()

    await user.should_see(messages.SETUP_BUTTON)
    assert config.load(saved_keys).is_ready is False
    assert ui_app.first_screen(ui_app.current_config()) == "setup"


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_cancelling_forget_keeps_the_keys(user: User, saved_keys: Path) -> None:
    await _open_settings(user)
    user.find(messages.SETTINGS_FORGET).click()
    await user.should_see(messages.SETTINGS_FORGET_QUESTION)

    user.find(messages.SETTINGS_CANCEL).click()

    await user.should_see(marker="forget-dialog")
    assert next(iter(user.find(marker="forget-dialog").elements)).value is False
    assert config.load(saved_keys).is_ready is True


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_a_run_locks_the_keys_and_speed_but_leaves_the_screen_readable(
    user: User, saved_keys: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "is_running", lambda: True)

    await _open_settings(user)

    await user.should_see(messages.SETTINGS_LOCKED)
    await user.should_see(messages.SETTINGS_SPEED_LABEL)  # the rest stays readable
    assert next(iter(user.find(marker="speed-toggle").elements)).enabled is False
    assert next(iter(user.find(marker="settings-api-key").elements)).enabled is False
    assert next(iter(user.find(marker="settings-farm-token").elements)).enabled is False
    assert next(iter(user.find(marker="settings-back").elements)).enabled is True


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_the_saved_keys_are_never_sent_to_the_page(user: User, saved_keys: Path) -> None:
    await _open_settings(user)

    for marker in ("settings-api-key", "settings-farm-token"):
        assert not next(iter(user.find(marker=marker).elements)).value


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_new_keys_are_checked_and_saved_from_settings(
    user: User, saved_keys: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keys, "check_farm_token", lambda token, session=None: None)

    await _open_settings(user)
    user.find(marker="settings-api-key").type("new-key")
    user.find(marker="settings-farm-token").type("new-token")
    user.find(messages.SETTINGS_SAVE_KEYS).click()

    await user.should_see(messages.SETTINGS_SAVED)
    assert config.load(saved_keys).api_key == "new-key"
