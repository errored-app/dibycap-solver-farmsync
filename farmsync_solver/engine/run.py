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
- A service fault is dibycap's, not the key's, so the round loop waits it out
  rather than ending the run (ADR 0003).
- Nothing here prints. A windowed build has no console (spec 2).
- Nothing here holds a sentence. The snapshot carries a `Headline` member and
  the numbers a line counts; the words are `ui/messages.py`'s (ADR 0005), which
  is why this file imports nothing out of `ui`.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, replace
from typing import Any, Callable

from .. import credit
from ..errors import AppError, ErrorCode, is_terminal, is_waitable
from ..logging_setup import event

from .dibycap import HOPELESS_CODES, Dibycap
from .farmsync import Farmsync
from .snapshot import IDLE, AccountRow, Headline, Result, RunSnapshot, RunState

# The fixed rest between rounds (spec 5.1) and the live credit read (spec 7).
# Module constants, not constructor arguments: spec 9.4 refuses a seam that only
# a test would use, so a test that needs a quick round patches these instead.
REST_SECONDS = 60.0
CREDIT_SECONDS = 10.0

# How long Waiting sits between probes (ADR 0003). Its own constant, not
# `REST_SECONDS`: a rest is the pace of the work, and this is the pace of a knock
# on a door that is not answering.
WAIT_SECONDS = 60.0

