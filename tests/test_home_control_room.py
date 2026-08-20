"""§4.2, §4.4, §5.2 and §5.6: the control room really draws, and Start really presses.

The engine is a stand-in here. What is under test is the screen: that its controls
are built once and survive the 5 Hz refresh, that the press reaches the engine
with the saved values, and that a failure never opens a dialog.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from nicegui.testing import User

from farmsync_solver import config, engine as engine_module, keys
from farmsync_solver.engine.snapshot import (
    IDLE,
    AccountRow,
    Headline,
    Result,
    RunSnapshot,
    RunState,
)
from farmsync_solver.ui import home, messages

pytest_plugins = ["nicegui.testing.user_plugin"]

BALANCE = {"success": True, "estimated_solves": 5662, "price_per_1k": 1.5}

# Long enough for several refreshes at `home.REFRESH_SECONDS`, so a test that
# presses a button presses one the refresh has already been over many times.
SETTLE_SECONDS = home.REFRESH_SECONDS * 5


class FakeEngine:
    """The four members of spec 9.2's seam, and nothing else."""

    def __init__(self) -> None:
        self.snapshot_value: RunSnapshot = IDLE
        self.started: list[tuple[str, str, int]] = []
        self.stops = 0
        self._rows: list[AccountRow] = []

    def start(self, api_key: str, farm_token: str, speed_percent: int) -> None:
        self.started.append((api_key, farm_token, speed_percent))
        self.snapshot_value = replace(IDLE, state=RunState.DISCOVERING, round_number=1)

    def stop(self) -> None:
        self.stops += 1
        self.snapshot_value = replace(self.snapshot_value, state=RunState.STOPPING)

    def snapshot(self) -> RunSnapshot:
        return self.snapshot_value

    def take_new_rows(self) -> list[AccountRow]:
        rows, self._rows = self._rows, []
        return rows

    # --- what a test drives it with ---------------------------------------

    def show(self, **changes: Any) -> None:
        self.snapshot_value = replace(self.snapshot_value, **changes)

    def finish(self, username: str, outcome: Result, detail: str = "") -> None:
        self._rows.append(AccountRow(username=username, outcome=outcome, detail=detail, at=0.0))


def _good_key(key: str, session: Any | None = None) -> dict[str, Any]:
    return BALANCE


@pytest.fixture
def run_engine(monkeypatch: pytest.MonkeyPatch) -> FakeEngine:
    fake = FakeEngine()
    monkeypatch.setattr(engine_module, "current", lambda: fake)
    return fake


@pytest.fixture
def saved_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ui_app: ModuleType) -> None:
    path = tmp_path / "config.json"
    monkeypatch.setattr(config, "default_path", lambda: path)
    monkeypatch.setattr(keys, "check_api_key", _good_key)
    config.save(config.Config(api_key="abc", farm_token="xyz", speed_percent=50), path)
    ui_app.load_config()


def _element(user: User, marker: str) -> Any:
    return next(iter(user.find(marker=marker).elements))


def _table(user: User) -> Any:
    return _element(user, "run-table")


async def _open_home(user: User) -> None:
    await user.open("/")
    await user.should_see(marker="run-button")
    await asyncio.sleep(SETTLE_SECONDS)


