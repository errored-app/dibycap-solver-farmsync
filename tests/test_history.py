r"""§10.2: the one reader and writer of %APPDATA%\FarmsyncSolver\history.json."""
from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from farmsync_solver import history
from farmsync_solver.errors import ErrorCode

ROW_FIELDS = {
    "started_at",
    "ended_at",
    "ending",
    "fault",
    "rounds",
    "joined",
    "solved",
    "failed",
    "speed_percent",
    "price_per_1k",
}


@pytest.fixture
def history_file(tmp_path: Path) -> Path:
    return tmp_path / "history.json"


def written(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return written(path)["runs"]


def a_row(started_at: float) -> dict[str, Any]:
    return {
        "started_at": started_at,
        "ended_at": started_at + 100.0,
        "ending": "stopped",
        "rounds": 1,
        "joined": 1,
        "solved": 1,
        "failed": 0,
        "speed_percent": 100,
    }


def full_file(path: Path, count: int) -> None:
    runs = [a_row(1000.0 + index) for index in range(count)]
    path.write_text(json.dumps({"version": 1, "runs": runs}), encoding="utf-8")


def test_the_file_sits_beside_the_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", r"C:\Users\Someone\AppData\Roaming")
    path = history.default_path()

    assert path.name == "history.json"
    assert path.parent.name == "FarmsyncSolver"


def test_a_missing_file_reads_as_an_empty_history(history_file: Path) -> None:
    loaded = history.load(history_file)

    assert loaded.runs == ()
    assert loaded.from_newer_build is False


def test_a_started_run_is_on_disk_before_it_ends(history_file: Path) -> None:
    recorder = history.Recorder(history_file)
    recorder.start(started_at=1755690191.4, speed_percent=75)

    (row,) = rows(history_file)
    assert row["started_at"] == 1755690191.4
    assert row["speed_percent"] == 75
    assert "ended_at" not in row
    assert "ending" not in row


def test_the_row_is_updated_in_place(history_file: Path) -> None:
    recorder = history.Recorder(history_file)
    recorder.start(started_at=1755690191.4, speed_percent=100)
    recorder.round_ended(rounds=1, joined=70, solved=26, failed=34)
    recorder.round_ended(rounds=2, joined=140, solved=52, failed=68)
    recorder.end(ended_at=1755693791.2, ending=history.Ending.STOPPED)

    (row,) = rows(history_file)
    assert row["rounds"] == 2
    assert row["solved"] == 52
    assert row["ended_at"] == 1755693791.2
    assert row["ending"] == "stopped"


def test_a_round_with_no_price_keeps_the_last_one_read(history_file: Path) -> None:
    recorder = history.Recorder(history_file)
    recorder.start(started_at=1.0, speed_percent=100)
    recorder.round_ended(rounds=1, joined=70, solved=26, failed=34, price_per_1k=1.2)
    recorder.round_ended(rounds=2, joined=140, solved=52, failed=68)

    assert rows(history_file)[0]["price_per_1k"] == 1.2


def test_a_run_that_faulted_mid_round_still_keeps_its_price(history_file: Path) -> None:
    recorder = history.Recorder(history_file)
    recorder.start(started_at=1.0, speed_percent=100)
    recorder.end(
        ended_at=2.0,
        ending=history.Ending.FAULTED,
        fault=ErrorCode.NO_CREDIT,
        price_per_1k=1.2,
    )

    assert rows(history_file)[0]["price_per_1k"] == 1.2


def test_a_run_that_never_read_a_price_has_no_price_field(history_file: Path) -> None:
    recorder = history.Recorder(history_file)
    recorder.start(started_at=1.0, speed_percent=100)
    recorder.round_ended(rounds=1, joined=70, solved=26, failed=34)

    assert "price_per_1k" not in rows(history_file)[0]


def test_a_row_holds_exactly_the_fields_of_the_spec(history_file: Path) -> None:
    recorder = history.Recorder(history_file)
    recorder.start(started_at=1755690191.4, speed_percent=100)
    recorder.round_ended(rounds=12, joined=840, solved=312, failed=402, price_per_1k=1.2)
    recorder.end(
        ended_at=1755693791.2,
        ending=history.Ending.FAULTED,
        fault=ErrorCode.SERVICE_PAUSED,
    )

    assert written(history_file)["version"] == history.HISTORY_VERSION
    assert set(rows(history_file)[0]) == ROW_FIELDS


def test_a_saved_run_comes_back_whole(history_file: Path) -> None:
    recorder = history.Recorder(history_file)
    recorder.start(started_at=1755690191.4, speed_percent=75)
    recorder.round_ended(rounds=12, joined=840, solved=312, failed=402, price_per_1k=1.2)
    recorder.end(
        ended_at=1755693791.2,
        ending=history.Ending.STOPPED,
        fault=ErrorCode.SERVICE_PAUSED,
    )

    (run,) = history.load(history_file).runs
    assert run == history.Record(
        started_at=1755690191.4,
        speed_percent=75,
        ended_at=1755693791.2,
        ending=history.Ending.STOPPED,
        fault=ErrorCode.SERVICE_PAUSED,
        rounds=12,
        joined=840,
        solved=312,
        failed=402,
        price_per_1k=1.2,
    )


def test_a_second_run_lands_beside_the_first(history_file: Path) -> None:
    first = history.Recorder(history_file)
    first.start(started_at=1.0, speed_percent=100)
    first.end(ended_at=2.0, ending=history.Ending.STOPPED)

    second = history.Recorder(history_file)
    second.start(started_at=3.0, speed_percent=100)

    assert [run.started_at for run in history.load(history_file).runs] == [1.0, 3.0]


def test_saving_creates_the_folder(tmp_path: Path) -> None:
    path = tmp_path / "FarmsyncSolver" / "history.json"
    history.Recorder(path).start(started_at=1.0, speed_percent=100)

    assert path.is_file()


def test_saving_leaves_no_temp_file_behind(history_file: Path) -> None:
    history.Recorder(history_file).start(started_at=1.0, speed_percent=100)

    assert [p.name for p in history_file.parent.iterdir()] == ["history.json"]


# --- the ending -------------------------------------------------------------


def test_a_row_with_no_end_time_reads_as_interrupted(history_file: Path) -> None:
    history.Recorder(history_file).start(started_at=1.0, speed_percent=100)

    (run,) = history.load(history_file).runs
    assert run.ending is history.Ending.INTERRUPTED
    assert run.ended_at is None


def test_interrupted_is_never_written(history_file: Path) -> None:
    recorder = history.Recorder(history_file)
    recorder.start(started_at=1.0, speed_percent=100)

    with pytest.raises(ValueError):
        recorder.end(ended_at=2.0, ending=history.Ending.INTERRUPTED)

    assert "interrupted" not in history_file.read_text(encoding="utf-8")


def test_a_crashed_run_is_written_as_crashed(history_file: Path) -> None:
    recorder = history.Recorder(history_file)
    recorder.start(started_at=1.0, speed_percent=100)
    recorder.end(ended_at=2.0, ending=history.Ending.CRASHED, fault=ErrorCode.UNKNOWN)

    (run,) = history.load(history_file).runs
    assert run.ending is history.Ending.CRASHED
    assert run.fault is ErrorCode.UNKNOWN


def test_a_fault_this_build_does_not_know_leaves_the_row_standing(
    history_file: Path,
) -> None:
    row = a_row(1.0) | {"ending": "faulted", "fault": "SOMETHING_LATER"}
    history_file.write_text(
        json.dumps({"version": 1, "runs": [row]}), encoding="utf-8"
    )

    (run,) = history.load(history_file).runs
    assert run.ending is history.Ending.FAULTED
    assert run.fault is None


# --- how it fails -----------------------------------------------------------


CORRUPT = [
    "{not json",
    "[]",
    '[{"started_at": 1.0}]',
    '{"runs": []}',
    '{"version": "1", "runs": []}',
    '{"version": 1, "runs": {}}',
    '"a string"',
]


@pytest.mark.parametrize("body", CORRUPT)
def test_a_corrupt_file_reads_as_empty_and_is_moved_aside(
    history_file: Path, body: str
) -> None:
    history_file.write_text(body, encoding="utf-8")

    loaded = history.load(history_file)

    assert loaded.runs == ()
    assert loaded.from_newer_build is False
    assert not history_file.exists()
    assert history_file.with_suffix(".json.corrupt").read_text(encoding="utf-8") == body


def test_the_corrupt_slot_holds_the_newest_bad_file_only(history_file: Path) -> None:
    history_file.write_text("{first", encoding="utf-8")
    history.load(history_file)
    history_file.write_text("{second", encoding="utf-8")
    history.load(history_file)

    corrupt = history_file.with_suffix(".json.corrupt")
    assert corrupt.read_text(encoding="utf-8") == "{second"
    assert [p.name for p in history_file.parent.iterdir()] == ["history.json.corrupt"]


def test_a_corrupt_file_that_will_not_move_still_reads_as_empty(
    history_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history_file.write_text("{not json", encoding="utf-8")

    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("the file is in use")

    monkeypatch.setattr(Path, "replace", refuse)

    assert history.load(history_file).runs == ()


BROKEN_ROWS = [
    "not an object",
    {"ended_at": 2.0, "rounds": 1, "joined": 1, "solved": 1, "failed": 0},
    a_row(1.0) | {"started_at": "yesterday"},
    a_row(1.0) | {"rounds": 1.5},
    a_row(1.0) | {"speed_percent": True},
    a_row(1.0) | {"ending": "abandoned"},
    a_row(1.0) | {"ended_at": "later"},
    a_row(1.0) | {"price_per_1k": "cheap"},
    {key: value for key, value in a_row(1.0).items() if key != "ending"},
]


@pytest.mark.parametrize("broken", BROKEN_ROWS)
def test_one_unreadable_row_is_dropped_and_its_neighbours_survive(
    history_file: Path, broken: object, caplog: pytest.LogCaptureFixture
) -> None:
    history_file.write_text(
        json.dumps({"version": 1, "runs": [a_row(1.0), broken, a_row(3.0)]}),
        encoding="utf-8",
    )

    with caplog.at_level(logging.DEBUG, logger="farmsync_solver.history"):
        loaded = history.load(history_file)

    assert [run.started_at for run in loaded.runs] == [1.0, 3.0]
    assert caplog.records


def test_a_write_that_fails_raises_nothing_and_later_writes_still_try(
    history_file: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    recorder = history.Recorder(history_file)

    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("the folder is locked")

    monkeypatch.setattr(Path, "replace", refuse)
    with caplog.at_level(logging.DEBUG, logger="farmsync_solver.history"):
        recorder.start(started_at=1.0, speed_percent=100)
        recorder.round_ended(rounds=1, joined=70, solved=26, failed=34)
        recorder.round_ended(rounds=2, joined=140, solved=52, failed=68)

    levels = [record.levelno for record in caplog.records]
    assert levels == [logging.WARNING, logging.DEBUG, logging.DEBUG]
    assert "the folder is locked" in caplog.records[0].getMessage()
    assert not history_file.exists()

    monkeypatch.undo()
    recorder.end(ended_at=2.0, ending=history.Ending.STOPPED)

    (run,) = history.load(history_file).runs
    assert run.solved == 52
    assert run.ended_at == 2.0


def test_a_failed_write_leaves_no_temp_file_behind(
    history_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("the folder is locked")

    monkeypatch.setattr(Path, "replace", refuse)
    history.Recorder(history_file).start(started_at=1.0, speed_percent=100)

    assert list(history_file.parent.iterdir()) == []


# --- a file from a newer build ----------------------------------------------


NEWER = json.dumps(
    {
        "version": history.HISTORY_VERSION + 1,
        "runs": [{"started_at": 1.0, "spent": 3.0}],
    }
)


def test_a_newer_file_reads_as_empty_and_says_so(history_file: Path) -> None:
    history_file.write_text(NEWER, encoding="utf-8")

    loaded = history.load(history_file)

    assert loaded.runs == ()
    assert loaded.from_newer_build is True
    assert history_file.read_text(encoding="utf-8") == NEWER


def test_a_newer_file_is_never_written(history_file: Path) -> None:
    history_file.write_text(NEWER, encoding="utf-8")

    recorder = history.Recorder(history_file)
    recorder.start(started_at=2.0, speed_percent=100)
    recorder.round_ended(rounds=1, joined=70, solved=26, failed=34)
    recorder.end(ended_at=3.0, ending=history.Ending.STOPPED)
    history.prune(history_file)
    history.clear(history_file)

    assert history_file.read_text(encoding="utf-8") == NEWER


def test_a_newer_file_is_not_moved_aside(history_file: Path) -> None:
    history_file.write_text(NEWER, encoding="utf-8")
    history.load(history_file)

    assert not history_file.with_suffix(".json.corrupt").exists()


# --- pruning and clearing ---------------------------------------------------


def test_the_file_is_pruned_to_the_newest_500_on_startup(history_file: Path) -> None:
    full_file(history_file, history.MAX_RUNS + 20)

    history.prune(history_file)

    kept = rows(history_file)
    assert len(kept) == history.MAX_RUNS
    assert kept[0]["started_at"] == 1020.0
    assert kept[-1]["started_at"] == 1519.0


def test_pruning_a_short_file_leaves_it_alone(history_file: Path) -> None:
    full_file(history_file, 3)
    before = history_file.read_text(encoding="utf-8")

    history.prune(history_file)

    assert history_file.read_text(encoding="utf-8") == before


def test_a_new_run_pushes_out_the_oldest(history_file: Path) -> None:
    full_file(history_file, history.MAX_RUNS)

    history.Recorder(history_file).start(started_at=9999.0, speed_percent=100)

    kept = rows(history_file)
    assert len(kept) == history.MAX_RUNS
    assert kept[-1]["started_at"] == 9999.0
    assert kept[0]["started_at"] == 1001.0


def test_clearing_empties_the_history(history_file: Path) -> None:
    full_file(history_file, 3)

    history.clear(history_file)

    assert history.load(history_file).runs == ()
    assert written(history_file) == {"version": history.HISTORY_VERSION, "runs": []}


def test_a_history_cleared_mid_run_stays_cleared(history_file: Path) -> None:
    full_file(history_file, 3)
    recorder = history.Recorder(history_file)
    recorder.start(started_at=9999.0, speed_percent=100)

    history.clear(history_file)
    recorder.round_ended(rounds=1, joined=70, solved=26, failed=34)

    kept = history.load(history_file).runs
    assert [record.started_at for record in kept] == [9999.0]
    assert kept[0].solved == 26


def test_clearing_a_missing_file_raises_nothing(history_file: Path) -> None:
    history.clear(history_file)

    assert history.load(history_file).runs == ()


def test_a_failed_clear_raises_nothing(
    history_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full_file(history_file, 3)

    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("the folder is locked")

    monkeypatch.setattr(Path, "replace", refuse)
    history.clear(history_file)

    assert len(rows(history_file)) == 3


# --- nothing about who ------------------------------------------------------


def test_a_row_has_no_field_that_could_name_anyone() -> None:
    assert {field.name for field in dataclasses.fields(history.Record)} == ROW_FIELDS


def test_nothing_a_caller_hands_over_can_carry_a_username(history_file: Path) -> None:
    recorder = history.Recorder(history_file)
    recorder.start(started_at=1.0, speed_percent=100)
    recorder.round_ended(rounds=1, joined=70, solved=26, failed=34, price_per_1k=1.2)
    recorder.end(ended_at=2.0, ending=history.Ending.STOPPED, fault=ErrorCode.NO_CREDIT)

    text = history_file.read_text(encoding="utf-8")
    assert all(word not in text for word in ("user", "name", "cookie", "token", "key"))
