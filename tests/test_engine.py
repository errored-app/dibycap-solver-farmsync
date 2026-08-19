"""§5.2, §5.4, §5.5, §7, §9.2: the Engine runs a round, headless.

Every test here drives a real `Engine` with real threads and fake clients, so
the round loop, the account queue and the polite stop are exercised, not mocked.
Spec 9.4 refuses a client seam that only a test would use, so the fakes are put
in place of `run.Dibycap` and `run.Farmsync` with `monkeypatch`, and the two
timing constants are patched the same way to keep a round quick.

`wait_for` is how a test waits on another thread: no `sleep` long enough to be
flaky, no `join` on something that may never end.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

import pytest

from farmsync_solver.engine import Engine, run
from farmsync_solver.engine.snapshot import AccountRow, Result, RunSnapshot, RunState
from farmsync_solver.errors import AppError, ErrorCode
from farmsync_solver.ui import messages

from conftest import wait_for

from fakes import Script

REPO = Path(__file__).resolve().parent.parent
BALANCE = {
    "success": True,
    "balance": 8.4938,
    "estimated_solves": 5662,
    "price_per_1k": 1.5,
    "max_concurrent": 4,
}
FAST_REST = 0.01
NO_REFRESH = 1000.0
API_KEY = "secret-key-value"
TOKEN = "secret-farm-token"


def accounts(count: int) -> list[dict[str, Any]]:
    return [
        {"id": 100 + number, "username": f"user{number}", "cookie": f"cookie-{number}"}
        for number in range(count)
    ]


class FakeDibycap:
    """A dibycap client that answers from a script instead of the network."""

    def __init__(
        self,
        *balances: dict[str, Any] | Exception,
        solve: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self._balances = Script(*(balances or (dict(BALANCE),)))
        self._solve = solve or (lambda cookie: {"total_ms": 900, "solve_ms": 0})
        self.solved: list[str] = []
        self.worker_names: set[str] = set()

    @property
    def balance_calls(self) -> int:
        return self._balances.calls

    def balance(self) -> dict[str, Any]:
        return self._balances()

    def solve(self, cookie: str) -> dict[str, Any]:
        self.worker_names.add(threading.current_thread().name)
        self.solved.append(cookie)
        return self._solve(cookie)


class FakeFarmsync:
    """A farmsync client whose discovery is a canned answer per round."""

    def __init__(self, *rounds: list[dict[str, Any]] | Exception) -> None:
        self._rounds = Script(*(rounds or (accounts(3),)))

    @property
    def calls(self) -> int:
        return self._rounds.calls

    def discover(self) -> list[dict[str, Any]]:
        return self._rounds()


def build(
    monkeypatch: pytest.MonkeyPatch,
    engines: list[Engine],
    client: FakeDibycap | None = None,
    farm: FakeFarmsync | None = None,
    rest_seconds: float = FAST_REST,
    credit_seconds: float = NO_REFRESH,
) -> tuple[Engine, FakeDibycap, FakeFarmsync]:
    client = client or FakeDibycap()
    farm = farm or FakeFarmsync()
    monkeypatch.setattr(run, "Dibycap", lambda key: client)
    monkeypatch.setattr(run, "Farmsync", lambda token: farm)
    monkeypatch.setattr(run, "REST_SECONDS", rest_seconds)
    monkeypatch.setattr(run, "CREDIT_SECONDS", credit_seconds)

    engine = Engine()
    engines.append(engine)
    return engine, client, farm


def run_one_round(engine: Engine) -> None:
    """Let one round finish, then stop and wait for Idle."""
    assert wait_for(lambda: engine.snapshot().state is RunState.RESTING), engine.snapshot()
    engine.stop()
    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE), engine.snapshot()


# --- the seam --------------------------------------------------------------


def test_the_engine_offers_exactly_four_members() -> None:
    """Spec 9.2: four members is the whole interface the UI gets."""
    public = {name for name in vars(Engine) if not name.startswith("_")}

    assert public == {"start", "stop", "snapshot", "take_new_rows"}


def test_a_new_engine_answers_with_an_idle_snapshot() -> None:
    """No fake empty object is ever needed from the caller (spec 9.2)."""
    picture = Engine().snapshot()

    assert isinstance(picture, RunSnapshot)
    assert picture.state is RunState.IDLE
    assert (picture.round_number, picture.done, picture.total) == (0, 0, 0)


def test_the_snapshot_module_starts_no_thread() -> None:
    """The UI imports this file, so it must not pull in the threading ones."""
    source = (REPO / "farmsync_solver" / "engine" / "snapshot.py").read_text(encoding="utf-8")

    for banned in ("import threading", "import queue", "from .run", "import run"):
        assert banned not in source


def test_the_old_console_tool_is_gone() -> None:
    """Spec 9.8: `counter.py` and `thread_lock.py` become one `queue.Queue`."""
    assert not (REPO / "src").exists()


# --- one round -------------------------------------------------------------


def test_one_round_solves_every_eligible_account(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    engine, client, farm = build(monkeypatch, engines, farm=FakeFarmsync(accounts(5)))

    engine.start(API_KEY, TOKEN, 100)
    run_one_round(engine)

    assert sorted(client.solved) == sorted(f"cookie-{number}" for number in range(5))
    assert farm.calls == 1


def test_the_round_counts_each_outcome(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    def answer(cookie: str) -> dict[str, Any]:
        if cookie == "cookie-0":
            return {"solve_ms": 700}
        if cookie == "cookie-1":
            raise AppError(ErrorCode.UNKNOWN, "captcha_unsolvable")
        return {"solve_ms": 0}

    engine, _, _ = build(
        monkeypatch,
        engines,
        client=FakeDibycap(solve=answer),
        farm=FakeFarmsync(accounts(4)),
    )

    engine.start(API_KEY, TOKEN, 100)
    run_one_round(engine)

    picture = engine.snapshot()
    assert (picture.solved, picture.joined, picture.failed) == (1, 2, 1)
    assert (picture.done, picture.total, picture.round_number) == (4, 4, 1)


def test_finished_accounts_become_rows_taken_once(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    engine, _, _ = build(monkeypatch, engines, farm=FakeFarmsync(accounts(3)))

    engine.start(API_KEY, TOKEN, 100)
    run_one_round(engine)
    rows = engine.take_new_rows()

    assert isinstance(rows[0], AccountRow)
    assert sorted(row.username for row in rows) == ["user0", "user1", "user2"]
    assert all(row.outcome is Result.JOINED and row.at > 0 for row in rows)
    assert engine.take_new_rows() == []


def test_the_run_walks_the_states_of_a_round(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    engine, _, _ = build(monkeypatch, engines, rest_seconds=5.0)
    seen: list[RunState] = []

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: seen.append(engine.snapshot().state) or RunState.RESTING in seen)
    engine.stop()
    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE)

    assert RunState.SOLVING in seen
    assert seen[-1] is RunState.RESTING


def test_a_round_with_nothing_to_do_says_so_and_rests(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    engine, client, _ = build(monkeypatch, engines, farm=FakeFarmsync([]), rest_seconds=5.0)

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.RESTING)

    assert client.solved == []
    assert engine.snapshot().total == 0
    assert engine.snapshot().headline == messages.RUN_NO_ACCOUNTS


def test_a_second_round_follows_the_rest(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    engine, _, farm = build(monkeypatch, engines, farm=FakeFarmsync(accounts(2), accounts(2)))

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().round_number == 2)
    engine.stop()

    assert farm.calls >= 2


# --- threads from Speed ----------------------------------------------------


def test_the_run_uses_the_thread_count_speed_asks_for(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """Spec 5.4: 50% of this key's `max_concurrent` of 4 is two workers."""
    gate = threading.Event()
    engine, client, _ = build(
        monkeypatch,
        engines,
        client=FakeDibycap(solve=lambda cookie: gate.wait(5) and {"solve_ms": 0}),
        farm=FakeFarmsync(accounts(10)),
    )

    engine.start(API_KEY, TOKEN, 50)
    assert wait_for(lambda: len(client.solved) >= 2)
    gate.set()
    run_one_round(engine)

    assert len(client.worker_names) == 2


