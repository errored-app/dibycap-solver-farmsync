"""§5.5, §8.2, §9.4, §9.7: one account in, one named outcome out."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from farmsync_solver.engine import run
from farmsync_solver.engine.dibycap import COOKIE_FIELD, HOPELESS_CODES, Dibycap
from farmsync_solver.errors import AppError, ErrorCode, is_terminal

from fakes import FakeResponse, FakeSession, Queue

CREATE_URL = "https://api.dibycap.com/createTask"
POLL_URL = "https://api.dibycap.com/getTask"
PACKAGE = Path(__file__).resolve().parent.parent / "farmsync_solver"

API_KEY = "secret-key-value"
COOKIE = "WARNING-DO-NOT-SHARE-THIS-super-secret-cookie"
ACCOUNT = {"id": 4821, "cookie": COOKIE, "username": "someone"}


def answers(*polls: FakeResponse) -> dict[str, Any]:
    """A createTask answer, then one getTask answer per poll."""
    return {
        CREATE_URL: FakeResponse(payload={"success": True, "task_id": "t-1"}),
        POLL_URL: Queue(*polls),
    }


def solved(**timings: Any) -> FakeResponse:
    return FakeResponse(payload={"success": True, "status": "done", "timings": timings})


def refused(code: str) -> FakeResponse:
    return FakeResponse(payload={"success": False, "error": code})


def nothing(_seconds: float) -> None:
    """A sleep that costs no time."""


def client(session: FakeSession) -> Dibycap:
    return Dibycap(API_KEY, session=session, sleep=nothing)


# --- Dibycap.solve ---------------------------------------------------------


def test_solve_sends_the_cookie_to_create_a_task() -> None:
    session = FakeSession(answers(solved(total_ms=900, solve_ms=0)))

    client(session).solve(COOKIE)

    assert session.urls == [CREATE_URL, POLL_URL]
    assert session.bodies[0] == {"cookie": f"{COOKIE_FIELD}={COOKIE}"}
    assert session.sent_headers["X-API-Key"] == API_KEY


def test_solve_returns_the_timings() -> None:
    session = FakeSession(answers(solved(total_ms=1500, solve_ms=700)))

    assert client(session).solve(COOKIE) == {"total_ms": 1500, "solve_ms": 700}


@pytest.mark.parametrize("status", ["pending", "solving", "processing"])
def test_solve_waits_while_the_task_is_still_running(status: str) -> None:
    waiting = FakeResponse(payload={"status": status, "retry_after_ms": 300})
    session = FakeSession(answers(waiting, solved(total_ms=800)))
    slept: list[float] = []

    Dibycap(API_KEY, session=session, sleep=slept.append).solve(COOKIE)

    assert session.urls == [CREATE_URL, POLL_URL, POLL_URL]
    assert slept == [0.3]


def test_a_task_that_never_finishes_ends_as_an_error() -> None:
    session = FakeSession(answers(FakeResponse(payload={"status": "pending"})))

    with pytest.raises(AppError) as caught:
        client(session).solve(COOKIE)
    assert caught.value.code is ErrorCode.UNKNOWN
    assert "timeout" in caught.value.detail


def test_a_create_task_with_no_task_id_is_an_error() -> None:
    session = FakeSession({CREATE_URL: FakeResponse(payload={"error": "cookie_dead"})})

    with pytest.raises(AppError) as caught:
        client(session).solve(COOKIE)
    assert caught.value.code is ErrorCode.UNKNOWN
    assert caught.value.detail == "cookie_dead"


def test_a_failed_solve_keeps_the_raw_dibycap_code() -> None:
    session = FakeSession(answers(refused("captcha_unsolvable")))

    with pytest.raises(AppError) as caught:
        client(session).solve(COOKIE)
    assert caught.value.code is ErrorCode.UNKNOWN
    assert caught.value.detail == "captcha_unsolvable"


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("invalid_api_key", ErrorCode.BAD_API_KEY),
        ("key_disabled", ErrorCode.BAD_API_KEY),
        ("key_expired", ErrorCode.BAD_API_KEY),
        ("service_paused", ErrorCode.BAD_API_KEY),
        ("insufficient_balance", ErrorCode.NO_CREDIT),
    ],
)
def test_a_terminal_code_becomes_a_typed_error(raw: str, code: ErrorCode) -> None:
    session = FakeSession(answers(refused(raw)))

    with pytest.raises(AppError) as caught:
        client(session).solve(COOKIE)
    assert caught.value.code is code
    assert caught.value.detail == raw
    assert is_terminal(caught.value)


def test_a_terminal_code_is_read_whole_not_as_a_substring() -> None:
    """`invalid_api_key_format` is its own code, not the terminal one."""
    session = FakeSession(answers(refused("invalid_api_key_format")))

    with pytest.raises(AppError) as caught:
        client(session).solve(COOKIE)
    assert caught.value.code is ErrorCode.UNKNOWN
    assert not is_terminal(caught.value)


def test_a_terminal_code_in_the_message_field_is_still_seen() -> None:
    refusal = FakeResponse(payload={"success": False, "message": "key_expired"})
    session = FakeSession(answers(refusal))

    with pytest.raises(AppError) as caught:
        client(session).solve(COOKIE)
    assert caught.value.code is ErrorCode.BAD_API_KEY


@pytest.mark.parametrize("raw", ["Insufficient balance", "INSUFFICIENT_BALANCE"])
def test_a_terminal_code_is_read_whatever_its_case_and_spacing(raw: str) -> None:
    """The zero-balance answer shape has never been seen (spec 15)."""
    session = FakeSession(answers(refused(raw)))

    with pytest.raises(AppError) as caught:
        client(session).solve(COOKIE)
    assert caught.value.code is ErrorCode.NO_CREDIT


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_solve_call_is_a_bad_key(status: int) -> None:
    session = FakeSession({CREATE_URL: FakeResponse(status_code=status, payload={"error": "no"})})

    with pytest.raises(AppError) as caught:
        client(session).solve(COOKIE)
    assert caught.value.code is ErrorCode.BAD_API_KEY


def test_a_dead_network_during_a_solve_is_no_internet() -> None:
    session = FakeSession({CREATE_URL: OSError("connection refused")})

    with pytest.raises(AppError) as caught:
        client(session).solve(COOKIE)
    assert caught.value.code is ErrorCode.NO_INTERNET
    assert not is_terminal(caught.value)


def test_the_cookie_never_appears_in_the_error_text() -> None:
    session = FakeSession(answers(refused(f"bad cookie {COOKIE}")))

    with pytest.raises(AppError) as caught:
        client(session).solve(COOKIE)
    assert COOKIE not in str(caught.value)


# --- solve_account ---------------------------------------------------------


def test_a_captcha_solve_is_named_solved() -> None:
    session = FakeSession(answers(solved(total_ms=1500, solve_ms=700)))

    outcome = run.solve_account(client(session), ACCOUNT, sleep=nothing)

    assert outcome.result is run.Result.SOLVED
    assert outcome.account_id == "4821"


def test_a_pass_with_no_captcha_is_named_joined() -> None:
    session = FakeSession(answers(solved(total_ms=900, solve_ms=0)))

    assert run.solve_account(client(session), ACCOUNT, sleep=nothing).result is run.Result.JOINED


def test_an_account_that_keeps_failing_is_named_failed_with_its_code() -> None:
    session = FakeSession(answers(refused("captcha_unsolvable")))

    outcome = run.solve_account(client(session), ACCOUNT, sleep=nothing)

    assert outcome.result is run.Result.FAILED
    assert outcome.detail == "captcha_unsolvable"


def test_the_account_is_tried_three_times_before_it_is_called_failed() -> None:
    session = FakeSession(answers(refused("captcha_unsolvable")))

    run.solve_account(client(session), ACCOUNT, sleep=nothing)

    assert session.urls.count(CREATE_URL) == run.MAX_ATTEMPTS == 3


def test_a_later_attempt_can_still_succeed() -> None:
    session = FakeSession(answers(refused("captcha_unsolvable"), solved(solve_ms=5)))

    assert run.solve_account(client(session), ACCOUNT, sleep=nothing).result is run.Result.SOLVED


@pytest.mark.parametrize("raw", sorted(HOPELESS_CODES))
def test_an_account_a_retry_cannot_help_is_tried_once(raw: str) -> None:
    """Today's `src/roblox.py` gives these one attempt too; three would cost time."""
    session = FakeSession(answers(refused(raw)))

    outcome = run.solve_account(client(session), ACCOUNT, sleep=nothing)

    assert outcome.result is run.Result.FAILED
    assert outcome.detail == raw
    assert session.urls.count(CREATE_URL) == 1


