r"""§10.2, ADR 0008 and ADR 0009: the row a run leaves in `history.json`.

A real `Engine` runs against fake clients with `%APPDATA%` pointed at a
temporary folder, and the file it leaves behind is read back. The point of the
file is a record of spending, so the tests assert on what a row has to hold for
the History screen to be true: the counts, the price, and who ended the run.

The file is read **once**, at a moment the snapshot has already named: a run
parked in Solving, a rest that has begun, a run gone back to Idle. Polling the
file instead would be its own bug, because on Windows a reader holding the file
open stops the run's atomic replace going through, and the test that watched
the file would be the thing that emptied it.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

import pytest

from farmsync_solver.engine import Engine
from farmsync_solver.engine.snapshot import Headline, RunState
from farmsync_solver.errors import AppError, ErrorCode, Severity

from conftest import wait_for

from test_engine import (
    API_KEY,
    BALANCE,
    TOKEN,
    FakeDibycap,
    FakeFarmsync,
    accounts,
    build,
    waiting,
)


class Held:
    """A solve that does not answer until the test lets it go.

    It is how a run is held still: everything written before the round started
    is on disk, and nothing is being written while the file is read.
    """

    def __init__(self) -> None:
        self.let_go = threading.Event()

    def __call__(self, cookie: str) -> dict[str, Any]:
        self.let_go.wait(timeout=10.0)
        return {"total_ms": 900, "solve_ms": 0}


class Breaks:
    """A solve that is a bug until the test mends it."""

    def __init__(self) -> None:
        self.mended = False

    def __call__(self, cookie: str) -> dict[str, Any]:
        if not self.mended:
            raise RuntimeError("boom")
        return {"total_ms": 900, "solve_ms": 0}


def rows(app_data: Path) -> list[dict[str, Any]]:
    """Every row on disk, or none at all when nothing has been written yet."""
    try:
        raw = (app_data / "history.json").read_text(encoding="utf-8")
    except OSError:
        return []
    return json.loads(raw)["runs"]


def one_row(app_data: Path) -> dict[str, Any]:
    (row,) = rows(app_data)
    return row


def ends(engine: Engine) -> None:
    """Wait for the run to be over.

    Idle is the whole signal: the row is closed before the snapshot is, so a
    run that reads Idle is a run whose record is finished (ADR 0008).
    """
    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE), engine.snapshot()


def rests(engine: Engine) -> None:
    """Wait for the round to be over, which is where its row is written."""
    assert wait_for(lambda: engine.snapshot().state is RunState.RESTING), engine.snapshot()


def stop_and_end(engine: Engine) -> None:
    engine.stop()
    ends(engine)


def run_and_end(monkeypatch: pytest.MonkeyPatch, engines: list[Engine], **built: Any) -> Engine:
    """Start a run whose first round ends it, and wait for it to be over."""
    engine, _, _ = build(monkeypatch, engines, **built)
    engine.start(API_KEY, TOKEN, 100)
    ends(engine)
    return engine


# --- a row while the run is still going (ADR 0008) -------------------------


def test_a_row_is_on_disk_from_the_moment_the_run_starts(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    """The row is there before the first round has anything to say about it."""
    held = Held()
    engine, _, _ = build(
        monkeypatch, engines, client=FakeDibycap(solve=held), farm=FakeFarmsync(accounts(3))
    )

    engine.start(API_KEY, TOKEN, 75)
    assert wait_for(lambda: engine.snapshot().state is RunState.SOLVING), engine.snapshot()
    row = one_row(app_data)
    held.let_go.set()

    assert "ended_at" not in row and "ending" not in row
    assert row["speed_percent"] == 75
    assert (row["rounds"], row["joined"], row["solved"], row["failed"]) == (0, 0, 0, 0)


def test_killing_the_process_mid_run_leaves_the_last_rounds_counts(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    """The row a task-kill leaves behind: the counts, and no end (spec 10.2)."""
    engine, _, _ = build(monkeypatch, engines, farm=FakeFarmsync(accounts(4)), rest_seconds=30.0)

    engine.start(API_KEY, TOKEN, 100)
    rests(engine)

    row = one_row(app_data)
    assert "ended_at" not in row and "ending" not in row
    assert (row["rounds"], row["joined"], row["solved"], row["failed"]) == (1, 4, 0, 0)


def test_the_row_counts_the_run_not_the_round(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    """The counters run to the end of the run, and the row says what they say."""
    engine, _, _ = build(monkeypatch, engines, farm=FakeFarmsync(accounts(2), accounts(3)))

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().round_number >= 3), engine.snapshot()
    stop_and_end(engine)

    row, picture = one_row(app_data), engine.snapshot()
    assert picture.joined > 3  # more than the biggest round found, so they add up
    assert (row["rounds"], row["joined"]) == (picture.round_number, picture.joined)


# --- how the run ended (ADR 0009) ------------------------------------------


def test_stop_writes_stopped_and_no_fault(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    engine, _, _ = build(monkeypatch, engines, farm=FakeFarmsync(accounts(3)))

    engine.start(API_KEY, TOKEN, 100)
    rests(engine)
    stop_and_end(engine)

    row = one_row(app_data)
    assert row["ending"] == "stopped"
    assert "fault" not in row
    assert row["ended_at"] >= row["started_at"]


def test_a_terminal_error_writes_faulted_and_its_code(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    def refuse(cookie: str) -> dict[str, Any]:
        raise AppError(ErrorCode.NO_CREDIT, "insufficient_balance", severity=Severity.ENDS_RUN)

    run_and_end(
        monkeypatch, engines, client=FakeDibycap(solve=refuse), farm=FakeFarmsync(accounts(4))
    )

    row = one_row(app_data)
    assert (row["ending"], row["fault"]) == ("faulted", "NO_CREDIT")


def test_a_run_refused_before_its_first_round_still_leaves_a_row(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    """Spec 5.4 refuses the run at `/balance`, and the refusal is still a run."""
    run_and_end(monkeypatch, engines, client=FakeDibycap(dict(BALANCE, estimated_solves=0)))

    row = one_row(app_data)
    assert (row["ending"], row["fault"]) == ("faulted", "NO_CREDIT")
    assert row["rounds"] == 0


def test_an_engine_bug_writes_crashed(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    """Anything the round loop did not expect is a bug, not a fault."""
    run_and_end(monkeypatch, engines, farm=FakeFarmsync(RuntimeError("boom")))

    row = one_row(app_data)
    assert (row["ending"], row["fault"]) == ("crashed", "UNKNOWN")


def test_a_bug_in_a_worker_writes_crashed_too(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    """A worker is engine code as much as the loop is, and it wraps its own bugs."""

    def burst(cookie: str) -> dict[str, Any]:
        raise RuntimeError("boom")

    run_and_end(
        monkeypatch, engines, client=FakeDibycap(solve=burst), farm=FakeFarmsync(accounts(4))
    )

    assert one_row(app_data)["ending"] == "crashed"


def test_a_bug_beside_a_key_fault_is_still_the_key_faults_run(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    """The ending names what ended the run, not the worst thing that happened.

    One round can hold both: an account refused for good, and a worker that hit
    a bug on its way to the same answer. The run ended on the refusal.
    """
    refused = threading.Event()

    def mixed(cookie: str) -> dict[str, Any]:
        if cookie == "cookie-0":
            refused.set()
            raise AppError(ErrorCode.NO_CREDIT, "insufficient_balance", severity=Severity.ENDS_RUN)
        refused.wait(timeout=10.0)  # so the refusal is the fault the loop sees first
        raise RuntimeError("boom")

    run_and_end(
        monkeypatch, engines, client=FakeDibycap(solve=mixed), farm=FakeFarmsync(accounts(2))
    )

    row = one_row(app_data)
    assert (row["ending"], row["fault"]) == ("faulted", "NO_CREDIT")


def test_a_bug_in_one_run_does_not_follow_the_next(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    """A crash is a fact about the run it happened in, and a start is a fresh one."""
    solve = Breaks()
    engine, _, _ = build(
        monkeypatch, engines, client=FakeDibycap(solve=solve), farm=FakeFarmsync(accounts(2))
    )

    engine.start(API_KEY, TOKEN, 100)
    ends(engine)
    solve.mended = True
    engine.start(API_KEY, TOKEN, 100)
    rests(engine)
    stop_and_end(engine)

    first, second = rows(app_data)
    assert (first["ending"], second["ending"]) == ("crashed", "stopped")


def test_a_named_fault_is_faulted_however_it_is_coded(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    """ADR 0009: the ending is named where the run ends, never read off a code.

    A client that names `UNKNOWN` as terminal is a fault the run hit, not a bug
    in the engine, and the two must not land in the file as the same word.
    """

    def refuse(cookie: str) -> dict[str, Any]:
        raise AppError(ErrorCode.UNKNOWN, "solver said something new", severity=Severity.ENDS_RUN)

    run_and_end(
        monkeypatch, engines, client=FakeDibycap(solve=refuse), farm=FakeFarmsync(accounts(4))
    )

    row = one_row(app_data)
    assert (row["ending"], row["fault"]) == ("faulted", "UNKNOWN")


def test_a_run_stopped_while_waiting_keeps_the_fault_it_waited_on(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    """ADR 0009: stopped + `SERVICE_PAUSED` must not read as an hour of work."""
    engine, _, _ = waiting(monkeypatch, engines)

    stop_and_end(engine)

    row = one_row(app_data)
    assert (row["ending"], row["fault"]) == ("stopped", "SERVICE_PAUSED")


# --- the price the run was watching (§10.2) --------------------------------


def test_the_row_keeps_the_last_price_the_run_read(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    engine, _, _ = build(
        monkeypatch,
        engines,
        client=FakeDibycap(dict(BALANCE), dict(BALANCE, price_per_1k=2.5)),
        farm=FakeFarmsync(accounts(4)),
        credit_seconds=0.0,
    )

    engine.start(API_KEY, TOKEN, 100)
    rests(engine)
    stop_and_end(engine)

    assert one_row(app_data)["price_per_1k"] == 2.5


def test_a_later_balance_with_no_price_leaves_the_one_read_standing(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    """A payload that carries no price is not a run that read none (spec 10.2)."""
    priceless = {"success": True, "balance": 8.49, "estimated_solves": 5662, "max_concurrent": 4}
    engine, _, _ = build(
        monkeypatch,
        engines,
        client=FakeDibycap(dict(BALANCE), priceless),
        farm=FakeFarmsync(accounts(4)),
        credit_seconds=0.0,
    )

    engine.start(API_KEY, TOKEN, 100)
    rests(engine)
    stop_and_end(engine)

    assert one_row(app_data)["price_per_1k"] == BALANCE["price_per_1k"]


def test_a_run_that_never_read_a_price_leaves_the_field_out(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    """A dash on screen and a row the totals skip, rather than a price of zero."""
    priceless = {"success": True, "balance": 8.49, "estimated_solves": 5662, "max_concurrent": 4}
    engine, _, _ = build(
        monkeypatch, engines, client=FakeDibycap(priceless), farm=FakeFarmsync(accounts(3))
    )

    engine.start(API_KEY, TOKEN, 100)
    rests(engine)
    stop_and_end(engine)

    assert "price_per_1k" not in one_row(app_data)


# --- the file never gets in the run's way (§10.2) --------------------------


def test_a_write_that_cannot_go_through_never_reaches_the_run(
    monkeypatch: pytest.MonkeyPatch,
    engines: list[Engine],
    app_data: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A folder that is a file: every write fails, and the run does not care."""
    app_data.parent.mkdir(parents=True, exist_ok=True)
    app_data.write_text("this is not a folder", encoding="utf-8")

    engine, _, _ = build(monkeypatch, engines, farm=FakeFarmsync(accounts(4)))
    with caplog.at_level(logging.WARNING):
        engine.start(API_KEY, TOKEN, 100)
        rests(engine)
        stop_and_end(engine)

    picture = engine.snapshot()
    assert picture.headline is Headline.STOPPED
    assert (picture.joined, picture.detail) == (4, "")
    assert [record for record in caplog.records if "history" in record.getMessage()]


def test_a_second_run_lands_beside_the_first(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    engine, _, _ = build(monkeypatch, engines, farm=FakeFarmsync(accounts(2)))

    for speed in (100, 50):
        engine.start(API_KEY, TOKEN, speed)
        rests(engine)
        stop_and_end(engine)

    first, second = rows(app_data)
    assert first["started_at"] < second["started_at"]
    assert (first["speed_percent"], second["speed_percent"]) == (100, 50)
    assert (first["ending"], second["ending"]) == ("stopped", "stopped")


def test_nothing_a_run_writes_can_name_an_account(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], app_data: Path
) -> None:
    """§10.2: the file is safe to open in front of anyone."""
    engine, _, _ = build(monkeypatch, engines, farm=FakeFarmsync(accounts(3)))

    engine.start(API_KEY, TOKEN, 100)
    rests(engine)
    stop_and_end(engine)

    body = (app_data / "history.json").read_text(encoding="utf-8")
    for secret in ("user0", "cookie-0", API_KEY, TOKEN):
        assert secret not in body
