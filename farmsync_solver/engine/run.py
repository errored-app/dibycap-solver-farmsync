"""The `Engine`: the round loop, the worker threads, and the account queue.

Spec 9.2 and 9.8. `Engine` is the whole interface the UI gets — `start`, `stop`,
`snapshot`, `take_new_rows` — and this is the only file in the app that starts a
thread. The types that cross the seam live in `snapshot.py`, so the UI never has
to import this one.

Three rules shape the worker body at the bottom of the file:

- A failed account is normal operation, not an alarm: 28.6% of attempts fail
  (spec 2), so a failure is an outcome, not an exception.
- A terminal error is about the key, so it is raised at once and never retried
  (spec 5.5). The round loop ends the run on the first one.
- Nothing here prints. A windowed build has no console (spec 2).
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, replace
from typing import Any, Callable

from .. import credit
from ..errors import AppError, ErrorCode, is_terminal
from ..logging_setup import event

# The engine holds no user copy of its own: every sentence a run puts on screen
# comes from the one table of spec 9.7. `ui.messages` imports no NiceGUI, so a
# headless run pays nothing for this (spec 9.2).
from ..ui import messages
from .dibycap import HOPELESS_CODES, Dibycap
from .farmsync import Farmsync
from .snapshot import IDLE, AccountRow, Result, RunSnapshot, RunState

# The fixed rest between rounds (spec 5.1) and the live credit read (spec 7).
# Module constants, not constructor arguments: spec 9.4 refuses a seam that only
# a test would use, so a test that needs a quick round patches these instead.
REST_SECONDS = 60.0
CREDIT_SECONDS = 10.0

# Discovery is all or nothing now, so a failure is retried quietly rather than
# skipped per device: one try plus two retries (spec 5.5).
DISCOVERY_ATTEMPTS = 3

# How long the round loop waits on the finished queue before it looks at the
# clock again. Short enough that the credit refresh and the row stream stay
# live, long enough that the loop is not a spin.
DRAIN_SECONDS = 0.05
TICK_SECONDS = 1.0

# The snapshot counter each result adds to. One map, so the count is not a
# three-branch decision rebuilt for every finished account.
COUNTER_OF = {Result.JOINED: "joined", Result.SOLVED: "solved", Result.FAILED: "failed"}

# One gap per retry. The count follows from the schedule, so there is no cap
# constant that never binds.
BACKOFF_SECONDS = (1.0, 2.0)
MAX_ATTEMPTS = len(BACKOFF_SECONDS) + 1

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Outcome:
    """One account's result. Holds a farmsync id and a code — never a cookie."""

    account_id: str
    result: Result
    detail: str = ""


