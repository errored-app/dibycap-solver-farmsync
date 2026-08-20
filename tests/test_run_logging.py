"""§8.1: what one run writes to its log file.

A real `Engine` runs against fake clients, with logging pointed at a temporary
folder, and the file it leaves behind is read back. The point of the file is
support, so the tests assert on what a maintainer needs to find in it: one line
per account, the round boundaries, every state change — and no secret anywhere.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterator

import pytest

from farmsync_solver import logging_setup
from farmsync_solver.engine import run as engine_run
from farmsync_solver.engine.snapshot import Headline, RunState
from farmsync_solver.errors import AppError, ErrorCode
from farmsync_solver.ui import messages

from test_engine import (
    API_KEY,
    TOKEN,
    FakeDibycap,
    FakeFarmsync,
    accounts,
    build,
    run_one_round,
    wait_for,
)

LINE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}  [A-Z]+  [a-z]+  (\w+=\S+|\w+=\"[^\"]*\")"
)


@pytest.fixture
def log_file(tmp_path: Path) -> Iterator[Path]:
    """A run log in a temporary folder, flushed and readable after the test body."""
    path = logging_setup.configure(log_dir=tmp_path)
    assert path is not None
    yield path
    logging_setup.reset()


def read(path: Path) -> list[str]:
    for handler in logging.getLogger().handlers:
        handler.flush()
    return path.read_text(encoding="utf-8").splitlines()


def fields(line: str) -> dict[str, str]:
    return dict(pair.split("=", 1) for pair in line.split("  ")[-1].split(" ") if "=" in pair)


def events(lines: list[str], name: str) -> list[dict[str, str]]:
    return [fields(line) for line in lines if f"  {name}  " in line]


# --- the fixed shape -------------------------------------------------------


def test_the_event_helper_writes_one_fixed_shape_line() -> None:
    """Spec 8.1: an event name, then key=value fields."""
    assert logging_setup.event("solve", account="8812", result="joined") == (
        "solve  account=8812 result=joined"
    )


def test_an_empty_field_is_left_out_rather_than_written_blank() -> None:
    assert logging_setup.event("solve", account="8812", code="") == "solve  account=8812"


def test_a_value_with_a_space_is_quoted_so_the_shape_holds() -> None:
    assert logging_setup.event("run", fault="ValueError: kaboom") == (
        'run  fault="ValueError: kaboom"'
    )


# --- what a run writes -----------------------------------------------------


def test_every_account_attempt_writes_one_line(
    monkeypatch: pytest.MonkeyPatch, engines: list, log_file: Path
) -> None:
    engine, _, _ = build(monkeypatch, engines, farm=FakeFarmsync(accounts(5)))

    engine.start(API_KEY, TOKEN, 100)
    run_one_round(engine)

    solves = events(read(log_file), "solve")
    assert len(solves) == 5
    assert {row["result"] for row in solves} == {"joined"}
    assert {row["account"] for row in solves} == {str(100 + number) for number in range(5)}


def test_the_round_boundaries_are_both_written(
    monkeypatch: pytest.MonkeyPatch, engines: list, log_file: Path
) -> None:
    engine, _, _ = build(monkeypatch, engines, farm=FakeFarmsync(accounts(2)))

    engine.start(API_KEY, TOKEN, 100)
    run_one_round(engine)

    rounds = events(read(log_file), "round")
    assert [row["phase"] for row in rounds][:2] == ["start", "end"]
    assert rounds[1]["joined"] == "2"


def test_every_state_change_is_written_in_order(
    monkeypatch: pytest.MonkeyPatch, engines: list, log_file: Path
) -> None:
    engine, _, _ = build(monkeypatch, engines, farm=FakeFarmsync(accounts(2)))

    engine.start(API_KEY, TOKEN, 100)
    run_one_round(engine)

    named = [row["state"] for row in events(read(log_file), "state")]
    assert named[:3] == [
        RunState.DISCOVERING.value,
        RunState.SOLVING.value,
        RunState.RESTING.value,
    ]
    assert named[-1] == RunState.IDLE.value


def test_a_failed_account_writes_its_real_dibycap_code(
    monkeypatch: pytest.MonkeyPatch, engines: list, log_file: Path
) -> None:
    """Spec 8.1: the file is technical — the raw code, not the friendly words."""

    def refuse(cookie: str) -> dict:
        raise AppError(ErrorCode.UNKNOWN, "CLASSIFICATION_ERROR")

    monkeypatch.setattr(engine_run, "BACKOFF_SECONDS", (0.0, 0.0))
    engine, _, _ = build(
        monkeypatch,
        engines,
        client=FakeDibycap(solve=refuse),
        farm=FakeFarmsync(accounts(1)),
    )

    engine.start(API_KEY, TOKEN, 100)
    run_one_round(engine)

    lines = read(log_file)
    failed = [row for row in events(lines, "solve") if row["result"] == "failed"]
    assert failed and failed[0]["detail"] == "CLASSIFICATION_ERROR"
    # Every attempt leaves a line, including the two the screen never shows.
    assert len(events(lines, "attempt")) == 3


def test_no_cookie_and_no_key_ever_reach_the_file(
    monkeypatch: pytest.MonkeyPatch, engines: list, log_file: Path
) -> None:
    """Spec 8.2: redaction is structural — the secrets are never handed over."""
    engine, _, _ = build(monkeypatch, engines, farm=FakeFarmsync(accounts(3)))

    engine.start(API_KEY, TOKEN, 100)
    run_one_round(engine)

    text = "\n".join(read(log_file))
    assert API_KEY not in text
    assert TOKEN not in text
    assert "cookie" not in text


def test_the_run_lines_keep_the_fixed_shape(
    monkeypatch: pytest.MonkeyPatch, engines: list, log_file: Path
) -> None:
    engine, _, _ = build(monkeypatch, engines, farm=FakeFarmsync(accounts(2)))

    engine.start(API_KEY, TOKEN, 100)
    run_one_round(engine)

    written = [line for line in read(log_file) if "  solve  " in line or "  round  " in line]
    assert written
    for line in written:
        assert LINE.match(line), line


def test_a_run_still_finishes_when_logging_is_off(
    monkeypatch: pytest.MonkeyPatch, engines: list, tmp_path: Path
) -> None:
    """Spec 8.3: a log that cannot be written never stops a run."""
    blocked = tmp_path / "blocked"
    blocked.write_text("I am a file, not a folder", encoding="utf-8")
    assert logging_setup.configure(log_dir=blocked) is None

    engine, client, _ = build(monkeypatch, engines, farm=FakeFarmsync(accounts(2)))
    engine.start(API_KEY, TOKEN, 100)
    run_one_round(engine)

    assert wait_for(lambda: len(client.solved) == 2)


def test_the_sentence_the_user_saw_is_logged_by_its_name(
    monkeypatch: pytest.MonkeyPatch, engines: list, log_file: Path
) -> None:
    """Spec 8.1: technical tone — the `Headline` name, not the friendly words."""
    engine, _, _ = build(monkeypatch, engines, farm=FakeFarmsync([]))

    engine.start(API_KEY, TOKEN, 100)
    run_one_round(engine)

    shown = [row["message"] for row in events(read(log_file), "shown")]
    assert "NO_ACCOUNTS" in shown
    assert messages.headline(Headline.NO_ACCOUNTS) not in "\n".join(read(log_file))


def test_a_run_that_ended_on_a_fault_logs_the_code_it_ended_on(
    monkeypatch: pytest.MonkeyPatch, engines: list, log_file: Path
) -> None:
    """The headline of a fault is its code, so the log line names the code."""
    refused = AppError(ErrorCode.BAD_API_KEY, "invalid_api_key")
    engine, _, _ = build(monkeypatch, engines, client=FakeDibycap(refused))

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE)

    shown = [row["message"] for row in events(read(log_file), "shown")]
    assert "BAD_API_KEY" in shown