# How often a wait that is going nowhere says so in the log. Once per probe would
# be 60 lines an hour of "still down"; this is 12, which is enough to read an
# outage's length off the log without reading the gaps between timestamps.
WAIT_LOG_SECONDS = 300.0

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
        # Set when a service fault has been seen: the workers take no new account,
        # but the run is not over. Cleared once the round has drained.
        self._pausing = threading.Event()
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
        self._pausing.clear()
        _empty(self._accounts)
        _empty(self._finished)
        _empty(self._rows)
        # Back to the empty snapshot first, then through `_set`, so the run's
        # first state change is logged like every later one (spec 8.1).
        self._snapshot = IDLE
        self._set(state=RunState.DISCOVERING, headline=Headline.STARTING)

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
        self._set(state=RunState.STOPPING, headline=Headline.STOPPING)

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
            if not is_waitable(error):
                # Spec 5.4: a `/balance` that does not answer refuses the run.
                # There is no fallback thread count, so nothing is discovered and
                # no worker starts. A key fault and a zero balance land here.
                _log.warning(
                    event("run", phase="refused", code=error.code.value, detail=error.detail)
                )
                self._finish(error)
                return
            # dibycap itself is down. The run starts anyway and waits it out
            # (ADR 0003); the thread count is read again on the way back.
            _log.info(event("run", phase="waiting-at-start", code=error.code.value))
            threads = 0

        _log.info(event("run", phase="start", threads=threads, speed=speed_percent))
        farm = Farmsync(farm_token)
        round_number = 0

        try:
            while not self._stopping.is_set():
                round_number += 1
                self._set(round_number=round_number, done=0, total=0)
                _log.info(event("round", number=round_number, phase="start"))

                found = self._discover(client, farm)
                fault: AppError | None = None
                probe: Callable[[], bool] = lambda: False
                if found:
                    if threads <= 0:
                        threads, fault = self._read_threads(client, speed_percent)
                        probe = lambda: self._read_threads(client, speed_percent)[0] > 0
                    if fault is None:
                        fault = self._solve_round(client, found, threads)
                        account = found[0]
                        probe = lambda: self._probe(client, account)
                self._log_round_end(round_number, found)

                if fault is not None and is_waitable(fault):
                    if not self._wait_out(fault, probe):
                        break
                    continue  # a fresh round, which discovers again (ADR 0003)

                terminal = fault
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

    def _read_threads(self, client: Dibycap, speed_percent: int) -> tuple[int, AppError | None]:
        """The thread count, or the service fault that stopped us reading it.

        Only reached when a run started while dibycap was down, or came back from
        Waiting: a healthy run reads `/balance` once and keeps the answer. It is
        also the probe Waiting knocks with when `/balance` is the call that failed.
        """
        try:
            return self._thread_count(client, speed_percent), None
        except AppError as error:
            if not is_waitable(error):
                raise
            return 0, error

    def _discover(self, client: Dibycap, farm: Farmsync) -> list[dict[str, Any]] | None:
        """This round's eligible accounts. `None` means farmsync was not reached.

        A farmsync that cannot be reached is retried quietly and then waited out
        (spec 5.5); a farmsync that says no to the token raises, because every
        later round would be refused the same way.
        """
        self._set(
            state=RunState.DISCOVERING,
            headline=Headline.DISCOVERING,
            done=0,
            total=0,
            seconds_left=None,
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
            headline=Headline.SOLVING,
            total=len(accounts),
            done=0,
            seconds_left=None,
        )

        workers = [
            threading.Thread(
                target=self._work, args=(client,), name=f"engine-worker-{number}", daemon=True
            )
            for number in range(min(threads, len(accounts)))
        ]
        for worker in workers:
            worker.start()

        fault: AppError | None = None
        while any(worker.is_alive() for worker in workers):
            fault = self._drain(client) or fault
        fault = self._drain(client) or fault  # the last accounts land after the last look

        _empty(self._accounts)  # a stop leaves accounts nobody will take
        self._pausing.clear()  # the workers are gone; the flag has done its job
        return fault

    def _work(self, client: Dibycap) -> None:
        """One worker thread: take an account, solve it, put the outcome back."""
        while not self._stopping.is_set() and not self._pausing.is_set():
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
        """Take in what the workers finished, then refresh credit if it is due.

        Both faults stop new accounts from starting and let the in-flight ones
        land — the polite stop of spec 5.2. What differs is what the round loop
        does next: a key fault ends the run, a service fault is waited out.
        """
        fault: AppError | None = None
        try:
            while True:
                name, answer = self._finished.get(timeout=DRAIN_SECONDS)
                if isinstance(answer, AppError):
                    fault = fault or answer
                    if is_waitable(answer):
                        self._pausing.set()
                    else:
                        self._stopping.set()
                else:
                    self._count(name, answer)
        except queue.Empty:
            pass

        self._refresh_credit(client)
        return fault

    def _count(self, username: str, outcome: Outcome) -> None:
        """Fold one finished account into the counters and into the table."""
        current = self._snapshot
        counter = COUNTER_OF[outcome.result]
        done = current.done + 1

        self._set(done=done, **{counter: getattr(current, counter) + 1})
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

    def _wait_out(self, fault: AppError, probe: Callable[[], bool]) -> bool:
        """Sit in Waiting until dibycap answers again. `False` when the user stopped.

        The wait has no end of its own (ADR 0003): a paused service comes back on
        its own clock, so the only ways out are the service answering and the
        Stop button. Farmsync is not called at all in here — that is the whole
        point of holding an account to knock with.

        The probe is always the call that failed. A solve that was refused is
        knocked on with a solve, and a `/balance` that did not answer is knocked
        on with a `/balance`: a probe of the other call would report a service
        that is up while the run still cannot take a step.

        Nothing the probe finds is counted. The round number, the table and the
        three totals are left exactly as the interrupted round left them, because
        the round is run again in full once the service is back.

        The elapsed clock belongs to this call, so a service that comes back and
        dies again starts the count over. That reads wrong only if a probe
        succeeding is routinely followed by the round failing, and the probe is
        the same call the round makes.
        """
        _log.info(event("wait", phase="start", code=fault.code.value, detail=fault.detail))
        self._set(
            state=RunState.WAITING,
            headline=_waiting_headline(fault),
            seconds_waited=0.0,
            seconds_left=int(WAIT_SECONDS),
        )

        began = time.monotonic()
        said = 0.0
        while True:
            # The line ticks every second, like the rest does. A wait that
            # only redrew once a knock would sit unchanged for a minute at a
            # time, which is a run and a hung window telling the same story.
            left = WAIT_SECONDS
            while left > 0:
                waited = time.monotonic() - began
                self._set(seconds_waited=waited, seconds_left=int(left))
                if waited - said >= WAIT_LOG_SECONDS:
                    said = waited
                    _log.info(event("wait", phase="still", seconds=int(waited)))
                step = min(TICK_SECONDS, left)
                if self._stopping.wait(step):
                    _log.info(event("wait", phase="stopped"))
                    return False
                left -= step

            # The knock itself. A probe is a real solve, so against a sick
            # service it is the step most likely to take a while, and "in 0s"
            # held for ten seconds is the freeze again in miniature.
            self._set(seconds_waited=time.monotonic() - began, seconds_left=None)
            if probe():
                _log.info(event("wait", phase="end", seconds=int(time.monotonic() - began)))
                return True

    def _probe(self, client: Dibycap, account: dict[str, Any]) -> bool:
        """One real account, sent to ask whether solving is back.

        Any answer that is not a service fault means the service is answering,
        a dead cookie included: the probe asks about dibycap, not about the
        account. A key fault is raised, and the round loop ends the run on it.
        """
        try:
            solve_account(client, account)
        except AppError as error:
            if not is_waitable(error):
                raise
            _log.info(event("probe", result="down", code=error.code.value))
            return False

        _log.info(event("probe", result="up"))
        return True

    def _rest(self, client: Dibycap, headline: Headline) -> None:
        """The fixed pause between rounds. A stop cuts it short (spec 5.2)."""
        self._set(state=RunState.RESTING, headline=headline, seconds_left=int(REST_SECONDS))

        left = REST_SECONDS
        while left > 0:
            self._refresh_credit(client)
            self._set(seconds_left=int(left))
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
        headline goes with it, by name: the file has to say which line the user
        was reading, and it says it in the engine's words, not the user's.
        """
        was = self._snapshot
        self._snapshot = replace(self._snapshot, **changes)
        if self._snapshot.state is not was.state:
            _log.info(event("state", state=self._snapshot.state.value))
        if self._snapshot.headline is not was.headline:
            shown = self._snapshot.headline
            _log.info(event("shown", message=shown.name if shown is not None else ""))

    def _show_credit(self, balance: dict[str, Any]) -> None:
        self._set(credit_left=credit.money(balance), estimated_solves=credit.solves(balance))

    def _finish(self, terminal: AppError | None) -> None:
        """Back to Idle, keeping the totals so Home can show the last-run summary.

        The stop flag is set on the way out, so a worker that outlives the round
        loop takes no further account.

        A run that ended on a fault leaves its raw text in `detail`. That is what
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
            detail=terminal.detail if terminal else "",
            seconds_left=None,
        )


