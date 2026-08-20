"""The stable error codes are part of the contract with the UI and the updater."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from farmsync_solver.errors import AppError, ErrorCode, Severity, is_terminal, is_waitable

PACKAGE = Path(__file__).resolve().parent.parent / "farmsync_solver"


def test_every_stable_code_exists() -> None:
    assert {code.value for code in ErrorCode} == {
        "BAD_API_KEY",
        "NO_CREDIT",
        "SERVICE_PAUSED",
        "BAD_FARM_TOKEN",
        "NO_INTERNET",
        "UNKNOWN",
    }


def test_code_name_matches_its_value() -> None:
    for code in ErrorCode:
        assert code.name == code.value


def test_app_error_carries_its_code() -> None:
    error = AppError(ErrorCode.NO_CREDIT, "balance is 0")
    assert error.code is ErrorCode.NO_CREDIT
    assert "NO_CREDIT" in str(error)
    assert isinstance(error, Exception)


def test_app_error_defaults_to_unknown() -> None:
    assert AppError.from_exception(ValueError("boom")).code is ErrorCode.UNKNOWN


def test_app_error_from_exception_keeps_an_app_error_as_is() -> None:
    original = AppError(ErrorCode.BAD_API_KEY, "rejected")
    assert AppError.from_exception(original) is original


def test_raising_an_app_error_is_catchable_by_code() -> None:
    with pytest.raises(AppError) as caught:
        raise AppError(ErrorCode.BAD_FARM_TOKEN, "401 from farmsync")
    assert caught.value.code is ErrorCode.BAD_FARM_TOKEN


# --- Severity --------------------------------------------------------------


def test_every_severity_exists() -> None:
    assert {level.value for level in Severity} == {
        "RETRY",
        "ACCOUNT_DONE",
        "WAIT_IT_OUT",
        "ENDS_RUN",
    }


def test_severity_name_matches_its_value() -> None:
    for level in Severity:
        assert level.name == level.value


def test_a_failure_nobody_named_is_worth_another_try() -> None:
    error = AppError(ErrorCode.UNKNOWN, "captcha_unsolvable")
    assert error.severity is Severity.RETRY
    assert not is_terminal(error)
    assert not is_waitable(error)


def test_the_client_names_the_severity() -> None:
    error = AppError(ErrorCode.NO_CREDIT, "balance is 0", severity=Severity.ENDS_RUN)
    assert is_terminal(error)
    assert not is_waitable(error)


def test_a_service_fault_is_waited_out_and_never_terminal() -> None:
    error = AppError(ErrorCode.SERVICE_PAUSED, "service_paused", severity=Severity.WAIT_IT_OUT)
    assert is_waitable(error)
    assert not is_terminal(error)


def test_an_account_that_is_done_ends_nothing_but_itself() -> None:
    error = AppError(ErrorCode.UNKNOWN, "cookie_dead", severity=Severity.ACCOUNT_DONE)
    assert not is_terminal(error)
    assert not is_waitable(error)


def test_a_wrapped_exception_is_only_worth_another_try() -> None:
    """`from_exception` is where an engine bug becomes an AppError, and a bug does
    not heal in a minute."""
    assert AppError.from_exception(TypeError("engine bug")).severity is Severity.RETRY


def test_no_run_ending_fault_is_ever_raised_without_a_severity() -> None:
    """The cost of the client naming it: a forgotten `severity=` reads as `RETRY`.

    These two codes are the ones that must end the run (ADR 0006), so a raise of
    either that leaves the severity implicit is the one mistake worth pinning.
    """
    must_end_the_run = {"BAD_API_KEY", "NO_CREDIT"}
    unnamed: list[str] = []

    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or getattr(node.func, "id", "") != "AppError":
                continue
            first = node.args[0] if node.args else None
            if not isinstance(first, ast.Attribute) or first.attr not in must_end_the_run:
                continue
            if not any(word.arg == "severity" for word in node.keywords):
                unnamed.append(f"{path.name}:{node.lineno} {first.attr}")

    assert unnamed == []
