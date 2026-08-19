"""The Home screen: credit header, key re-check, Start, and the control room.

Spec 4.2 and 7. On every open the app makes one cheap cookie-free `/balance`
call. It is both the credit read and a key re-check: a key that died since the
last run becomes a red line before the run, not a mystery in the middle of one.

Pressing Start runs the engine, and the screen becomes the control room of spec
4.2: a fixed left panel holding everything that is not a table row, and one live
table of this round's accounts, newest first.

Three pure functions hold the whole of what the screen shows, so all of it is
tested without a window:

- `read_credit` — one re-check, as header text and a red line.
- `panel_of` — one `RunSnapshot`, as every word and bar in the left panel.
- `table_rows` — the finished accounts, as the rows of the table.
- `update_bar` — the update the startup check found, as the bar across the top.

`build` is the thin screen on top of them. Spec 4.4 shapes it: every control is
created once, and the 5 Hz refresh only changes text, colour and visibility. A
refresh that rebuilt the tree would replace the Start button between press and
release, and the click would vanish with no error and no log line.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from nicegui import app as native_app
from nicegui import run, ui
from nicegui.events import KeyEventArguments

from .. import credit, engine, keys, updater
from ..engine.snapshot import AccountRow, RunSnapshot, RunState
from ..errors import AppError, ErrorCode
from ..keys import KeyCheck
from ..updater import Update  # the type only: every call goes through `updater`
from . import messages

LOW_COLOUR = "text-orange-600"
NORMAL_COLOUR = "text-gray-900"
EMPTY: dict[str, Any] = {"estimated_solves": 0}

# 5 Hz. Fast enough that the rest countdown ticks smoothly, and the rate spec 4.4
# names as the one that broke the prototype — so the build-once rule is proved by
# the app's own refresh, not by a test-only speed.
REFRESH_SECONDS = 0.2

# The badge colour for each outcome. Failures are **orange, not red** (spec 4.2):
# 28.6% of attempts fail, so a failure is routine, not an alarm.
BADGE_COLOUR: dict[str, str] = {"joined": "green", "solved": "blue", "failed": "orange"}

TABLE_COLUMNS = [
    {"name": "status", "label": messages.TABLE_STATUS, "field": "status", "align": "left"},
    {"name": "account", "label": messages.TABLE_ACCOUNT, "field": "account", "align": "left"},
    {"name": "detail", "label": messages.TABLE_DETAIL, "field": "detail", "align": "left"},
    {"name": "elapsed", "label": messages.TABLE_ELAPSED, "field": "elapsed", "align": "right"},
]

# The status cell is a badge rather than a word, so the colour rule of spec 4.2 is
# visible at a glance. Quasar draws it; the colour comes from the row.
STATUS_BADGE = """
<q-td :props="props">
  <q-badge :color="props.row.colour" :label="props.value" outline />