class Engine:
    """One run at a time, for the life of the app (spec 9.2).

    One `Engine` is built once and kept, so the UI's timer always has something
    to read: `snapshot()` answers when Idle too, and no caller ever has to invent
    an empty snapshot. It takes no arguments — `start` carries the plain values a
    run needs, so a bare script can drive it with no config file.

    Threading, in one paragraph: one round-loop thread owns every counter and is
    the only writer of the snapshot, which it replaces whole rather than editing,
    so a reader on the UI thread can never see half a change. The workers own
    nothing — they take accounts from one `queue.Queue` and put finished work on
    another, which is why spec 9.8's `Counter` and `ThreadLock` are gone.
    """

    def __init__(self) -> None:
        self._snapshot = IDLE
        self._stopping = threading.Event()
        self._loop: threading.Thread | None = None
        self._accounts: queue.Queue[dict[str, Any]] = queue.Queue()
        self._finished: queue.Queue[tuple[str, Outcome | AppError]] = queue.Queue()
        self._rows: queue.Queue[AccountRow] = queue.Queue()
        self._credit_read_at = 0.0

    # --- the four members the UI gets --------------------------------------

    def start(self, api_key: str, farm_token: str, speed_percent: int) -> None:
        """Begin a run. Plain values, so a bare script needs no config file.

        Every counter goes back to zero here, which is all spec 5.2's "Start
        after Stop is a fresh start" needs. A second call while a run is going is
        ignored rather than refused: the button is disabled anyway, and a double
        click must not begin a second run.
        """
        if self._is_running:
            return

        self._stopping.clear()
        _empty(self._accounts)
        _empty(self._finished)
        _empty(self._rows)
        # Back to the empty snapshot first, then through `_set`, so the run's
        # first state change is logged like every later one (spec 8.1).
        self._snapshot = IDLE
        self._set(state=RunState.DISCOVERING, headline=messages.RUN_STARTING)

        self._loop = threading.Thread(
            target=self._run,
            args=(api_key, farm_token, speed_percent),
            name="engine-round-loop",
            daemon=True,  # a closing window must not be held open by the run
        )
        self._loop.start()

    def stop(self) -> None:
        """The polite stop of spec 5.2: no new accounts, in-flight solves finish.

        Returns at once. The run is over when `snapshot().state` is Idle again.
        """
        if not self._is_running:
            return

        _log.info(event("stop"))
        self._stopping.set()
        self._set(state=RunState.STOPPING, headline=messages.RUN_STOPPING, message="")

    def snapshot(self) -> RunSnapshot:
        """The whole picture, now. Always answers, Idle included."""
        return self._snapshot

    def take_new_rows(self) -> list[AccountRow]:
        """The accounts finished since the last call. Empty when nothing is new."""
        rows: list[AccountRow] = []
        while True:
            try:
                rows.append(self._rows.get_nowait())
            except queue.Empty:
                return rows

    # --- the round loop ----------------------------------------------------

    @property
    def _is_running(self) -> bool:
        return self._loop is not None and self._loop.is_alive()

    def _run(self, api_key: str, farm_token: str, speed_percent: int) -> None:
        """The round-loop thread: rounds until stopped, or until the key fails."""
        client = Dibycap(api_key)
        terminal: AppError | None = None

        try:
            threads = self._thread_count(client, speed_percent)
        except AppError as error:
            # Spec 5.4: a `/balance` that does not answer refuses the run. There
            # is no fallback thread count, so nothing is discovered and no worker
            # starts.
            _log.warning(event("run", phase="refused", code=error.code.value, detail=error.detail))
            self._finish(error)
            return

        _log.info(event("run", phase="start", threads=threads, speed=speed_percent))
        farm = Farmsync(farm_token)
        round_number = 0

        try:
            while not self._stopping.is_set():
                round_number += 1
                self._set(round_number=round_number, done=0, total=0)
                _log.info(event("round", number=round_number, phase="start"))

                found = self._discover(client, farm)
                if found:
                    terminal = self._solve_round(client, found, threads)
                self._log_round_end(round_number, found)
                if terminal is not None:
                    break
                if self._stopping.is_set():
                    break
                self._rest(client, _rest_headline(found))
        except AppError as error:
            terminal = error
        except Exception as error:  # an engine bug stops the run, quietly (spec 5.5)
            _log.exception(event("run", phase="crashed", detail=f"{type(error).__name__}: {error}"))
            terminal = AppError.from_exception(error)

        self._finish(terminal)

    def _thread_count(self, client: Dibycap, speed_percent: int) -> int:
        """Read `/balance`, then derive the thread count from it (spec 5.4).

        Three answers refuse the run rather than guess at it: a call that fails,
        a key with no credit left (spec 7, "zero is terminal"), and a payload
        with no `max_concurrent` in it. The last one matters because the minimum
        of one thread would otherwise turn a missing figure into a crawling run.
        """
        balance = client.balance()
        self._show_credit(balance)
        self._credit_read_at = time.monotonic()

        if credit.solves(balance) <= 0:
            raise AppError(ErrorCode.NO_CREDIT, "estimated_solves=0")

        at_once = credit.max_concurrent(balance)
        if at_once <= 0:
            raise AppError(ErrorCode.UNKNOWN, "balance carried no max_concurrent")
        return credit.threads(at_once, speed_percent)

    def _discover(self, client: Dibycap, farm: Farmsync) -> list[dict[str, Any]] | None:
        """This round's eligible accounts. `None` means farmsync was not reached.

        A farmsync that cannot be reached is retried quietly and then waited out
        (spec 5.5); a farmsync that says no to the token raises, because every
        later round would be refused the same way.
        """
        self._set(
            state=RunState.DISCOVERING,
            headline=messages.RUN_DISCOVERING,
            message="",
            done=0,
            total=0,
        )

        for _ in range(DISCOVERY_ATTEMPTS):
            if self._stopping.is_set():
                return []
            self._refresh_credit(client)  # discovery is ~12 s of a ~72 s round
            try:
                found = farm.discover()
                _log.info(event("discover", accounts=len(found)))
                return found
            except AppError as error:
                if error.code is ErrorCode.BAD_FARM_TOKEN:
                    raise
                _log.warning(event("discover", phase="failed", code=error.code.value))

        return None

    def _solve_round(
        self, client: Dibycap, accounts: list[dict[str, Any]], threads: int
    ) -> AppError | None:
        """Run one round across the workers. Answers with what ended the run, if any.

        The workers are waited on by watching them, not by `join()`: the loop has
        to keep draining finished accounts and refreshing credit while they work.
        """
        for account in accounts:
            self._accounts.put(account)
        self._set(
            state=RunState.SOLVING,
            headline=messages.RUN_SOLVING,
            message=messages.run_progress(0, len(accounts)),
            total=len(accounts),
            done=0,
        )

        workers = [
            threading.Thread(
                target=self._work, args=(client,), name=f"engine-worker-{number}", daemon=True
            )
            for number in range(min(threads, len(accounts)))
        ]
        for worker in workers:
            worker.start()

        terminal: AppError | None = None
        while any(worker.is_alive() for worker in workers):
            terminal = self._drain(client) or terminal
        terminal = self._drain(client) or terminal  # the last accounts land after the last look

        _empty(self._accounts)  # a stop leaves accounts nobody will take
        return terminal

    def _work(self, client: Dibycap) -> None:
        """One worker thread: take an account, solve it, put the outcome back."""
        while not self._stopping.is_set():
            try:
                account = self._accounts.get_nowait()
            except queue.Empty:
                return

            name = _name_of(account)
            try:
                self._finished.put((name, solve_account(client, account)))
            except AppError as error:
                self._finished.put((name, error))
                return  # a fault about the key; the round loop decides what it means
            except Exception as error:
                self._finished.put((name, AppError.from_exception(error)))
                return

    def _drain(self, client: Dibycap) -> AppError | None:
        """Take in what the workers finished, then refresh credit if it is due."""
        terminal: AppError | None = None
        try:
            while True:
                name, answer = self._finished.get(timeout=DRAIN_SECONDS)
                if isinstance(answer, AppError):
                    terminal = terminal or answer
                    self._stopping.set()  # no new account starts after a key fault
                else:
                    self._count(name, answer)
        except queue.Empty:
            pass

        self._refresh_credit(client)
        return terminal

    def _count(self, username: str, outcome: Outcome) -> None:
        """Fold one finished account into the counters and into the table."""
        current = self._snapshot
        counter = COUNTER_OF[outcome.result]
        done = current.done + 1

        self._set(
            done=done,
            message=messages.run_progress(done, current.total),
            **{counter: getattr(current, counter) + 1},
        )
        self._rows.put(
            AccountRow(
                username=username,
                outcome=outcome.result,
                detail=outcome.detail,
                at=time.time(),
            )
        )

    def _refresh_credit(self, client: Dibycap) -> None:
        """The live credit read of spec 7: every 10 s, in every state of a run.

        A refresh that cannot be made is not a reason to stop — the run is
        working and the figure is only a display. A refresh that answers zero is:
        at zero the app would look busy while fixing nothing, so it raises and
        the round loop ends the run.
        """
        if time.monotonic() - self._credit_read_at < CREDIT_SECONDS:
            return
        self._credit_read_at = time.monotonic()

        try:
            balance = client.balance()
        except AppError as error:
            _log.info(event("credit", phase="missed", code=error.code.value))
            return

        self._show_credit(balance)
        if credit.solves(balance) <= 0:
            raise AppError(ErrorCode.NO_CREDIT, "estimated_solves=0")

    def _rest(self, client: Dibycap, headline: str) -> None:
        """The fixed pause between rounds. A stop cuts it short (spec 5.2)."""
        self._set(state=RunState.RESTING, headline=headline)

        left = REST_SECONDS
        while left > 0:
            self._refresh_credit(client)
            self._set(message=messages.run_rest(int(left)))
            step = min(TICK_SECONDS, left)
            if self._stopping.wait(step):
                return
            left -= step

    def _log_round_end(self, number: int, found: list[dict[str, Any]] | None) -> None:
        """Close the round in the log with the totals the run holds so far."""
        current = self._snapshot
        _log.info(
            event(
                "round",
                number=number,
                phase="end",
                found=0 if found is None else len(found),
                done=current.done,
                joined=current.joined,
                solved=current.solved,
                failed=current.failed,
            )
        )

    # --- the snapshot ------------------------------------------------------

    def _set(self, **changes: Any) -> None:
        """Replace the snapshot. Never edits one: a reader holds a whole value.

        Every state change is logged from here rather than from each caller, so
        spec 8.1's "every run-state change" cannot be missed by a new branch. The
        headline goes with it, by its `messages.py` name: the file has to say
        which sentence the user was reading, not read it back in friendly words.
        """
        was = self._snapshot
        self._snapshot = replace(self._snapshot, **changes)
        if self._snapshot.state is not was.state:
            _log.info(event("state", state=self._snapshot.state.value))
        if self._snapshot.headline != was.headline:
            _log.info(event("shown", message=messages.name_of(self._snapshot.headline)))

    def _show_credit(self, balance: dict[str, Any]) -> None:
        self._set(credit_left=credit.money(balance), estimated_solves=credit.solves(balance))

    def _finish(self, terminal: AppError | None) -> None:
        """Back to Idle, keeping the totals so Home can show the last-run summary.

        The stop flag is set on the way out, so a worker that outlives the round
        loop takes no further account.

        A run that ended on a fault leaves its raw text in `message`. That is what
        the screen puts behind the small **Details** link of spec 5.6 — the
        headline stays plain words, and the raw text is one click away.
        """
        _log.info(
            event(
                "run",
                phase="end",
                fault=terminal.code.value if terminal else "none",
                detail=terminal.detail if terminal else "",
            )
        )
        self._stopping.set()
        self._set(
            state=RunState.IDLE,
            headline=_end_headline(terminal),
            message=terminal.detail if terminal else "",
        )


