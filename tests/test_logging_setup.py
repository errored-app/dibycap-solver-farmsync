"""Logging must start before anything else, and must never take the app down."""
from __future__ import annotations

import logging
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from farmsync_solver import logging_setup

LINE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}  INFO  hello world$"
)


def test_configure_writes_one_file_per_run(tmp_path: Path) -> None:
    first = logging_setup.configure(log_dir=tmp_path)
    logging_setup.reset()
    second = logging_setup.configure(log_dir=tmp_path)

    assert first is not None and second is not None
    assert first != second
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [first.name, second.name]
    )


def test_log_lines_have_the_fixed_shape(tmp_path: Path) -> None:
    log_file = logging_setup.configure(log_dir=tmp_path)
    logging.getLogger("test").info("hello world")
    logging.shutdown()

    assert log_file is not None
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert any(LINE.match(line) for line in lines), lines


def test_configure_twice_without_reset_keeps_the_first_file(tmp_path: Path) -> None:
    first = logging_setup.configure(log_dir=tmp_path)
    assert logging_setup.configure(log_dir=tmp_path) == first


def test_pruning_drops_files_older_than_seven_days(tmp_path: Path) -> None:
    old = tmp_path / "2020-01-01_00-00-00.log"
    old.write_text("old", encoding="utf-8")
    stale = (datetime.now() - timedelta(days=8)).timestamp()
    os.utime(old, (stale, stale))

    logging_setup.configure(log_dir=tmp_path)

    assert not old.exists()


def test_pruning_keeps_at_most_twenty_files(tmp_path: Path) -> None:
    for index in range(30):
        (tmp_path / f"2026-08-18_00-00-{index:02d}.log").write_text("x", encoding="utf-8")

    logging_setup.configure(log_dir=tmp_path)

    assert len(list(tmp_path.glob("*.log"))) == 20


def test_a_log_failure_never_raises(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("I am a file, not a folder", encoding="utf-8")

    assert logging_setup.configure(log_dir=blocked) is None
    logging.getLogger("test").info("this must not raise")


def test_the_excepthook_writes_uncaught_exceptions_to_the_file(tmp_path: Path) -> None:
    log_file = logging_setup.configure(log_dir=tmp_path)

    sys.excepthook(ValueError, ValueError("kaboom"), None)
    logging.shutdown()

    assert log_file is not None
    text = log_file.read_text(encoding="utf-8")
    assert "ValueError" in text
    assert "kaboom" in text


def test_reset_restores_the_original_excepthook(tmp_path: Path) -> None:
    original = sys.excepthook
    logging_setup.configure(log_dir=tmp_path)
    assert sys.excepthook is not original
    logging_setup.reset()
    assert sys.excepthook is original
