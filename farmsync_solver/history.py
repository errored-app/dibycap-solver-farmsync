"""The only reader of history.json: one record per run, and what it spent.

Spec 10.2. It owns the file's name and its shape the way `config` owns
`config.json`, and asks `paths` where the folder is. Three rules shape it:

- **A record is written when the run starts**, and rewritten on each round end
  and once more at the end (ADR 0008). A record with no `ended_at` is not
  damage: it is the record of an app that was closed mid-run, and it reads as
  `interrupted`.
- **The money is not stored.** The counts and the price are, and the screen
  works the money out from them, so a record can never disagree with itself.
- **Nothing here reaches the screen or ends a run.** A corrupt file, an
  unreadable record and a write that will not go through are all logged and
  swallowed. The caller is told nothing, because there is nothing it can do.

No usernames, ever. The record's fields are the whole of what is written, and
none of them can name anyone.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from . import paths
from .errors import ErrorCode

HISTORY_VERSION = 1
MAX_RUNS = 500

_log = logging.getLogger(__name__)


class Ending(str, Enum):
    """How a run finished (ADR 0009). Three are written; the fourth is read."""

    STOPPED = "stopped"  # the user pressed Stop
    FAULTED = "faulted"  # a terminal error ended it, named in `fault`
    CRASHED = "crashed"  # an engine bug
    INTERRUPTED = "interrupted"  # no end time: the process died before it could


WRITTEN_ENDINGS = (Ending.STOPPED, Ending.FAULTED, Ending.CRASHED)


@dataclass(frozen=True)
class Record:
    """One run's row in the file. Times are epoch seconds, like `AccountRow.at`.

    A `Run` is what the app is doing; this is what it left behind, which is why
    it is a record and not a run (`CONTEXT.md`).
    """

    started_at: float
    speed_percent: int
    ended_at: float | None = None
    ending: Ending | None = None
    fault: ErrorCode | None = None
    rounds: int = 0
    joined: int = 0
    solved: int = 0
    failed: int = 0
    price_per_1k: float | None = None


@dataclass(frozen=True)
class History:
    """Every record the file holds, oldest first.

    `from_newer_build` is the one thing the screen has to know about the file
    itself: an empty history and a history this build cannot read look the same
    otherwise, and only one of them means *no runs yet* (spec 4.5).
    """

    runs: tuple[Record, ...] = ()
    from_newer_build: bool = False


def default_path() -> Path:
    r"""`%APPDATA%\FarmsyncSolver\history.json`, beside the config."""
    return paths.app_data_dir() / "history.json"


def load(path: Path | None = None) -> History:
    """Read the file. Anything wrong with it reads as an empty history."""
    target = _target(path)
    raw = _payload(target)
    if raw is None:
        return History()

    version, listed = raw
    if version > HISTORY_VERSION:
        _log.warning(
            "history was written by a newer build (version=%s); leaving it alone",
            version,
        )
        return History(from_newer_build=True)

    return History(runs=tuple(_readable(listed)))


def prune(path: Path | None = None) -> None:
    """Spec 10.2: keep the newest 500 records, the way the logs are pruned."""
    target = _target(path)
    held = load(target)
    if held.from_newer_build or len(held.runs) <= MAX_RUNS:
        return

    dropped = len(held.runs) - MAX_RUNS
    if _Writer(target).write(held.runs[-MAX_RUNS:]):
        _log.info("history pruned dropped=%s kept=%s", dropped, MAX_RUNS)


def clear(path: Path | None = None) -> None:
    """Spec 4.5's Clear history: every record goes, the file stays."""
    target = _target(path)
    if load(target).from_newer_build:
        return

    if _Writer(target).write(()):
        _log.info("history cleared")


