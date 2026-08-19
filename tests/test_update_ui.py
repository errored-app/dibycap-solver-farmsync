"""§12 on the screens: the bar on Home, the manual check in Settings.

The rules being held to here are the ones a user feels: nothing at all when the
app is current, a bar and not a dialog when it is not, and no install while a run
is going.
"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any, Iterator

import pytest
from nicegui.testing import User

from farmsync_solver import config, keys, updater
from farmsync_solver.engine.snapshot import RunSnapshot, RunState
from farmsync_solver.ui import home, messages, settings

pytest_plugins = ["nicegui.testing.user_plugin"]

UPDATE = updater.Update(
    version="1.2.0",
    setup_name="FarmsyncSolver-Setup-1.2.0.exe",
    setup_url="https://example.test/setup.exe",
    checksums_url="https://example.test/SHA256SUMS.txt",
)


@pytest.fixture(autouse=True)
def no_remembered_update() -> Iterator[None]:
    """The found update is process-wide, so it must not leak between tests."""
    updater.remember(None)
    yield
    updater.remember(None)


def found(update: updater.Update | None = UPDATE) -> Any:
    """What a check answers when it reached GitHub."""
    return lambda *args, **kwargs: updater.CheckAnswer(update)


@pytest.fixture
def saved_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ui_app: ModuleType) -> None:
    path = tmp_path / "config.json"
    monkeypatch.setattr(config, "default_path", lambda: path)
    config.save(config.Config(api_key="abc", farm_token="xyz"), path)
    ui_app.load_config()


def _good_key(key: str, session: Any | None = None) -> dict[str, Any]:
    return {"success": True, "estimated_solves": 5662, "price_per_1k": 1.5}


# --- the bar, as a pure answer ---------------------------------------------


def test_no_update_means_no_bar() -> None:
    assert home.update_bar(None, home.UpdateStage.READY).visible is False


def test_a_found_update_offers_its_version_and_a_live_button() -> None:
    bar = home.update_bar(UPDATE, home.UpdateStage.READY)

    assert bar.visible is True
    assert bar.headline == "Version 1.2.0 is ready."
    assert bar.button_enabled is True
    assert bar.note == ""
    assert bar.progress_visible is False


def test_a_run_locks_the_button_and_says_why() -> None:
    bar = home.update_bar(UPDATE, home.UpdateStage.LOCKED)

    assert bar.button_enabled is False
    assert bar.note == messages.UPDATE_LOCKED


def test_a_download_shows_a_progress_bar_and_no_second_press() -> None:
    bar = home.update_bar(UPDATE, home.UpdateStage.DOWNLOADING, fraction=0.4)

    assert bar.progress_visible is True
    assert bar.fraction == 0.4
    assert bar.button_enabled is False
    assert bar.note == messages.UPDATE_DOWNLOADING


def test_a_failed_download_says_the_app_still_works_and_offers_another_go() -> None:
    bar = home.update_bar(UPDATE, home.UpdateStage.FAILED)

    assert bar.note == messages.UPDATE_FAILED
    assert bar.button_enabled is True


# --- the bar, on the running screen ----------------------------------------


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_home_shows_nothing_when_the_app_is_current(
    user: User, saved_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keys, "check_api_key", _good_key)
    monkeypatch.setattr(updater, "check", found(None))

    await user.open("/")
    await user.should_see(messages.HOME_START)
    await user.should_not_see(messages.UPDATE_NOW)


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_home_offers_the_update_the_startup_check_found(
    user: User, saved_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keys, "check_api_key", _good_key)
    monkeypatch.setattr(updater, "check", found())

    await user.open("/")
    await user.should_see("Version 1.2.0 is ready.")
    await user.should_see(messages.UPDATE_NOW)


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_pressing_update_now_downloads_then_hands_over(
    user: User, saved_keys: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    setup = tmp_path / "FarmsyncSolver-Setup-1.2.0.exe"
    order: list[str] = []
    on_close: list[Any] = []
    monkeypatch.setattr(keys, "check_api_key", _good_key)
    monkeypatch.setattr(updater, "check", found())
    monkeypatch.setattr(updater, "download", lambda update, **kwargs: setup)
    monkeypatch.setattr(updater, "install", lambda started: order.append(f"install {started.name}"))
    monkeypatch.setattr(home.native_app, "on_shutdown", on_close.append)
    monkeypatch.setattr(home.native_app, "shutdown", lambda: order.append("closed"))

    await user.open("/")
    await user.should_see(messages.UPDATE_NOW)
    await _screen_of(user).press_update()

    # The window goes first; the installer is what the closing app leaves behind.
    assert order == ["closed"]
    on_close[-1]()
    assert order == ["closed", f"install {setup.name}"]


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_a_failed_download_leaves_the_app_open_and_says_so(
    user: User, saved_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[str] = []
    monkeypatch.setattr(keys, "check_api_key", _good_key)
    monkeypatch.setattr(updater, "check", found())
    monkeypatch.setattr(updater, "download", lambda update, **kwargs: None)
    monkeypatch.setattr(home.native_app, "shutdown", lambda: closed.append("closed"))

    await user.open("/")
    await user.should_see(messages.UPDATE_NOW)
    await _screen_of(user).press_update()

    await user.should_see(messages.UPDATE_FAILED)
    assert closed == []


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_a_run_in_progress_installs_nothing(
    user: User, saved_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloads: list[Any] = []
    checks: list[str] = []
    monkeypatch.setattr(keys, "check_api_key", _good_key)
    monkeypatch.setattr(updater, "check", found())
    monkeypatch.setattr(updater, "download", lambda update, **kwargs: downloads.append(update))

    await user.open("/")
    await user.should_see(messages.UPDATE_NOW)

    screen = _screen_of(user)
    monkeypatch.setattr(screen._worker, "snapshot", lambda: RunSnapshot(state=RunState.SOLVING))
    monkeypatch.setattr(updater, "check", lambda *args, **kwargs: checks.append("asked"))
    await screen.press_update()
    await screen.look_for_update()

    assert downloads == []
    assert checks == []  # a run is not interrupted, not even by a question


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_a_run_started_during_the_download_stops_the_install(
    user: User, saved_keys: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    closed: list[str] = []
    monkeypatch.setattr(keys, "check_api_key", _good_key)
    monkeypatch.setattr(updater, "check", found())
    monkeypatch.setattr(home.native_app, "shutdown", lambda: closed.append("closed"))

    await user.open("/")
    await user.should_see(messages.UPDATE_NOW)
    screen = _screen_of(user)

    def start_a_run_mid_download(update: Any, **kwargs: Any) -> Path:
        monkeypatch.setattr(screen._worker, "snapshot", lambda: RunSnapshot(state=RunState.SOLVING))
        return tmp_path / "FarmsyncSolver-Setup-1.2.0.exe"

    monkeypatch.setattr(updater, "download", start_a_run_mid_download)
    await screen.press_update()

    assert closed == []
    await user.should_see(messages.UPDATE_LOCKED)


def _screen_of(user: User) -> Any:
    """The `_Screen` the open page built, found through the button it wired up.

    The screen is private to `home`, and pressing the button through the page
    would not wait for the download it starts. This reaches the same object the
    click would have called.
    """
    button = next(iter(user.find(messages.UPDATE_NOW).elements))
    for listener in button._event_listeners.values():
        owner = getattr(listener.handler, "__self__", None)
        if owner is not None:
            return owner
    raise AssertionError("the update button has no screen behind it")


# --- the manual check in Settings ------------------------------------------


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_settings_says_when_there_is_nothing_to_install(
    user: User, saved_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keys, "check_api_key", _good_key)
    monkeypatch.setattr(updater, "check", found(None))

    await user.open("/")
    user.find(marker="settings-gear").click()
    await user.should_see(messages.SETTINGS_CHECK_UPDATES)
    user.find(messages.SETTINGS_CHECK_UPDATES).click()

    await user.should_see(messages.SETTINGS_UP_TO_DATE)


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_settings_does_not_call_a_check_it_could_not_make_up_to_date(
    user: User, saved_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keys, "check_api_key", _good_key)
    monkeypatch.setattr(
        updater, "check", lambda *args, **kwargs: updater.CheckAnswer(None, reached_github=False)
    )

    await user.open("/")
    user.find(marker="settings-gear").click()
    await user.should_see(messages.SETTINGS_CHECK_UPDATES)
    user.find(messages.SETTINGS_CHECK_UPDATES).click()

    await user.should_see(messages.SETTINGS_CHECK_FAILED)


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_settings_points_a_found_update_back_at_home(
    user: User, saved_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(keys, "check_api_key", _good_key)
    monkeypatch.setattr(updater, "check", found())

    await user.open("/")
    user.find(marker="settings-gear").click()
    await user.should_see(messages.SETTINGS_CHECK_UPDATES)
    user.find(messages.SETTINGS_CHECK_UPDATES).click()

    await user.should_see(messages.update_found("1.2.0"))
    assert settings.is_running() is False
