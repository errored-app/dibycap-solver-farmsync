"""§4: Setup appears only when the keys are missing or unusable."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from farmsync_solver import config
from farmsync_solver.ui import app, close_guard


def test_no_keys_means_setup() -> None:
    assert app.first_screen(config.Config()) == "setup"


def test_one_key_alone_still_means_setup() -> None:
    assert app.first_screen(config.Config(api_key="abc")) == "setup"


def test_two_keys_mean_home() -> None:
    assert app.first_screen(config.Config(api_key="abc", farm_token="xyz")) == "home"


def test_a_corrupt_file_sends_the_app_back_to_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    config.save(config.Config(api_key="abc", farm_token="xyz"), path)
    path.write_text("}}garbage", encoding="utf-8")
    monkeypatch.setattr(config, "default_path", lambda: path)

    assert app.first_screen(app.load_config()) == "setup"


def test_a_deleted_file_sends_the_app_back_to_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "default_path", lambda: tmp_path / "gone.json")

    assert app.first_screen(app.load_config()) == "setup"


def test_a_key_from_another_windows_login_sends_the_app_back_to_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "api_key": "bm90LW91cnM=",
                "farm_token": "bm90LW91cnM=",
                "speed_percent": 100,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "default_path", lambda: path)

    assert app.first_screen(app.load_config()) == "setup"


# --- the door the window's X knocks on (spec 5.3) ---------------------------


async def test_the_close_question_is_answered_by_the_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.home, "close_or_ask", lambda: False)

    assert await app.answer_close_request() == {"close": False}


async def test_an_app_with_nothing_to_ask_says_close(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.home, "close_or_ask", lambda: True)

    assert await app.answer_close_request() == {"close": True}


def test_the_route_is_mounted_where_the_window_knocks() -> None:
    from nicegui import app as ui_app

    app.register_pages()

    routes = {getattr(route, "path", "") for route in ui_app.routes}
    assert close_guard.CLOSE_ROUTE in routes


def test_the_window_is_armed_before_it_opens(monkeypatch: pytest.MonkeyPatch) -> None:
    """NiceGUI hands `start_args` to `webview.start`, which calls `func` (spec 5.3)."""
    from nicegui import app as ui_app

    monkeypatch.setattr(ui_app.native, "start_args", {})
    app.arm_close_question()

    assert ui_app.native.start_args["func"] is close_guard.bind