# --- what refuses a run ----------------------------------------------------


def test_an_unreachable_balance_refuses_the_run(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """Spec 5.4: no credit information, no fallback thread count, no run."""
    engine, client, farm = build(
        monkeypatch, engines, client=FakeDibycap(AppError(ErrorCode.NO_INTERNET, "timeout"))
    )

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE)

    assert farm.calls == 0
    assert client.solved == []
    assert engine.snapshot().headline == messages.for_code(ErrorCode.NO_INTERNET)


def test_a_key_with_no_credit_left_refuses_the_run(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """Spec 7: zero is terminal — the run stops and will not start."""
    engine, _, farm = build(
        monkeypatch, engines, client=FakeDibycap(dict(BALANCE, estimated_solves=0))
    )

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE)

    assert farm.calls == 0
    assert engine.snapshot().headline == messages.for_code(ErrorCode.NO_CREDIT)


def test_a_balance_with_no_max_concurrent_refuses_the_run(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """A missing figure must not quietly become the minimum of one thread."""
    thin = {"success": True, "estimated_solves": 5662, "balance": 8.49, "price_per_1k": 1.5}
    engine, _, farm = build(monkeypatch, engines, client=FakeDibycap(thin))

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE)

    assert farm.calls == 0
    assert engine.snapshot().headline == messages.RUN_CRASHED
    assert engine.snapshot().message == "balance carried no max_concurrent"


