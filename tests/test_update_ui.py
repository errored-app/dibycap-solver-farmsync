"""§12 on the screens: the bar Home paints, the manual check in Settings.

Only what needs a page open lives here. The stages, the hand-over order and the
words in the bar are `tests/test_update_offer.py`, which needs no window at all.
"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any, Iterator

import pytest
from nicegui.testing import User

from farmsync_solver import config, keys, updater
from farmsync_solver.ui import messages, settings, update_offer

pytest_plugins = ["nicegui.testing.user_plugin"]

UPDATE = updater.Update(
    version="1.2.0",
    setup_name="FarmsyncSolver-Setup-1.2.0.exe",
    setup_url="https://example.test/setup.exe",
    checksums_url="https://example.test/SHA256SUMS.txt",
)


@pytest.fixture(autouse=True)
def no_standing_offer() -> Iterator[None]:
    """The offer lives for the life of the process, so it must not leak."""
    update_offer.forget()
    yield
    update_offer.forget()


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
async def test_home_paints_what_the_offer_is_showing(
    user: User, saved_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bar is the offer's view, put on screen. Its words are tested elsewhere."""
    monkeypatch.setattr(keys, "check_api_key", _good_key)
    monkeypatch.setattr(updater, "check", found())

    await user.open("/")
    await user.should_see(update_offer.current().view().headline)
    await user.should_see(messages.UPDATE_NOW)


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
    # The check made here is the one the bar on Home reads.
    assert update_offer.current().update == UPDATE