def _end_headline(terminal: AppError | None) -> Headline | ErrorCode:
    """The headline a finished run leaves behind.

    A named fault is its own headline: the code goes into the snapshot and the UI
    reads the sentence for it off the error table. An unnamed one is an engine bug
    as far as the user is concerned, and spec 5.6 gives it its own sentence: the
    run stopped, which "try again in a moment" does not say.
    """
    if terminal is None:
        return Headline.STOPPED
    if terminal.code is ErrorCode.UNKNOWN:
        return Headline.CRASHED
    return terminal.code


def _waiting_headline(fault: AppError) -> Headline:
    """What Waiting says, which is why we are waiting.

    Two sentences, not one: a paused service and a service that cannot be reached
    look the same to the engine and read nothing alike to the user.
    """
    if fault.code is ErrorCode.SERVICE_PAUSED:
        return Headline.WAITING_PAUSED
    return Headline.WAITING_UNREACHABLE


def _rest_headline(found: list[dict[str, Any]] | None) -> Headline:
    """What the rest says, which is how the round that just ended went.

    A farmsync that could not be reached, and a round with nothing to do, both
    say so through the whole rest rather than for the instant before it.
    """
    if found is None:
        return Headline.NO_FARMSYNC
    return Headline.RESTING if found else Headline.NO_ACCOUNTS


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
    is never told an attempt is a second try (spec 5.6). Three answers end it
    early — a terminal error, which the round loop must see at once; a service
    fault, which no number of attempts can fix; and a hopeless account, which a
    second attempt cannot change.

    Raises `AppError` for a key fault and for a service fault, and for nothing
    else. A retry against a down service would only be a slower way to reach the
    same answer, and this is also the probe Waiting knocks with.
    """
    account_id = str(account.get("id", ""))
    cookie = str(account.get("cookie") or "")
    detail = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _named(account_id, _read(client.solve(cookie)))
        except AppError as error:
            if is_terminal(error) or is_waitable(error):
                _log.info(
                    event(
                        "solve",
                        account=account_id,
                        result="service" if is_waitable(error) else "terminal",
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