# --- what ends a run -------------------------------------------------------


def test_a_terminal_solver_error_ends_the_run(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    def refuse(cookie: str) -> dict[str, Any]:
        raise AppError(ErrorCode.NO_CREDIT, "insufficient_balance")

    engine, _, _ = build(
        monkeypatch, engines, client=FakeDibycap(solve=refuse), farm=FakeFarmsync(accounts(6))
    )

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE)

    assert engine.snapshot().headline == messages.for_code(ErrorCode.NO_CREDIT)


def test_a_refused_farm_token_ends_the_run(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    engine, _, farm = build(
        monkeypatch,
        engines,
        farm=FakeFarmsync(AppError(ErrorCode.BAD_FARM_TOKEN, "devices http 401")),
    )

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE)

    assert farm.calls == 1  # not retried: every later round is refused the same way
    assert engine.snapshot().headline == messages.for_code(ErrorCode.BAD_FARM_TOKEN)


def test_an_unreachable_farmsync_is_retried_and_then_waited_out(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """Spec 5.5: discovery failure is retried twice quietly, then rested out."""
    dead = AppError(ErrorCode.NO_INTERNET, "farmsync ConnectionError")
    engine, _, farm = build(
        monkeypatch,
        engines,
        farm=FakeFarmsync(dead, dead, dead, accounts(2)),
        rest_seconds=5.0,
    )

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.RESTING)

    assert farm.calls == 3
    assert engine.snapshot().headline == messages.RUN_NO_FARMSYNC


# --- credit ----------------------------------------------------------------