class Recorder:
    """One run's record, kept in step with the file as the run goes.

    Every write re-reads the file and puts this run's record back into what it
    finds, rather than holding the other records from the start of the run: the
    history can be cleared while a run is on (spec 4.5), and a cleared history
    must stay cleared when the next round ends.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._writer = _Writer(_target(path))
        self._record: Record | None = None

    def start(self, *, started_at: float, speed_percent: int) -> None:
        """Write the record the moment the run starts, counts still at zero."""
        self._record = Record(started_at=started_at, speed_percent=speed_percent)
        self._save()

    def round_ended(
        self,
        *,
        rounds: int,
        joined: int,
        solved: int,
        failed: int,
        price_per_1k: float | None = None,
    ) -> None:
        """Update the record with the counts a finished round leaves behind."""
        if self._record is None:
            _log.debug("a round ended before the run started; nothing to write")
            return

        self._record = replace(
            self._record,
            rounds=rounds,
            joined=joined,
            solved=solved,
            failed=failed,
            price_per_1k=self._price(price_per_1k),
        )
        self._save()

    def end(
        self,
        *,
        ended_at: float,
        ending: Ending,
        fault: ErrorCode | None = None,
        price_per_1k: float | None = None,
    ) -> None:
        """Close the record: when it ended, who ended it, and what was wrong.

        A price is taken here as well as on a round end, because a run that
        faulted halfway through its first round still read one, and that is the
        rate the user was watching (spec 10.2).
        """
        if ending not in WRITTEN_ENDINGS:
            raise ValueError(f"ending={ending!r} is derived on read, never written")

        if self._record is None:
            _log.debug("a run ended before it started; nothing to write")
            return

        self._record = replace(
            self._record,
            ended_at=ended_at,
            ending=ending,
            fault=fault,
            price_per_1k=self._price(price_per_1k),
        )
        self._save()

    def _price(self, read: float | None) -> float | None:
        """The last price the run read. A round that read none changes nothing."""
        if read is not None:
            return read
        return self._record.price_per_1k if self._record else None

    def _save(self) -> None:
        if self._record is None:
            return

        held = load(self._writer.path)
        if held.from_newer_build:
            return

        mine = self._record.started_at
        others = [other for other in held.runs if other.started_at != mine]
        self._writer.write([*others[-(MAX_RUNS - 1) :], self._record])


class _Writer:
    """Writes the whole file atomically, and says so once when it cannot.

    The first failure is a `warning` with the reason, later ones `debug`: a
    locked folder must not put eighty identical lines in a four-hour run's log
    (ADR 0008).
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._reported = False

    def write(self, records: Sequence[Record]) -> bool:
        """True when the file now holds these records. Never raises."""
        body = json.dumps(
            {"version": HISTORY_VERSION, "runs": [_row(record) for record in records]},
            indent=2,
        )
        temporary = self.path.with_name(self.path.name + ".tmp")

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(body)
            temporary.replace(self.path)
        except OSError as error:
            self._failed(error)
            _remove(temporary)
            return False
        return True

    def _failed(self, error: OSError) -> None:
        if self._reported:
            _log.debug("history could not be written again: %s", error)
            return
        self._reported = True
        _log.warning("history could not be written: %s; the run carries on", error)


def _target(path: Path | None) -> Path:
    return path if path is not None else default_path()


def _row(record: Record) -> dict[str, Any]:
    """One row, holding the fields of spec 10.2 and nothing else.

    An absent field rather than a null: `ended_at` missing is what makes a run
    `interrupted`, and a price that was never read is a dash on screen.
    """
    row: dict[str, Any] = {"started_at": record.started_at}
    if record.ended_at is not None:
        row["ended_at"] = record.ended_at
    if record.ending is not None and record.ending in WRITTEN_ENDINGS:
        row["ending"] = record.ending.value
    if record.fault is not None:
        row["fault"] = record.fault.value
    row["rounds"] = record.rounds
    row["joined"] = record.joined
    row["solved"] = record.solved
    row["failed"] = record.failed
    row["speed_percent"] = record.speed_percent
    if record.price_per_1k is not None:
        row["price_per_1k"] = record.price_per_1k
    return row


