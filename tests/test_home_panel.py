"""§4.2, §5.6 and §5.7: the control room's left panel and live table, without a window."""
from __future__ import annotations

from dataclasses import replace

import pytest

from farmsync_solver.engine.snapshot import (
    IDLE,
    AccountRow,
    Headline,
    Result,
    RunSnapshot,
    RunState,
)
from farmsync_solver.errors import ErrorCode
from farmsync_solver.ui import home, messages


def _row(username: str, outcome: Result, at: float, detail: str = "") -> AccountRow:
    return AccountRow(username=username, outcome=outcome, detail=detail, at=at)


# --- the button (spec 5.7) --------------------------------------------------


def test_idle_offers_start_and_follows_the_key_check() -> None:
    assert home.panel_of(IDLE, can_start=True).button == messages.HOME_START
    assert home.panel_of(IDLE, can_start=True).button_enabled is True
    assert home.panel_of(IDLE, can_start=False).button_enabled is False


@pytest.mark.parametrize(
    "state", [RunState.DISCOVERING, RunState.SOLVING, RunState.RESTING]
)
def test_a_going_run_offers_stop(state: RunState) -> None:
    panel = home.panel_of(replace(IDLE, state=state), can_start=False)

    assert panel.button == messages.HOME_STOP
    assert panel.button_enabled is True


def test_stopping_reads_stopping_and_takes_no_press() -> None:
    panel = home.panel_of(replace(IDLE, state=RunState.STOPPING), can_start=True)

    assert panel.button == messages.HOME_STOPPING
    assert panel.button_enabled is False


# --- the progress indicator (spec 4.2) --------------------------------------


def test_discovering_spins_because_there_is_nothing_to_count() -> None:
    panel = home.panel_of(replace(IDLE, state=RunState.DISCOVERING), can_start=False)

    assert panel.spinner is True
    assert panel.fraction is None


def test_solving_fills_a_bar_over_the_accounts_of_this_round() -> None:
    solving = replace(IDLE, state=RunState.SOLVING, done=87, total=132)

    assert home.panel_of(solving, can_start=False).fraction == pytest.approx(87 / 132)
    assert home.panel_of(solving, can_start=False).spinner is False


def test_solving_before_the_first_count_shows_no_bar() -> None:
    solving = replace(IDLE, state=RunState.SOLVING, done=0, total=0)

    assert home.panel_of(solving, can_start=False).fraction is None


def test_resting_shows_the_countdown_and_neither_indicator() -> None:
    resting = replace(IDLE, state=RunState.RESTING, headline=Headline.RESTING, seconds_left=9)
    panel = home.panel_of(resting, can_start=False)

    assert panel.message == "Next round in 9s"
    assert panel.spinner is False
    assert panel.fraction is None


# --- the moving line, built here from what the snapshot counts (ADR 0005) ----


def test_solving_counts_the_accounts_of_this_round() -> None:
    solving = replace(IDLE, state=RunState.SOLVING, done=87, total=132)

    assert home.panel_of(solving, can_start=False).message == "87 of 132"


def test_waiting_says_how_long_it_has_been_and_when_the_next_knock_lands() -> None:
    """ADR 0003's Waiting line: the news first, then the heartbeat."""
    waiting = replace(IDLE, state=RunState.WAITING, seconds_waited=125.0, seconds_left=17)

    assert home.panel_of(waiting, can_start=False).message == (
        "Waiting for 2m 5s. Checking again in 17s"
    )


def test_a_knock_that_is_out_says_so_instead_of_counting_down() -> None:
    """The one moment something is happening, and the one most likely to hang."""
    knocking = replace(IDLE, state=RunState.WAITING, seconds_waited=125.0, seconds_left=None)

    assert home.panel_of(knocking, can_start=False).message.endswith("Checking now…")


@pytest.mark.parametrize("state", [RunState.IDLE, RunState.DISCOVERING, RunState.STOPPING])
def test_the_states_with_nothing_to_count_say_nothing(state: RunState) -> None:
    """A stale countdown left over from the last round would read as a live one."""
    left_over = replace(IDLE, state=state, seconds_left=9, seconds_waited=60.0)

    assert home.panel_of(left_over, can_start=False).message == ""


# --- the numbers and the credit ---------------------------------------------


def test_the_four_numbers_are_ready_to_display() -> None:
    running = replace(IDLE, state=RunState.SOLVING, round_number=3, joined=1234, solved=7, failed=38)
    panel = home.panel_of(running, can_start=False)

    assert (panel.round_number, panel.joined, panel.solved, panel.failed) == (
        "3",
        "1,234",
        "7",
        "38",
    )


def test_a_run_credit_read_becomes_the_header_and_turns_orange_when_low() -> None:
    running = replace(
        IDLE, state=RunState.SOLVING, round_number=1, estimated_solves=999, credit_left=1.5
    )
    panel = home.panel_of(running, can_start=False)

    assert panel.credit == "999 captchas left ($1.50)"
    assert panel.low is True