def test_the_run_shows_the_credit_it_started_from(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    engine, _, _ = build(monkeypatch, engines)

    engine.start(API_KEY, TOKEN, 100)
    run_one_round(engine)

    picture = engine.snapshot()
    assert picture.estimated_solves == 5662
    assert picture.credit_left == pytest.approx(8.493, abs=0.01)


def test_credit_is_refreshed_while_accounts_are_being_checked(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """Spec 7: every 10 s during a run. Here, every 0 s, so the test is quick."""
    gate = threading.Event()
    engine, _, _ = build(
        monkeypatch,
        engines,
        client=FakeDibycap(
            dict(BALANCE),
            dict(BALANCE, estimated_solves=42),
            solve=lambda cookie: gate.wait(5) and {"solve_ms": 0},
        ),
        farm=FakeFarmsync(accounts(4)),
        credit_seconds=0.0,
    )

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.SOLVING)
    assert wait_for(lambda: engine.snapshot().estimated_solves == 42)
    gate.set()


def test_credit_is_refreshed_during_the_rest(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """The rest is 60 s of a ~72 s round, so a stale figure there is most of it."""
    engine, client, _ = build(
        monkeypatch, engines, farm=FakeFarmsync([]), rest_seconds=5.0, credit_seconds=0.0
    )

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.RESTING)
    resting_at = client.balance_calls

    assert wait_for(lambda: client.balance_calls > resting_at)
    assert engine.snapshot().state is RunState.RESTING


def test_a_refresh_that_reads_zero_stops_the_run(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    engine, _, _ = build(
        monkeypatch,
        engines,
        client=FakeDibycap(dict(BALANCE), dict(BALANCE, estimated_solves=0)),
        farm=FakeFarmsync(accounts(4)),
        credit_seconds=0.0,
    )

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE)

    assert engine.snapshot().headline == messages.for_code(ErrorCode.NO_CREDIT)


def test_a_missed_refresh_does_not_stop_the_run(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    engine, _, _ = build(
        monkeypatch,
        engines,
        client=FakeDibycap(dict(BALANCE), AppError(ErrorCode.NO_INTERNET, "timeout")),
        farm=FakeFarmsync(accounts(4)),
        credit_seconds=0.0,
    )

    engine.start(API_KEY, TOKEN, 100)
    run_one_round(engine)

    assert engine.snapshot().done == 4


# --- stop and restart ------------------------------------------------------


def test_stop_starts_no_new_account_and_lets_the_last_one_finish(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """Spec 5.2: the polite stop. An in-flight attempt may already be paid for."""
    started = threading.Event()
    gate = threading.Event()

    def slow(cookie: str) -> dict[str, Any]:
        started.set()
        gate.wait(5)
        return {"solve_ms": 0}

    engine, client, _ = build(
        monkeypatch, engines, client=FakeDibycap(solve=slow), farm=FakeFarmsync(accounts(20))
    )

    engine.start(API_KEY, TOKEN, 25)  # one worker, so exactly one is in flight
    assert started.wait(5)
    engine.stop()
    assert engine.snapshot().state is RunState.STOPPING
    gate.set()
    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE)

    assert len(client.solved) == 1
    assert engine.snapshot().done == 1


def test_a_stop_during_the_rest_is_instant(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    engine, _, _ = build(monkeypatch, engines, rest_seconds=60.0)

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.RESTING)
    engine.stop()

    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE, timeout=2)


def test_starting_again_resets_every_counter(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    engine, _, _ = build(monkeypatch, engines, farm=FakeFarmsync(accounts(3), accounts(1)))

    engine.start(API_KEY, TOKEN, 100)
    run_one_round(engine)
    assert engine.snapshot().joined == 3

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().round_number == 1)
    assert wait_for(lambda: engine.snapshot().done == 1)

    picture = engine.snapshot()
    assert (picture.joined, picture.solved, picture.failed) == (1, 0, 0)
    assert engine.take_new_rows()[0].username == "user0"


def test_a_second_start_while_running_is_ignored(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    engine, _, farm = build(monkeypatch, engines, rest_seconds=60.0)

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.RESTING)
    engine.start(API_KEY, TOKEN, 100)

    assert engine.snapshot().round_number == 1
    assert farm.calls == 1


def test_stopping_an_idle_engine_does_nothing() -> None:
    engine = Engine()

    engine.stop()

    assert engine.snapshot().state is RunState.IDLE


# --- Waiting out a down solve service (ADR 0003) ---------------------------

PAUSED = AppError(ErrorCode.SERVICE_PAUSED, "service_paused", service=True)
UNREACHABLE = AppError(ErrorCode.NO_INTERNET, "dibycap ConnectionError", service=True)
FAST_WAIT = 0.01


class Service:
    """A solve that is down until it is told the service came back."""

    def __init__(self, fault: AppError | None) -> None:
        self.fault = fault
        self.attempts = 0

    def __call__(self, cookie: str) -> dict[str, Any]:
        self.attempts += 1
        if self.fault is not None:
            raise self.fault
        return {"total_ms": 900, "solve_ms": 0}

    def comes_back(self) -> None:
        self.fault = None


def waiting(
    monkeypatch: pytest.MonkeyPatch,
    engines: list[Engine],
    fault: AppError = PAUSED,
    balances: tuple[dict[str, Any] | Exception, ...] = (),
) -> tuple[Engine, Service, FakeFarmsync]:
    """A started engine whose solve service is down, parked in Waiting."""
    service = Service(fault)
    engine, _, farm = build(
        monkeypatch,
        engines,
        client=FakeDibycap(*balances, solve=service),
        farm=FakeFarmsync(accounts(3)),
    )
    monkeypatch.setattr(run, "WAIT_SECONDS", FAST_WAIT)

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.WAITING), engine.snapshot()
    return engine, service, farm