def test_a_terminal_error_is_raised_at_once_and_not_retried() -> None:
    session = FakeSession(answers(refused("insufficient_balance")))

    with pytest.raises(AppError) as caught:
        run.solve_account(client(session), ACCOUNT, sleep=nothing)

    assert caught.value.code is ErrorCode.NO_CREDIT
    assert session.urls.count(CREATE_URL) == 1


def test_the_outcome_never_carries_the_cookie() -> None:
    session = FakeSession(answers(refused("cookie_dead")))

    outcome = run.solve_account(client(session), ACCOUNT, sleep=nothing)

    assert COOKIE not in outcome.detail
    assert COOKIE not in repr(outcome)


def test_the_log_line_holds_the_account_id_and_the_code_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = FakeSession(answers(refused("cookie_dead")))

    with caplog.at_level("INFO"):
        run.solve_account(client(session), ACCOUNT, sleep=nothing)

    written = "\n".join(record.getMessage() for record in caplog.records)
    assert "4821" in written
    assert "cookie_dead" in written
    assert COOKIE not in written
    assert API_KEY not in written


@pytest.mark.parametrize("written", ["print(", "sys.stdout", "sys.stderr"])
def test_the_engine_never_writes_to_the_console(written: str) -> None:
    """A windowed build has no console, so one write is a crash (spec 2)."""
    for path in PACKAGE.rglob("*.py"):
        if path.name == "logging_setup.py":  # owns the excepthook, so it may name sys
            continue
        assert written not in path.read_text(encoding="utf-8"), path
