"""§4: Setup appears only when the keys are missing or unusable."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from farmsync_solver import config
from farmsync_solver.ui import app, closing


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


def test_registering_the_page_mounts_the_close_route() -> None:
    """What the app owes the close question. The rest is `ui.closing`."""
    from nicegui import app as ui_app

    app.register_pages()

    routes = {getattr(route, "path", "") for route in ui_app.routes}
    assert closing.CLOSE_ROUTE in routes
