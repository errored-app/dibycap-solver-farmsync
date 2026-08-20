r"""§9.1: one module names `%APPDATA%\FarmsyncSolver`, and everything else asks it."""
from __future__ import annotations

from pathlib import Path

import pytest

from farmsync_solver import config, logging_setup, paths, updater

ROAMING = r"C:\Users\Someone\AppData\Roaming"


def test_the_app_folder_sits_under_appdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", ROAMING)

    folder = paths.app_data_dir()

    assert folder.name == "FarmsyncSolver"
    assert folder.parent.name == "Roaming"


def test_a_missing_appdata_falls_back_to_the_home_folder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Windows without APPDATA is not a Windows the app refuses to start on."""
    monkeypatch.delenv("APPDATA", raising=False)

    assert paths.app_data_dir() == Path.home() / "AppData" / "Roaming" / "FarmsyncSolver"


def test_the_config_the_logs_and_the_updates_all_sit_in_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPDATA", ROAMING)
    folder = paths.app_data_dir()

    assert config.default_path() == folder / "config.json"
    assert logging_setup.default_log_dir() == folder / "logs"
    assert updater.default_update_dir() == folder / "updates"