# --- Start and Stop (spec 5.2, 5.7) -----------------------------------------


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_start_runs_a_real_round_with_the_saved_values(
    user: User, saved_keys: None, run_engine: FakeEngine
) -> None:
    await _open_home(user)

    user.find(marker="run-button").click()
    await asyncio.sleep(SETTLE_SECONDS)

    assert run_engine.started == [("abc", "xyz", 50)]
    assert _element(user, "run-button").text == messages.HOME_STOP


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_the_button_survives_the_five_hertz_refresh(
    user: User, saved_keys: None, run_engine: FakeEngine
) -> None:
    """Spec 4.4: a rebuild on a timer swallows the click. This one must not."""
    await _open_home(user)
    await asyncio.sleep(SETTLE_SECONDS * 4)  # ~20 refreshes before the press

    user.find(marker="run-button").click()
    await asyncio.sleep(SETTLE_SECONDS)

    assert run_engine.started == [("abc", "xyz", 50)]


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_stop_asks_the_engine_politely_and_the_button_waits(
    user: User, saved_keys: None, run_engine: FakeEngine
) -> None:
    await _open_home(user)
    user.find(marker="run-button").click()
    await asyncio.sleep(SETTLE_SECONDS)

    user.find(marker="run-button").click()
    await asyncio.sleep(SETTLE_SECONDS)

    assert run_engine.stops == 1
    button = _element(user, "run-button")
    assert button.text == messages.HOME_STOPPING
    assert button.enabled is False


# --- the live table (spec 4.2) ----------------------------------------------


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_finished_accounts_land_in_the_table_newest_first(
    user: User, saved_keys: None, run_engine: FakeEngine
) -> None:
    await _open_home(user)
    run_engine.show(state=RunState.SOLVING, round_number=1)
    run_engine.finish("ada", Result.JOINED)
    run_engine.finish("bob", Result.FAILED, detail="INTERNAL_ERROR")
    await asyncio.sleep(SETTLE_SECONDS)

    assert [row["account"] for row in _table(user).rows] == ["bob", "ada"]


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_the_switch_filters_the_table_down_to_the_failures(
    user: User, saved_keys: None, run_engine: FakeEngine
) -> None:
    await _open_home(user)
    run_engine.show(state=RunState.SOLVING, round_number=1)
    run_engine.finish("ada", Result.JOINED)
    run_engine.finish("bob", Result.FAILED, detail="INTERNAL_ERROR")
    await asyncio.sleep(SETTLE_SECONDS)

    user.find(marker="failed-only").click()
    await asyncio.sleep(SETTLE_SECONDS)

    assert [row["account"] for row in _table(user).rows] == ["bob"]


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_a_new_round_clears_the_table(
    user: User, saved_keys: None, run_engine: FakeEngine
) -> None:
    await _open_home(user)
    run_engine.show(state=RunState.SOLVING, round_number=1)
    run_engine.finish("ada", Result.JOINED)
    await asyncio.sleep(SETTLE_SECONDS)

    run_engine.show(state=RunState.DISCOVERING, round_number=2)
    await asyncio.sleep(SETTLE_SECONDS)

    assert _table(user).rows == []


# --- how a failure is shown (spec 5.6) --------------------------------------


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_an_engine_bug_is_a_headline_and_never_a_dialog(
    user: User, saved_keys: None, run_engine: FakeEngine
) -> None:
    await _open_home(user)
    run_engine.show(
        state=RunState.IDLE,
        round_number=1,
        headline=Headline.CRASHED,
        detail="KeyError: 'accounts'",
    )
    await asyncio.sleep(SETTLE_SECONDS)

    await user.should_see(messages.headline(Headline.CRASHED))
    await user.should_see(messages.HOME_DETAILS)  # a link, not a popup
    assert _element(user, "closing-dialog").value is False  # nothing popped up


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_a_dibycap_code_stays_in_its_row(
    user: User, saved_keys: None, run_engine: FakeEngine
) -> None:
    await _open_home(user)
    run_engine.show(state=RunState.SOLVING, round_number=1, headline=Headline.SOLVING)
    run_engine.finish("bob", Result.FAILED, detail="UPSTREAM_TIMEOUT")
    await asyncio.sleep(SETTLE_SECONDS)

    await user.should_not_see(messages.HOME_DETAILS)
    assert _table(user).rows[0]["detail"] == "UPSTREAM_TIMEOUT"
    assert "UPSTREAM_TIMEOUT" not in _element(user, "run-headline").text