def _payload(target: Path) -> tuple[int, list[Any]] | None:
    """The file's version and its rows, or None when there is nothing to read.

    Anything that is not an object with an int `version` and a list `runs` is
    corrupt, a bare array included: an array has nowhere to hang a version, so
    an old shape and a broken one would be the same thing.
    """
    try:
        raw: Any = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except OSError as error:
        _log.warning("history could not be read: %s; showing none of it", error)
        return None
    except ValueError:
        _move_aside(target, "it is not JSON")
        return None

    reason = _wrong_shape(raw)
    if reason is not None:
        _move_aside(target, reason)
        return None
    return raw["version"], raw["runs"]


def _wrong_shape(raw: Any) -> str | None:
    """What is wrong with the file's own shape, or None when nothing is."""
    if not isinstance(raw, dict):
        return "it is not an object"
    version = raw.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        return "it has no version"
    if not isinstance(raw.get("runs"), list):
        return "its runs are not a list"
    return None


def _move_aside(target: Path, reason: str) -> None:
    """Keep the bad file in one slot. Spending records have no fallback.

    Overwritten each time rather than kept per timestamp: one bad file is worth
    a look, a folder of them is only ever litter.
    """
    corrupt = target.with_name(target.name + ".corrupt")
    try:
        target.replace(corrupt)
    except OSError as error:
        _log.warning("history is unreadable (%s) and would not move: %s", reason, error)
        return

    _log.warning("history is unreadable (%s); moved to %s", reason, corrupt.name)


def _readable(listed: list[Any]) -> list[Record]:
    """Every row that can be read. One bad row does not condemn its neighbours."""
    records: list[Record] = []
    for index, raw in enumerate(listed):
        record = _read_record(raw)
        if record is None:
            _log.warning("history row %s could not be read; dropping it", index)
            continue
        records.append(record)
    return records


def _read_record(raw: Any) -> Record | None:
    """One row, or None when a field it cannot do without is missing or odd."""
    if not isinstance(raw, dict):
        return None

    started_at = _number(raw.get("started_at"))
    speed_percent = _count(raw.get("speed_percent"))
    rounds = _count(raw.get("rounds"))
    joined = _count(raw.get("joined"))
    solved = _count(raw.get("solved"))
    failed = _count(raw.get("failed"))
    if started_at is None or speed_percent is None:
        return None
    if rounds is None or joined is None or solved is None or failed is None:
        return None

    ended_at: float | None = None
    ending = Ending.INTERRUPTED
    if raw.get("ended_at") is not None:
        ended_at = _number(raw["ended_at"])
        written = _ending(raw.get("ending"))
        if ended_at is None or written is None:
            return None
        ending = written

    price_per_1k: float | None = None
    if raw.get("price_per_1k") is not None:
        price_per_1k = _number(raw["price_per_1k"])
        if price_per_1k is None:
            return None

    return Record(
        started_at=started_at,
        speed_percent=speed_percent,
        ended_at=ended_at,
        ending=ending,
        fault=_fault(raw.get("fault")),
        rounds=rounds,
        joined=joined,
        solved=solved,
        failed=failed,
        price_per_1k=price_per_1k,
    )


def _ending(value: object) -> Ending | None:
    """One of the three written words, or None.

    A word this build has never heard of costs the row its place, unlike an
    unknown `fault`: a record that ended has to say how, and a file written by
    a build with a fourth word carries a newer `version` too, which is caught
    long before this (ADR 0009).
    """
    for ending in WRITTEN_ENDINGS:
        if value == ending.value:
            return ending
    return None


def _fault(value: object) -> ErrorCode | None:
    """The code in force at the end, or nothing.

    A code this build has never heard of costs the row its fault, not its place
    in the file: the counts and the money are still true (ADR 0009).
    """
    if value is None:
        return None
    try:
        return ErrorCode(value)
    except ValueError:
        _log.debug("history row carries an unknown fault %r; dropping the fault", value)
        return None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _remove(temporary: Path) -> None:
    try:
        temporary.unlink(missing_ok=True)
    except OSError as error:
        _log.debug("the history temp file would not go: %s", error)