</q-td>
"""

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Credit:
    """What one re-check tells the screen to show."""

    header: str
    low: bool
    error: str = ""

    @property
    def can_start(self) -> bool:
        """Low credit still starts; a failed check does not (spec 5.7)."""
        return not self.error

    @property
    def check_note(self) -> str:
        """How the diagnostics header reads this answer (spec 8.4)."""
        return self.error or messages.DIAGNOSTICS_KEY_OK


@dataclass(frozen=True)
class Panel:
    """What the left panel shows for one snapshot. Every field is ready to display.

    `credit` is empty when the run has not read a balance yet, which means "leave
    the header the open-time re-check wrote". `details` is empty unless a run
    ended on a fault, and holds its raw text — the headline never does (spec 4.2).
    """

    button: str
    button_enabled: bool
    headline: str
    message: str
    details: str
    spinner: bool
    fraction: float | None
    round_number: str
    joined: str
    solved: str
    failed: str
    credit: str
    low: bool


class UpdateStage(Enum):
    """Where an offered update has got to. One name, not three booleans."""

    READY = "ready"  # waiting for the button
    LOCKED = "locked"  # a run is going, and an install would kill it
    DOWNLOADING = "downloading"
    FAILED = "failed"


# The sentence under the headline. READY has nothing to add, so it says nothing.
UPDATE_NOTE: dict[UpdateStage, str] = {
    UpdateStage.READY: "",
    UpdateStage.LOCKED: messages.UPDATE_LOCKED,
    UpdateStage.DOWNLOADING: messages.UPDATE_DOWNLOADING,
    UpdateStage.FAILED: messages.UPDATE_FAILED,
}

# A failed download may be tried again; the other two dead stages may not.
PRESSABLE = frozenset({UpdateStage.READY, UpdateStage.FAILED})


@dataclass(frozen=True)
class UpdateBar:
    """What the bar across the top of Home shows (spec 4.2, 12).

    Not a dialog, and it never blocks: it says a version is ready and offers one
    button. An update is refused mid-run — an install during a run would kill the
    run — so the button is dead while a run is going and the note says why.
    """

    visible: bool
    headline: str
    note: str
    button_enabled: bool
    progress_visible: bool
    fraction: float


def update_bar(update: Update | None, stage: UpdateStage, fraction: float = 0.0) -> UpdateBar:
    """One found update at one stage, as every word and bar in the strip."""
    return UpdateBar(
        visible=update is not None,
        headline=messages.update_ready(update.version) if update else "",
        note=UPDATE_NOTE[stage],
        button_enabled=stage in PRESSABLE,
        progress_visible=stage is UpdateStage.DOWNLOADING,
        fraction=fraction,
    )


_last_credit: Credit | None = None


def forget_credit() -> None:
    """Drop the remembered re-check, so a stale answer cannot outlive the keys."""
    global _last_credit
    _last_credit = None


def last_credit() -> Credit | None:
    """What the last re-check answered, or None before the first one.

    Kept for the diagnostics header of spec 8.4: Settings must say whether the
    key works and how much credit is left, and re-checking on that screen would
    make pressing a Copy button reach the network.
    """
    return _last_credit


def read_credit(api_key: str, check_key: KeyCheck | None = None) -> Credit:
    """Re-check the key and turn the answer into header text and a red line."""
    global _last_credit

    # Looked up now, not in the signature, so a caller can swap it.
    check_key = check_key or keys.check_api_key

    try:
        balance = check_key(api_key)
    except AppError as error:
        return _remember(_refused(error.code))
    except Exception as error:  # a surprise must not take the window down
        return _remember(_refused(AppError.from_exception(error).code))

    return _remember(Credit(header=messages.credit_header(balance), low=credit.is_low(balance)))


def _remember(answer: Credit) -> Credit:
    """Keep the answer for the diagnostics header, and hand it back."""
    global _last_credit
    _last_credit = answer
    return answer


def panel_of(snapshot: RunSnapshot, can_start: bool) -> Panel:
    """One snapshot, as everything the left panel says.

    The progress indicator follows the run state (spec 4.2): a spinner while
    there is nothing to count, a bar while accounts are being worked through, and
    neither during the rest, whose countdown is words already.
    """
    idle = snapshot.state is RunState.IDLE
    return Panel(
        button=_button_text(snapshot.state),
        button_enabled=can_start if idle else snapshot.state is not RunState.STOPPING,
        headline=snapshot.headline or messages.HOME_NO_RUNS,
        # An Idle snapshot's message is the raw text of whatever ended the run, so
        # it belongs behind Details, never on the panel as a sentence.
        message="" if idle else snapshot.message,
        details=snapshot.message if idle else "",
        spinner=snapshot.state in (RunState.DISCOVERING, RunState.STOPPING),
        fraction=_fraction(snapshot),
        round_number=f"{snapshot.round_number:,}",
        joined=f"{snapshot.joined:,}",
        solved=f"{snapshot.solved:,}",
        failed=f"{snapshot.failed:,}",
        credit=_credit_line(snapshot),
        low=snapshot.estimated_solves < credit.LOW_SOLVES,
    )


def table_rows(
    rows: list[AccountRow], failed_only: bool, now: float | None = None
) -> list[dict[str, Any]]:
    """This round's accounts as table rows: newest first, and filtered by the switch.

    The one switch of spec 4.2 is the only filter: with ~38 failures in a
    132-account round, "show only the ones that failed" is the whole need.
    """
    moment = time.time() if now is None else now
    wanted = [row for row in rows if not failed_only or row.outcome.value == "failed"]
    return [
        {
            "key": f"{row.at:.6f}-{row.username}",
            "status": messages.outcome_word(row.outcome.value),
            "colour": BADGE_COLOUR.get(row.outcome.value, "grey"),
            "account": row.username,
            "detail": row.detail,
            "elapsed": messages.elapsed(moment - row.at),
        }
        for row in reversed(wanted)
    ]


def should_confirm_close(state: RunState) -> bool:
    """Spec 5.3: a run in progress is asked about before the window closes."""
    return state is not RunState.IDLE


# The Home screen this window is showing, or None while another screen is up.
# The close question arrives over HTTP, outside any screen, and this is how it
# finds the one dialog it must open.
_showing: "_Screen | None" = None


def close_or_ask() -> bool:
    """Spec 5.3: close the window, or put the close question on screen.

    True closes. False means the question is up instead, and the X must be
    refused. With Home off the page there is no question and no dialog to put
    it in, so the window goes.
    """
    return True if _showing is None else _showing.close_or_ask()


def forget_screen() -> None:
    """Home has left the page. Called before another screen is drawn over it."""
    global _showing
    _showing = None


def build(
    api_key: str,
    farm_token: str,
    speed_percent: int,
    on_settings: Callable[[], None],
    run_engine: engine.Engine | None = None,
) -> None:
    """Draw the screen, start the background re-check, and wire the controls.

    Takes plain values, not the config: `Engine.start` takes the same three for
    the same reason (spec 9.2), and the screen reads nothing else from the file.
    """
    global _showing
    worker = run_engine if run_engine is not None else engine.current()
    state = _Screen(worker, api_key, farm_token, speed_percent)
    _showing = state

    _update_strip(state)

    # The gear sits on its own row so it stays top-right of the whole screen,
    # not inside the panel below it.
    with ui.row().classes("w-full justify-end p-2"):
        gear = ui.button(icon="settings").props("flat round").mark("settings-gear")
        with gear:  # inside the button, or the tooltip covers the whole row
            ui.tooltip(messages.HOME_SETTINGS)
        gear.on("click", on_settings)

    with ui.row().classes("w-full flex-nowrap items-start gap-6 px-6"):
        _left_panel(state)
        _live_table(state)

    state.closing = _close_dialog(state)
    ui.keyboard(on_key=state.on_key)

    # once=True: one call on open, not a poll. The live credit figure during a run
    # comes from the snapshot instead (spec 7).
    ui.timer(0, state.recheck, once=True)
    # The silent check of spec 12. once=True, and it shows nothing at all when
    # the app is already the newest version.
    ui.timer(0, state.look_for_update, once=True)
    ui.timer(REFRESH_SECONDS, state.refresh)


class _Screen:
    """The controls, the rows, and the one refresh that writes into them.

    A class rather than a nest of closures because the refresh has real state:
    which round the table is showing, and what the open-time re-check answered.
    Nothing here builds a control twice — `build` makes them, this fills them in.
    """

    # Built by `_left_panel` and `_live_table`, once each. Named here so the
    # refresh below reads as one list of things that already exist.
    credit_header: ui.label
    error_line: ui.label
    button: ui.button
    tooltip: ui.tooltip
    headline: ui.label
    message: ui.label
    spinner: ui.spinner
    bar: ui.linear_progress
    round_number: ui.label
    joined: ui.label
    solved: ui.label
    failed: ui.label
    details: ui.expansion
    details_text: ui.label
    failed_only: ui.switch
    table: ui.table
    update_row: ui.row
    update_headline: ui.label
    update_note: ui.label
    update_button: ui.button
    update_progress: ui.linear_progress

    def __init__(
        self, worker: engine.Engine, api_key: str, farm_token: str, speed_percent: int
    ) -> None:
        self._worker = worker
        self._api_key = api_key
        self._farm_token = farm_token
        self._speed_percent = speed_percent
        self._can_start = False
        self._rows: list[AccountRow] = []
        self._round_shown = 0
        self._update: Update | None = updater.pending()
        self._downloading = False
        self._download_failed = False
        # Written from the download thread, read by the 5 Hz refresh. A float is
        # the whole of the shared state, so no lock buys anything here.
        self._fraction = 0.0
        self.closing: ui.dialog | None = None
        self._close_answered = False

    # --- the open-time re-check -------------------------------------------

    async def recheck(self) -> None:
        """The one cookie-free `/balance` of spec 4.2, in a worker thread.

        On the event loop a blocking network call would freeze the window it is
        supposed to be filling in.
        """
        answer = await run.io_bound(read_credit, self._api_key)
        if answer is None:  # NiceGUI answers None when it cancels the call
            return
        self._can_start = answer.can_start
        # Set here as well as on the next tick: a good key must not leave the
        # button dead for the 200 ms until the refresh comes round.
        self.button.set_enabled(answer.can_start)
        self._show_credit(answer.header, answer.low)
        self.error_line.set_text(answer.error)
        self.tooltip.set_text(answer.error)
        self.tooltip.set_visibility(bool(answer.error))  # no blank bubble when all is well

    # --- the update bar ---------------------------------------------------

    async def look_for_update(self) -> None:
        """The startup check, in a worker thread. Silent when nothing is found.

        Skipped during a run: Home is rebuilt on every hop back from Settings, so
        without this a check would run in the middle of one (spec 12).
        """
        if self._running():
            return

        answer = await run.io_bound(updater.check)
        if answer is None or answer.update is None:  # None when NiceGUI cancels
            return
        self._update = answer.update
        self._show_update()

    async def press_update(self) -> None:
        """Download, check, hand over. Any failure leaves this version running."""
        update = self._update
        if update is None or self._running():
            return

        self._downloading, self._download_failed, self._fraction = True, False, 0.0
        self._show_update()

        setup = await run.io_bound(updater.download, update, on_progress=self._downloaded)
        self._downloading = False

        if setup is None:
            self._download_failed = True
            self._show_update()
            return

        # Asked again, because a download is minutes long and Start was live for
        # every one of them. Installing now would kill the run that just began.
        if self._running():
            self._show_update()
            return

        self._hand_over(setup, update.version)

    def _hand_over(self, setup: Path, version: str) -> None:
        """Spec 12: the app exits itself, and the installer starts as it goes.

        Hung on the shutdown rather than run here, so the window is already gone
        when Setup starts replacing the folder the app runs from.
        """
        native_app.on_shutdown(lambda: updater.install(setup))
        _log.info("update handed over version=%s", version)
        native_app.shutdown()

    def _downloaded(self, fraction: float) -> None:
        """Called from the download thread. The refresh paints it."""
        self._fraction = fraction

    def _running(self) -> bool:
        return self._worker.snapshot().state is not RunState.IDLE

    def _stage(self) -> UpdateStage:
        """Which of the four stages the offered update is at."""
        if self._downloading:
            return UpdateStage.DOWNLOADING
        if self._download_failed:
            return UpdateStage.FAILED
        return UpdateStage.LOCKED if self._running() else UpdateStage.READY

    def _show_update(self) -> None:
        bar = update_bar(self._update, self._stage(), self._fraction)
        self.update_row.set_visibility(bar.visible)
        self.update_headline.set_text(bar.headline)
        self.update_note.set_text(bar.note)
        self.update_note.set_visibility(bool(bar.note))
        self.update_button.set_enabled(bar.button_enabled)
        self.update_progress.set_visibility(bar.progress_visible)
        self.update_progress.set_value(bar.fraction)

    # --- the button --------------------------------------------------------

    def press(self) -> None:
        """One button, both jobs (spec 4.2). Idle starts a run; a run is stopped."""
        if self._worker.snapshot().state is RunState.IDLE:
            self._rows.clear()  # a fresh start shows a fresh table (spec 5.2)
            self._round_shown = 0
            self._worker.start(self._api_key, self._farm_token, self._speed_percent)
            return
        self._worker.stop()

    def on_key(self, event: KeyEventArguments) -> None:
        """Ctrl+W is the close gesture the window itself does not handle."""
        if event.action.keydown and event.modifiers.ctrl and event.key.name == "w":
            self.request_close()

    def request_close(self) -> None:
        """Spec 5.3: a run is asked about; an idle app just closes."""
        if self.close_or_ask():
            native_app.shutdown()

    def close_or_ask(self) -> bool:
        """Spec 5.3: True closes, False puts the close question on screen instead.

        An answer already given holds. Closing the window raises the question a
        second time, and by then the polite stop has left the run Stopping, not
        Idle — asking again would trap the window inside its own dialog. A
        dialog that is no longer on the page cannot ask anything either, and a
        window nobody can close is the worse of the two failures.
        """
        if self._close_answered or self.closing is None or self.closing.is_deleted:
            return True
        if not should_confirm_close(self._worker.snapshot().state):
            return True
        self.closing.open()
        return False

    def stop_and_close(self) -> None:
        """The polite stop of spec 5.2, then the window goes."""
        self._close_answered = True
        self._worker.stop()
        native_app.shutdown()

    # --- the refresh -------------------------------------------------------

    def refresh(self) -> None:
        """Read the engine and write the answer into controls that already exist."""
        snapshot = self._worker.snapshot()
        self._collect(snapshot)
        self._show_panel(panel_of(snapshot, self._can_start))
        self._show_table()
        self._show_update()

    def _collect(self, snapshot: RunSnapshot) -> None:
        """Keep this round's finished accounts, and drop the round before it."""
        if snapshot.round_number != self._round_shown:
            self._round_shown = snapshot.round_number
            self._rows.clear()
        self._rows.extend(self._worker.take_new_rows())

    def _show_panel(self, panel: Panel) -> None:
        self.button.set_text(panel.button)
        self.button.set_enabled(panel.button_enabled)
        self.headline.set_text(panel.headline)
        self.message.set_text(panel.message)
        self.details.set_visibility(bool(panel.details))
        self.details_text.set_text(panel.details)
        self.spinner.set_visibility(panel.spinner)
        self.bar.set_visibility(panel.fraction is not None)
        self.bar.set_value(panel.fraction or 0.0)
        self.round_number.set_text(panel.round_number)
        self.joined.set_text(panel.joined)
        self.solved.set_text(panel.solved)
        self.failed.set_text(panel.failed)
        if panel.credit:
            self._show_credit(panel.credit, panel.low)

    def _show_table(self) -> None:
        # Only when it really changed. The elapsed column moves about once a
        # second, so a blind write here would send the whole table five times a
        # second for nothing.
        wanted = table_rows(self._rows, bool(self.failed_only.value))
        if wanted == self.table.rows:
            return
        self.table.rows = wanted
        self.table.update()

    def _show_credit(self, header: str, low: bool) -> None:
        self.credit_header.set_text(header)
        self.credit_header.classes(
            add=LOW_COLOUR if low else NORMAL_COLOUR,
            remove=NORMAL_COLOUR if low else LOW_COLOUR,
        )