# --- closing the window (spec 5.3) ------------------------------------------


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_stop_and_close_stops_the_run_before_the_window_goes(
    user: User, saved_keys: None, run_engine: FakeEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[bool] = []
    monkeypatch.setattr(home.native_app, "shutdown", lambda: closed.append(True))
    await _open_home(user)
    user.find(marker="run-button").click()
    await asyncio.sleep(SETTLE_SECONDS)

    _element(user, "closing-dialog").open()
    await user.should_see(messages.CLOSE_QUESTION)
    user.find(messages.CLOSE_YES).click()
    await asyncio.sleep(SETTLE_SECONDS)

    assert run_engine.stops == 1
    assert closed == [True]


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_keep_running_leaves_the_run_alone(
    user: User, saved_keys: None, run_engine: FakeEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[bool] = []
    monkeypatch.setattr(home.native_app, "shutdown", lambda: closed.append(True))
    await _open_home(user)
    user.find(marker="run-button").click()
    await asyncio.sleep(SETTLE_SECONDS)

    dialog = _element(user, "closing-dialog")
    dialog.open()
    await user.should_see(messages.CLOSE_NO)
    user.find(messages.CLOSE_NO).click()
    await asyncio.sleep(SETTLE_SECONDS)

    assert dialog.value is False
    assert run_engine.stops == 0
    assert closed == []


# --- the window's own X (spec 5.3) ------------------------------------------


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_the_x_raises_the_question_while_a_run_is_going(
    user: User, saved_keys: None, run_engine: FakeEngine
) -> None:
    await _open_home(user)
    user.find(marker="run-button").click()
    await asyncio.sleep(SETTLE_SECONDS)

    assert home.close_or_ask() is False  # the window stays

    await user.should_see(messages.CLOSE_QUESTION)


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_the_x_closes_an_idle_app_with_no_question(
    user: User, saved_keys: None, run_engine: FakeEngine
) -> None:
    await _open_home(user)

    assert home.close_or_ask() is True

    assert _element(user, "closing-dialog").value is False


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_stop_and_close_is_not_asked_about_a_second_time(
    user: User, saved_keys: None, run_engine: FakeEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closing the window fires `closing` again. The answer already given holds."""
    monkeypatch.setattr(home.native_app, "shutdown", lambda: None)
    await _open_home(user)
    user.find(marker="run-button").click()
    await asyncio.sleep(SETTLE_SECONDS)

    _element(user, "closing-dialog").open()
    user.find(messages.CLOSE_YES).click()
    await asyncio.sleep(SETTLE_SECONDS)

    assert run_engine.snapshot().state is RunState.STOPPING  # still not Idle
    assert home.close_or_ask() is True


def test_no_screen_yet_means_nothing_to_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setup is on screen, or the window is still opening. The X just closes."""
    monkeypatch.setattr(home, "_showing", None)

    assert home.close_or_ask() is True


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_the_x_never_traps_the_window_behind_settings(
    user: User, saved_keys: None, run_engine: FakeEngine
) -> None:
    """A run, then the gear: the dialog is off the page and cannot ask anything."""
    await _open_home(user)
    user.find(marker="run-button").click()
    await asyncio.sleep(SETTLE_SECONDS)

    user.find(marker="settings-gear").click()
    await user.should_see(marker="speed-toggle")

    assert home.close_or_ask() is True


# --- no devices, no auto-start (spec 4.2) -----------------------------------


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_opening_home_starts_nothing(
    user: User, saved_keys: None, run_engine: FakeEngine
) -> None:
    await _open_home(user)
    await asyncio.sleep(SETTLE_SECONDS * 3)

    assert run_engine.started == []


@pytest.mark.nicegui_main_file("tests/nicegui_main.py")
async def test_the_table_has_no_device_column(
    user: User, saved_keys: None, run_engine: FakeEngine
) -> None:
    await _open_home(user)

    labels = [str(column["label"]).lower() for column in _table(user).columns]

    assert not any("device" in label for label in labels)