def test_before_any_run_the_panel_leaves_the_open_time_header_alone() -> None:
    assert home.panel_of(IDLE, can_start=True).credit == ""


def test_an_app_that_has_never_run_says_so() -> None:
    assert home.panel_of(IDLE, can_start=True).headline == messages.HOME_NO_RUNS


# --- how a stopped run explains itself (spec 5.6) ---------------------------


def test_an_engine_bug_is_a_plain_headline_with_the_raw_text_behind_details() -> None:
    crashed = replace(IDLE, headline=Headline.CRASHED, detail="KeyError: 'accounts'")
    panel = home.panel_of(crashed, can_start=True)

    assert panel.headline == messages.headline(Headline.CRASHED)
    assert panel.details == "KeyError: 'accounts'"
    assert panel.message == ""


def test_a_run_that_ended_on_a_fault_reads_as_that_fault() -> None:
    """The code is the headline; the sentence for it is the error table's."""
    refused = replace(IDLE, headline=ErrorCode.BAD_API_KEY, detail="invalid_api_key")

    assert home.panel_of(refused, can_start=True).headline == messages.for_code(
        ErrorCode.BAD_API_KEY
    )


def test_a_clean_stop_offers_no_details_link() -> None:
    stopped = replace(IDLE, headline=Headline.STOPPED, round_number=2)

    assert home.panel_of(stopped, can_start=True).details == ""


@pytest.mark.parametrize("code", ["INTERNAL_ERROR", "CLASSIFICATION_ERROR", "UPSTREAM_TIMEOUT"])
def test_no_dibycap_code_ever_reaches_the_headline(code: str) -> None:
    solving = replace(IDLE, state=RunState.SOLVING, headline=Headline.SOLVING)
    rows = [_row("ada", Result.FAILED, at=0.0, detail=code)]

    assert code not in home.panel_of(solving, can_start=False).headline
    assert home.table_rows(rows, failed_only=False, now=0.0)[0]["detail"] == code


# --- the live table ---------------------------------------------------------


def test_the_table_is_newest_first() -> None:
    rows = [
        _row("first", Result.JOINED, at=100.0),
        _row("second", Result.SOLVED, at=101.0),
        _row("third", Result.FAILED, at=102.0),
    ]

    shown = home.table_rows(rows, failed_only=False, now=102.0)

    assert [row["account"] for row in shown] == ["third", "second", "first"]


def test_the_switch_shows_only_the_ones_that_failed() -> None:
    rows = [
        _row("ada", Result.JOINED, at=100.0),
        _row("bob", Result.FAILED, at=101.0, detail="INTERNAL_ERROR"),
    ]

    shown = home.table_rows(rows, failed_only=True, now=101.0)

    assert [row["account"] for row in shown] == ["bob"]


def test_a_failure_is_orange_and_reads_as_could_not_check() -> None:
    shown = home.table_rows([_row("bob", Result.FAILED, at=0.0)], failed_only=False, now=0.0)

    assert shown[0]["status"] == messages.HOME_FAILED
    assert shown[0]["colour"] == "orange"


def test_the_other_two_outcomes_read_in_the_words_of_the_spec() -> None:
    rows = [_row("ada", Result.JOINED, at=0.0), _row("eve", Result.SOLVED, at=1.0)]

    shown = home.table_rows(rows, failed_only=False, now=1.0)

    assert [row["status"] for row in shown] == ["Captcha solved", "Joined"]


def test_elapsed_counts_from_when_the_account_landed() -> None:
    shown = home.table_rows([_row("ada", Result.JOINED, at=100.0)], failed_only=False, now=175.0)

    assert shown[0]["elapsed"] == "1m 15s"


def test_every_row_has_its_own_key_so_the_table_can_track_it() -> None:
    rows = [_row("ada", Result.JOINED, at=100.0), _row("ada", Result.FAILED, at=101.0)]

    keys = [row["key"] for row in home.table_rows(rows, failed_only=False, now=101.0)]

    assert len(set(keys)) == 2


def test_no_row_ever_names_a_device() -> None:
    rows = [_row("ada", Result.JOINED, at=0.0, detail="")]

    assert set(home.table_rows(rows, failed_only=False, now=0.0)[0]) == {
        "key",
        "status",
        "colour",
        "account",
        "detail",
        "elapsed",
    }


# --- the seam itself --------------------------------------------------------


def test_the_panel_reads_a_snapshot_and_nothing_else() -> None:
    """Spec 9.2: snapshot in, screen out. No event-kind dispatch anywhere."""
    assert home.panel_of(RunSnapshot(), can_start=True) == home.panel_of(IDLE, can_start=True)