def _update_strip(state: _Screen) -> None:
    """The bar across the top (spec 4.2), built once and hidden until it is needed."""
    with ui.row().classes(
        "w-full items-center gap-3 bg-blue-50 px-6 py-3"
    ).mark("update-bar") as row:
        state.update_row = row
        with ui.column().classes("grow gap-0 min-w-0"):
            state.update_headline = ui.label().classes("text-sm font-semibold")
            state.update_note = ui.label().classes("text-xs text-gray-600")
            state.update_note.set_visibility(False)
        state.update_progress = ui.linear_progress(value=0.0, show_value=False).classes("w-40")
        state.update_progress.set_visibility(False)
        state.update_button = ui.button(messages.UPDATE_NOW).mark("update-button")
        state.update_button.on("click", state.press_update)
    row.set_visibility(False)


def _left_panel(state: _Screen) -> None:
    """Everything that is not a table row (spec 4.2), in one fixed column."""
    with ui.column().classes("w-72 shrink-0 items-stretch gap-3 pb-6"):
        state.credit_header = (
            ui.label(messages.HOME_CHECKING).classes("text-xl font-bold").mark("credit-header")
        )
        state.error_line = ui.label().classes("text-sm text-red-600")

        # The tooltip hangs on the wrapper, not on the button: a disabled Quasar
        # button takes no pointer events, so a tooltip inside it would never show
        # in the one state spec 5.7 needs it for.
        with ui.element("div") as start_holder:
            state.button = (
                ui.button(messages.HOME_START)
                .props("size=xl")
                .classes("w-full")
                .mark("run-button")
            )
            state.button.disable()  # nothing runs until the re-check answers
            state.button.on("click", state.press)
        with start_holder:
            state.tooltip = ui.tooltip(messages.HOME_CHECKING).mark("start-tooltip")

        state.headline = (
            ui.label(messages.HOME_NO_RUNS)
            .classes("text-base font-semibold")
            .mark("run-headline")
        )
        state.message = ui.label().classes("text-sm text-gray-600").mark("run-message")

        with ui.row().classes("items-center gap-2 h-6"):
            state.spinner = ui.spinner(size="sm").mark("run-spinner")
            state.spinner.set_visibility(False)
        state.bar = ui.linear_progress(value=0.0, show_value=False).mark("run-bar")
        state.bar.set_visibility(False)

        state.round_number = _number_row(messages.HOME_ROUND, "run-round")
        state.joined = _number_row(messages.HOME_JOINED, "run-joined")
        state.solved = _number_row(messages.HOME_SOLVED, "run-solved")
        state.failed = _number_row(messages.HOME_FAILED, "run-failed", LOW_COLOUR)

        # A link, not a dialog: spec 5.6 keeps a failure readable whenever the
        # user comes back, and a popup raised while they were away is a wall.
        state.details = ui.expansion(messages.HOME_DETAILS).props("dense").mark("run-details")
        with state.details:
            state.details_text = ui.label().classes("text-xs text-gray-500 break-all")
        state.details.set_visibility(False)