def _end_headline(terminal: AppError | None) -> str:
    """The headline a finished run leaves behind.

    An unnamed fault is an engine bug as far as the user is concerned, and spec
    5.6 gives it its own sentence: the run stopped, which "try again in a moment"
    does not say.
    """
    if terminal is None:
        return messages.RUN_STOPPED
    if terminal.code is ErrorCode.UNKNOWN:
        return messages.RUN_CRASHED
    return messages.for_code(terminal.code)


def _rest_headline(found: list[dict[str, Any]] | None) -> str:
    """What the rest says, which is how the round that just ended went.

    A farmsync that could not be reached, and a round with nothing to do, both
    say so through the whole rest rather than for the instant before it.
    """
    if found is None:
        return messages.RUN_NO_FARMSYNC
    return messages.RUN_RESTING if found else messages.RUN_NO_ACCOUNTS


def _name_of(account: dict[str, Any]) -> str:
    """What the table calls this account. Its id when farmsync gives no name."""
    return str(account.get("username") or account.get("id") or "")


def _empty(waiting: queue.Queue[Any]) -> None:
    """Drop whatever is left in a queue, without blocking."""
    while True:
        try:
            waiting.get_nowait()
        except queue.Empty:
            return


def solve_account(
    client: Dibycap,
    account: dict[str, Any],
    sleep: Callable[[float], None] = time.sleep,
) -> Outcome:
    """Send one account to the solver and name what happened.

    Tries up to `MAX_ATTEMPTS` times. The retry is deliberately invisible: the UI
    is never told an attempt is a second try (spec 5.6). Two answers end it
    early — a terminal error, which the round loop must see at once, and a
    hopeless account, which a second attempt cannot change.

    Raises `AppError` for a terminal fault, and for nothing else.
    """
    account_id = str(account.get("id", ""))
    cookie = str(account.get("cookie") or "")
    detail = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _named(account_id, _read(client.solve(cookie)))
        except AppError as error:
            if is_terminal(error):
                _log.info(
                    event(
                        "solve",
                        account=account_id,
                        result="terminal",
                        code=error.code.value,
                        detail=error.detail,
                    )
                )
                raise
            detail = error.detail
            _log.info(
                event("attempt", account=account_id, number=attempt, detail=detail)
            )
            if detail in HOPELESS_CODES:
                break

        if attempt < MAX_ATTEMPTS:
            sleep(BACKOFF_SECONDS[attempt - 1])

    return _named(account_id, Result.FAILED, detail)


def _read(timings: dict[str, Any]) -> Result:
    """A solve is billed, a join is not, and the timings are what tell them apart."""
    solve_ms = timings.get("solve_ms") or 0
    return Result.SOLVED if solve_ms > 0 else Result.JOINED


def _named(account_id: str, result: Result, detail: str = "") -> Outcome:
    _log.info(event("solve", account=account_id, result=result.value, detail=detail))
    return Outcome(account_id=account_id, result=result, detail=detail)
