"""The entry point: a native window, or a selftest that opens nothing."""
from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

import main


def test_selftest_exits_zero_and_opens_no_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ui_app: ModuleType
) -> None:
    def fail() -> None:
        raise AssertionError("a window was opened during --selftest")

    monkeypatch.setattr(ui_app, "start_window", fail)

    assert main.run(["--selftest"], log_dir=tmp_path) == 0


def test_selftest_still_writes_a_log_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ui_app: ModuleType
) -> None:
    monkeypatch.setattr(ui_app, "start_window", lambda: None)
    main.run(["--selftest"], log_dir=tmp_path)

    assert list(tmp_path.glob("*.log"))


def test_a_normal_launch_opens_the_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ui_app: ModuleType
) -> None:
    opened: list[bool] = []
    monkeypatch.setattr(ui_app, "start_window", lambda: opened.append(True))

    assert main.run([], log_dir=tmp_path) == 0
    assert opened == [True]


def test_a_crash_at_startup_is_logged_and_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ui_app: ModuleType
) -> None:
    def boom() -> None:
        raise RuntimeError("window is broken")

    monkeypatch.setattr(ui_app, "start_window", boom)

    assert main.run([], log_dir=tmp_path) == 1
    text = "\n".join(p.read_text(encoding="utf-8") for p in tmp_path.glob("*.log"))
    assert "window is broken" in text
    assert "UNKNOWN" in text


def test_logging_is_configured_before_the_ui_is_imported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ui_app: ModuleType
) -> None:
    """An import-time crash in the UI layer must still reach the log file."""
    import builtins

    real_import = builtins.__import__

    def explode(name: str, *args: object, **kwargs: object) -> object:
        if name == "farmsync_solver.ui":
            raise ImportError("nicegui assets are missing")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", explode)

    assert main.run([], log_dir=tmp_path) == 1
    monkeypatch.undo()
    text = "\n".join(p.read_text(encoding="utf-8") for p in tmp_path.glob("*.log"))
    assert "nicegui assets are missing" in text