def _live_table(state: _Screen) -> None:
    """The rest of the window: one switch, then this round's accounts."""
    with ui.column().classes("grow items-stretch gap-2 pb-6 min-w-0"):
        state.failed_only = ui.switch(messages.HOME_FAILED_ONLY).mark("failed-only")
        state.table = (
            ui.table(columns=TABLE_COLUMNS, rows=[], row_key="key")
            .classes("w-full")
            .mark("run-table")
        )
        state.table.add_slot("body-cell-status", STATUS_BADGE)


def _close_dialog(state: _Screen) -> ui.dialog:
    """Spec 5.3's question, built once beside the screen it belongs to."""
    with ui.dialog().mark("closing-dialog") as dialog, ui.card().classes("items-stretch gap-3"):
        ui.label(messages.CLOSE_QUESTION).classes("text-lg font-semibold")
        with ui.row().classes("justify-end gap-2"):
            ui.button(messages.CLOSE_NO).props("flat").on("click", dialog.close)
            ui.button(messages.CLOSE_YES).props("color=negative").on("click", state.stop_and_close)
    return dialog


def _number_row(label: str, marker: str, colour: str = NORMAL_COLOUR) -> ui.label:
    """One of the four counters: its name on the left, its figure on the right."""
    with ui.row().classes("w-full justify-between items-baseline"):
        ui.label(label).classes("text-sm text-gray-600")
        return ui.label("0").classes(f"text-sm font-semibold {colour}").mark(marker)


