"""§8.4: Copy diagnostics and Open log folder.

Diagnostics is a paste, not a file: a short header the maintainer reads first,
then the tail of the log the run was writing. Every failure here is silent — a
missing folder or an unreadable file still produces something to paste.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from farmsync_solver import diagnostics
from farmsync_solver._version import APP_NAME, VERSION


def write_log(folder: Path, lines: int, name: str = "2026-08-18_14-00-00.log") -> Path:
    path = folder / name
    path.write_text("\n".join(f"line {number}" for number in range(lines)), encoding="utf-8")
    return path


def bundle(log_file: Path | None, **changes: Any) -> str:
    values: dict[str, Any] = {
        "run_state": "idle",
        "key_check": "ok",
        "credit": "5,662 captchas left ($8.49)",
        "speed_percent": 100,
        "log_file": log_file,
    }
    values.update(changes)
    return diagnostics.bundle(**values)


# --- the tail --------------------------------------------------------------


def test_the_tail_is_the_last_two_hundred_lines(tmp_path: Path) -> None:
    path = write_log(tmp_path, 500)

    lines = diagnostics.tail(path)

    assert len(lines) == diagnostics.TAIL_LINES
    assert lines[0] == "line 300"
    assert lines[-1] == "line 499"


def test_a_short_log_gives_every_line_it_has(tmp_path: Path) -> None:
    assert len(diagnostics.tail(write_log(tmp_path, 12))) == 12


def test_an_unreadable_log_gives_no_lines_and_does_not_raise(tmp_path: Path) -> None:
    assert diagnostics.tail(tmp_path / "not-here.log") == []


# --- the bundle ------------------------------------------------------------


def test_the_header_carries_the_six_facts_a_report_needs(tmp_path: Path) -> None:
    text = bundle(write_log(tmp_path, 3), run_state="solving", key_check="ok", speed_percent=50)

    assert f"{APP_NAME} {VERSION}" in text
    assert "Windows" in text
    assert "solving" in text
    assert "ok" in text
    assert "5,662 captchas left ($8.49)" in text
    assert "50%" in text


def test_the_bundle_is_the_header_then_the_log_tail(tmp_path: Path) -> None:
    text = bundle(write_log(tmp_path, 250))

    assert text.index(VERSION) < text.index("line 50")
    assert text.rstrip().endswith("line 249")
    assert "line 49" not in text


def test_a_missing_log_still_gives_a_header_to_paste() -> None:
    text = bundle(None)

    assert VERSION in text
    assert diagnostics.NO_LOG in text


# --- opening the folder ----------------------------------------------------


def test_open_log_folder_shows_the_newest_file_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_log(tmp_path, 2, name="2026-08-17_10-00-00.log")
    newest = write_log(tmp_path, 2, name="2026-08-18_14-00-00.log")
    asked: list[list[str]] = []
    monkeypatch.setattr(diagnostics.subprocess, "run", lambda command, **kw: asked.append(command))

    assert diagnostics.open_log_folder(tmp_path) is True
    assert str(newest) in " ".join(asked[0])


def test_open_log_folder_still_opens_an_empty_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[list[str]] = []
    monkeypatch.setattr(diagnostics.subprocess, "run", lambda command, **kw: asked.append(command))

    assert diagnostics.open_log_folder(tmp_path) is True
    assert str(tmp_path) in " ".join(asked[0])


def test_open_log_folder_never_makes_the_folder_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A folder that is not there means logging is off — do not hide that."""
    missing = tmp_path / "logs"
    asked: list[list[str]] = []
    monkeypatch.setattr(diagnostics.subprocess, "run", lambda command, **kw: asked.append(command))

    assert diagnostics.open_log_folder(missing) is False
    assert not missing.exists()
    assert asked == []


def test_open_log_folder_answers_false_rather_than_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(command: list[str], **kwargs: Any) -> None:
        raise OSError("no explorer here")

    monkeypatch.setattr(diagnostics.subprocess, "run", explode)

    assert diagnostics.open_log_folder(tmp_path) is False