def test_a_paused_service_waits_instead_of_ending_the_run(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """The whole point of ADR 0003: the run does not die on a fault it cannot fix."""
    engine, _, _ = waiting(monkeypatch, engines)

    picture = engine.snapshot()
    assert picture.state is RunState.WAITING
    assert picture.headline == messages.RUN_WAITING_PAUSED


def test_a_service_that_cannot_be_reached_says_so_instead(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """Someone whose wifi is off must not read that the service is paused."""
    engine, _, _ = waiting(monkeypatch, engines, fault=UNREACHABLE)

    assert engine.snapshot().headline == messages.RUN_WAITING_UNREACHABLE


def test_farmsync_is_left_alone_while_the_run_waits(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """The probe knocks on dibycap with a held account, never on farmsync."""
    engine, service, farm = waiting(monkeypatch, engines)

    assert wait_for(lambda: service.attempts >= 5)  # five knocks in
    assert farm.calls == 1  # and still one discovery, not five


def test_waiting_counts_nothing_it_probes_with(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """A probe is a knock on a door, not work: no row, no counter, no round."""
    engine, service, _ = waiting(monkeypatch, engines)

    assert wait_for(lambda: service.attempts >= 5)
    picture = engine.snapshot()
    assert (picture.joined, picture.solved, picture.failed) == (0, 0, 0)
    assert picture.round_number == 1
    assert engine.take_new_rows() == []


def test_the_run_carries_on_when_the_service_comes_back(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """A clean round, discovered again, and the probe's own account not counted."""
    engine, service, farm = waiting(monkeypatch, engines)

    service.comes_back()

    assert wait_for(lambda: engine.snapshot().state is RunState.RESTING), engine.snapshot()
    picture = engine.snapshot()
    assert picture.round_number == 2
    assert picture.joined == 3  # the three accounts of round 2, not the probe as a fourth
    assert farm.calls == 2  # discovered again on the way out of Waiting


def test_stop_ends_a_waiting_run(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """Waiting is a run like any other, so the Stop button still owns it."""
    engine, _, _ = waiting(monkeypatch, engines)

    engine.stop()

    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE), engine.snapshot()


def test_a_waiting_run_is_a_run_the_window_asks_about(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """Spec 5.3's close question reads `is not IDLE`, and Waiting is not Idle."""
    from farmsync_solver.ui import home

    engine, _, _ = waiting(monkeypatch, engines)

    assert home.should_confirm_close(engine.snapshot().state)


def test_a_key_fault_found_while_waiting_still_ends_the_run(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """Waiting forever on a key nobody but the user can fix would be cruel."""
    engine, service, _ = waiting(monkeypatch, engines)

    service.fault = AppError(ErrorCode.BAD_API_KEY, "invalid_api_key")

    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE), engine.snapshot()
    assert engine.snapshot().headline == messages.for_code(ErrorCode.BAD_API_KEY)


def test_a_run_starts_and_waits_when_balance_itself_is_down(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """Start with dibycap fully down: one discovery, then a quiet wait."""
    down = AppError(ErrorCode.NO_INTERNET, "dibycap ConnectionError", service=True)
    client = FakeDibycap(down, down, down, dict(BALANCE), solve=Service(None))
    engine, _, farm = build(monkeypatch, engines, client=client, farm=FakeFarmsync(accounts(2)))
    monkeypatch.setattr(run, "WAIT_SECONDS", FAST_WAIT)

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.WAITING), engine.snapshot()
    assert engine.snapshot().headline == messages.RUN_WAITING_UNREACHABLE
    assert farm.calls == 1  # discovered once, then left alone

    # The fourth `/balance` answers, so the run picks itself up.
    assert wait_for(lambda: engine.snapshot().state is RunState.RESTING), engine.snapshot()
    assert engine.snapshot().joined == 2


def test_a_balance_that_refuses_the_key_still_refuses_the_run(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """Only a service fault waits. A key fault at Start is refused as before."""
    refused = AppError(ErrorCode.BAD_API_KEY, "invalid_api_key")
    engine, _, farm = build(monkeypatch, engines, client=FakeDibycap(refused))

    engine.start(API_KEY, TOKEN, 100)

    assert wait_for(lambda: engine.snapshot().state is RunState.IDLE), engine.snapshot()
    assert engine.snapshot().headline == messages.for_code(ErrorCode.BAD_API_KEY)
    assert farm.calls == 0


class StickyService(Service):
    """A service whose knock can be made to hang, the way a sick one really does."""

    def __init__(self, fault: AppError | None) -> None:
        super().__init__(fault)
        self.hang = threading.Event()
        self.let_go = threading.Event()

    def __call__(self, cookie: str) -> dict[str, Any]:
        if self.hang.is_set():
            self.let_go.wait(5.0)
        return super().__call__(cookie)


def test_the_waiting_line_moves_between_knocks(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """A minute of an unchanging screen reads as a hung window, not a run."""
    engine, _, _ = waiting(monkeypatch, engines)
    # A knock a long way off, so the ticks between them are what the test sees.
    monkeypatch.setattr(run, "WAIT_SECONDS", 3.0)
    monkeypatch.setattr(run, "TICK_SECONDS", 0.02)

    seen: set[str] = set()

    def counted_down() -> bool:
        seen.add(engine.snapshot().message)
        return len([line for line in seen if "Checking again" in line]) >= 2

    assert wait_for(counted_down), seen


def test_the_waiting_line_says_the_knock_is_out_while_it_hangs(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine]
) -> None:
    """The probe is a real solve: against a sick service it is what takes the time."""
    service = StickyService(PAUSED)
    engine, _, _ = build(
        monkeypatch,
        engines,
        client=FakeDibycap(solve=service),
        farm=FakeFarmsync(accounts(3)),
    )
    monkeypatch.setattr(run, "WAIT_SECONDS", FAST_WAIT)

    engine.start(API_KEY, TOKEN, 100)
    assert wait_for(lambda: engine.snapshot().state is RunState.WAITING), engine.snapshot()
    service.hang.set()

    try:
        assert wait_for(lambda: engine.snapshot().message.endswith("Checking now…")), (
            engine.snapshot()
        )
    finally:
        service.let_go.set()


def test_a_long_wait_says_so_in_the_log(
    monkeypatch: pytest.MonkeyPatch, engines: list[Engine], caplog: pytest.LogCaptureFixture
) -> None:
    """An outage's length should be readable off the log, not inferred from gaps."""
    monkeypatch.setattr(run, "WAIT_LOG_SECONDS", 0.0)
    with caplog.at_level("INFO"):
        engine, service, _ = waiting(monkeypatch, engines)
        assert wait_for(lambda: service.attempts >= 3)

    assert any(text.startswith("wait ") and "phase=still" in text for text in caplog.messages)