def _button_text(state: RunState) -> str:
    """Spec 5.7: Start when Idle, Stopping… while the last solves land, else Stop."""
    if state is RunState.IDLE:
        return messages.HOME_START
    if state is RunState.STOPPING:
        return messages.HOME_STOPPING
    return messages.HOME_STOP


def _fraction(snapshot: RunSnapshot) -> float | None:
    """How full the bar is, or `None` when there is nothing to count yet."""
    if snapshot.state is not RunState.SOLVING or snapshot.total <= 0:
        return None
    return min(1.0, snapshot.done / snapshot.total)


def _credit_line(snapshot: RunSnapshot) -> str:
    """The header text a run's own credit read gives, once it has made one."""
    if snapshot.round_number <= 0 and snapshot.estimated_solves <= 0:
        return ""
    return messages.credit_text(snapshot.estimated_solves, snapshot.credit_left)


def _refused(code: ErrorCode) -> Credit:
    """A refused check. Only "no credit" knows a figure, and that figure is 0."""
    _log.info("home re-check refused code=%s", code.value)
    out_of_credit = code is ErrorCode.NO_CREDIT
    return Credit(
        header=messages.credit_header(EMPTY) if out_of_credit else messages.CREDIT_UNKNOWN,
        low=out_of_credit,
        error=messages.for_code(code),
    )
