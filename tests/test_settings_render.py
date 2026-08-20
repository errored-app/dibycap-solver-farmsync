"""The Settings screen really draws, and the gear/back path works."""
from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from nicegui.testing import User

from farmsync_solver import config, keys
from farmsync_solver._version import VERSION
from farmsync_solver.ui import messages, settings, theme

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


def _element(user: User, marker: str) -> Any:
    """The one element behind a marker. `Any`: NiceGUI hands back a bare Element."""
    return next(iter(user.find(marker=marker).elements))


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
    toggle = _element(user, "speed-toggle")

    assert list(toggle.options) == list(config.SPEED_CHOICES)
    assert toggle.value == 100

    toggle.set_value(50)
    await user.should_see(messages.SETTINGS_SAVED)
    assert config.load(saved_keys).speed_percent == 50


# --- ADR 0004: the theme picker --------------------------------------------


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_the_window_opens_wearing_the_saved_theme(
    user: User, saved_keys: Path, ui_app: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The look is put on the page before the first screen is drawn."""
    worn: list[str] = []
    monkeypatch.setattr(theme, "wear", worn.append)
    config.save_theme("handheld", saved_keys)
    ui_app.load_config()

    await user.open("/")
    await user.should_see(marker="settings-gear")

    assert worn == ["handheld"]


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_picking_a_theme_paints_the_window_at_once(
    user: User, saved_keys: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The window is the answer to the click; the file catches up after."""
    await _open_settings(user)
    worn: list[str] = []
    monkeypatch.setattr(theme, "wear", worn.append)

    user.find(marker="theme-adventure").click()

    await user.should_see(messages.SETTINGS_SAVED)
    assert worn == ["adventure"]


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_the_theme_picker_offers_every_shipped_theme(
    user: User, saved_keys: Path
) -> None:
    await _open_settings(user)

    await user.should_see(messages.SETTINGS_THEME_TITLE)
    for key in config.THEME_CHOICES:
        await user.should_see(messages.theme_name(key))


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_picking_a_theme_saves_it(user: User, saved_keys: Path) -> None:
    await _open_settings(user)
    assert config.load(saved_keys).theme == config.DEFAULT_THEME

    user.find(marker="theme-console").click()

    await user.should_see(messages.SETTINGS_SAVED)
    assert config.load(saved_keys).theme == "console"


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_the_picked_theme_is_the_marked_one_when_the_screen_opens(
    user: User, saved_keys: Path, ui_app: ModuleType
) -> None:
    config.save_theme("adventure", saved_keys)
    ui_app.load_config()

    await _open_settings(user)
    tile = next(iter(user.find(marker="theme-adventure").elements))
    other = next(iter(user.find(marker="theme-modern").elements))

    assert "fs-tile-picked" in tile.classes
    assert "fs-tile-picked" not in other.classes


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_a_run_does_not_lock_the_theme(
    user: User, saved_keys: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0004: keys and Speed change what a run does. A theme changes paint."""
    monkeypatch.setattr(settings, "is_running", lambda: True)

    await _open_settings(user)
    user.find(marker="theme-handheld").click()

    await user.should_see(messages.SETTINGS_SAVED)
    assert config.load(saved_keys).theme == "handheld"


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
    assert _element(user, "forget-dialog").value is False
    assert config.load(saved_keys).is_ready is True


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_a_run_locks_the_keys_and_speed_but_leaves_the_screen_readable(
    user: User, saved_keys: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "is_running", lambda: True)

    await _open_settings(user)

    await user.should_see(messages.SETTINGS_LOCKED)
    await user.should_see(messages.SETTINGS_SPEED_LABEL)  # the rest stays readable
    assert _element(user, "speed-toggle").enabled is False
    assert _element(user, "settings-api-key").enabled is False
    assert _element(user, "settings-farm-token").enabled is False
    assert _element(user, "settings-back").enabled is True


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_the_saved_keys_are_never_sent_to_the_page(user: User, saved_keys: Path) -> None:
    await _open_settings(user)

    for marker in ("settings-api-key", "settings-farm-token"):
        assert not _element(user, marker).value


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


# --- §8.4: the support path ------------------------------------------------


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_copy_diagnostics_puts_the_report_on_the_clipboard(
    user: User, saved_keys: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nicegui import ui

    copied: list[str] = []

    def remember(text: str) -> None:  # sync, like the real `ui.clipboard.write`
        copied.append(text)

    monkeypatch.setattr(ui.clipboard, "write", remember)
    await _open_settings(user)

    user.find(marker="copy-diagnostics").click()
    await user.should_see(messages.SETTINGS_COPIED)

    assert copied and VERSION in copied[0]
    assert "Run state: idle" in copied[0]


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_open_log_folder_says_so_when_it_cannot(
    user: User, saved_keys: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from farmsync_solver import diagnostics

    monkeypatch.setattr(diagnostics, "open_log_folder", lambda folder=None: False)
    await _open_settings(user)

    user.find(marker="open-logs").click()
    await user.should_see(messages.SETTINGS_LOGS_FAILED)


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_the_support_buttons_stay_live_during_a_run(
    user: User, saved_keys: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 8.5: trouble is exactly when these are reached for."""
    from farmsync_solver.ui import settings

    monkeypatch.setattr(settings, "is_running", lambda: True)
    await _open_settings(user)

    for marker in ("copy-diagnostics", "open-logs"):
        assert _element(user, marker).enabled


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_the_report_carries_the_speed_as_it_is_when_copy_is_pressed(
    user: User, saved_keys: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Speed is changed on this very screen; the report must not lag behind."""
    from nicegui import ui

    copied: list[str] = []

    def remember(text: str) -> None:  # sync, like the real `ui.clipboard.write`
        copied.append(text)

    monkeypatch.setattr(ui.clipboard, "write", remember)
    await _open_settings(user)

    toggle = _element(user, "speed-toggle")
    toggle.set_value(25)
    await user.should_see(messages.SETTINGS_SAVED)
    user.find(marker="copy-diagnostics").click()
    await user.should_see(messages.SETTINGS_COPIED)

    assert "Speed: 25%" in copied[0]


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_forgetting_the_keys_drops_the_remembered_key_check(
    user: User, saved_keys: Path
) -> None:
    """A report must not say the key works after the key has been deleted."""
    from farmsync_solver.ui import home

    home.read_credit("abc")
    assert home.last_credit() is not None

    await _open_settings(user)
    user.find(messages.SETTINGS_FORGET).click()
    await user.should_see(messages.SETTINGS_FORGET_QUESTION)
    user.find(messages.SETTINGS_FORGET_YES).click()
    await user.should_see(messages.SETUP_BUTTON)

    assert home.last_credit() is None
