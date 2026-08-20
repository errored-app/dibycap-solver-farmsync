r"""PROTOTYPE — throwaway. Three history screens, in the real app (issue #44).

Three variants of "what is on the history screen", drawn with the real theme
rules and reached from the real Home, switchable via `?variant=`, `?theme=`,
`?screen=` and `?data=`.

    uv run python -m scripts.prototype_history_screen

Run it as a module, not as a file: the project is not installed
(`package = false`), so only `-m` puts the repo root on the import path. It opens
a browser tab rather than the native window, so variants can be flipped and
screenshotted side by side.

Nothing here is production code. There is no `history.json`: the rows are made up
at import from a fixed seed, so two screenshots of the same variant are the same
picture. The record shape is #43's — `started_at`, `ended_at`, `ending`, `fault`,
`rounds`, `joined`, `solved`, `failed`, `speed_percent`, `price_per_1k` — and the
money is worked out on read, never stored.

    A  The ledger        one dense table, every fact in a column of its own
    B  The receipt       no table: a stack of run rows with the money on the right
    C  Summary first     a totals band, four columns, and the rest on click

The bar at the bottom turns five knobs: the variant, the theme, Home against the
history screen, the data (a full file, an empty one, a file written by a newer
version), and whether the page is held at the real window size. The frame is on
by default and matters: 900x640 is the whole window (`ui/app.py`), and a table
that only works maximised is not a table this app can have.

Home is the real Home, so the entry-point question is asked where it lives: each
variant puts its own control next to the gear, and pressing it comes here.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Callable

from nicegui import ui

from farmsync_solver import keys
from farmsync_solver.ui import home, theme, update_offer

PORT = 8124

WINDOW_WIDTH = 900
WINDOW_HEIGHT = 640

VARIANTS = ["A", "B", "C"]
VARIANT_NAMES = {"A": "The ledger", "B": "The receipt", "C": "Summary first"}
THEMES = ["modern", "handheld", "handheld-color", "console", "adventure"]
DATASETS = ["full", "empty", "newer"]
FLAT = "flat dense color=white no-caps"

DAY = 86_400.0
NOW = 1_787_230_000.0  # a fixed "now" (20 Aug 2026), so every date is stable


# --- the record, and a file full of them ------------------------------------


@dataclass(frozen=True)
class Run:
    """One row of `history.json`, exactly the fields #43 settled.

    No money field: the money is `solved * price_per_1k / 1000`, worked out on
    read. `price_per_1k` is `None` for a run that never read a balance, and that
    run has no money at all — not a money of zero.
    """

    started_at: float
    ended_at: float | None
    ending: str  # stopped | faulted | crashed
    fault: str | None
    rounds: int
    joined: int
    solved: int
    failed: int
    speed_percent: int
    price_per_1k: float | None

    @property
    def interrupted(self) -> bool:
        """The fourth ending, derived: nobody was alive to write one."""
        return self.ended_at is None

    @property
    def dollars(self) -> float | None:
        return None if self.price_per_1k is None else self.solved * self.price_per_1k / 1000

    @property
    def seconds(self) -> float | None:
        return None if self.ended_at is None else self.ended_at - self.started_at


def make_history() -> list[Run]:
    """A plausible file: 243 runs over four months, newest first.

    The shapes the ticket asks the columns to survive are all in here on purpose:
    a run of 58 seconds and a run of eight hours, three killed by a bad key at
    2am, one stopped after hours of waiting on a paused service, one crash, one
    with no end time, and one written before the first balance ever answered.
    """
    dice = random.Random(44)
    runs: list[Run] = []
    at = NOW - 122 * DAY

    while at < NOW - DAY:
        at += dice.uniform(0.2, 1.4) * DAY
        seconds = dice.choice(
            [dice.uniform(58, 240), dice.uniform(600, 5_400), dice.uniform(3 * 3600, 8 * 3600)]
        )
        rounds = max(1, int(seconds // 90))
        attempts = rounds * 132
        solved = int(attempts * dice.uniform(0.50, 0.60))
        failed = int(attempts * dice.uniform(0.24, 0.32))
        runs.append(
            Run(
                started_at=at,
                ended_at=at + seconds,
                ending="stopped",
                fault=None,
                rounds=rounds,
                joined=attempts - solved - failed,
                solved=solved,
                failed=failed,
                speed_percent=dice.choice([50, 75, 100, 100]),
                price_per_1k=1.50 if at < NOW - 40 * DAY else 1.20,
            )
        )

    # The ones that are not an ordinary day. Every one of them is a row the
    # columns have to read differently, and three of them cost about the same
    # money as each other on purpose.
    runs.append(_odd(NOW - 31 * DAY, 74, "faulted", "BAD_API_KEY", solved=2_010))
    runs.append(_odd(NOW - 9 * DAY - 3_600, 61, "faulted", "BAD_API_KEY", solved=1_980))
    runs.append(_odd(NOW - 5 * DAY, 92, "faulted", "NO_CREDIT", solved=2_400))
    runs.append(_odd(NOW - 4 * DAY, 6 * 3600, "stopped", "SERVICE_PAUSED", solved=2_050))
    runs.append(_odd(NOW - 3 * DAY, 1_900, "crashed", "UNKNOWN", solved=640))
    runs.append(_odd(NOW - 2 * DAY, 130, "stopped", None, solved=0, price=None))
    runs.append(
        Run(  # the app was killed mid-run: no end time, and none was ever coming
            started_at=NOW - 26_000,
            ended_at=None,
            ending="stopped",
            fault=None,
            rounds=7,
            joined=180,
            solved=520,
            failed=224,
            speed_percent=100,
            price_per_1k=1.20,
        )
    )
    runs.sort(key=lambda run: run.started_at, reverse=True)
    return runs


def _odd(
    started: float,
    seconds: float,
    ending: str,
    fault: str | None,
    solved: int,
    price: float | None = 1.20,
) -> Run:
    return Run(
        started_at=started,
        ended_at=started + seconds,
        ending=ending,
        fault=fault,
        rounds=max(1, int(seconds // 90)),
        joined=solved // 3,
        solved=solved,
        failed=int(solved * 0.55),
        speed_percent=100,
        price_per_1k=price,
    )


HISTORY = make_history()


# --- what the totals line is made of ----------------------------------------


@dataclass(frozen=True)
class Totals:
    """The sums above the table. Rows with no price are counted, never priced.

    `unpriced` exists so a variant can decide whether to admit that a run is
    missing from the money. #43 settled that such a row is skipped by the totals:
    a spend of unknown is not a spend of nothing.
    """

    dollars: float
    solves: int
    runs: int
    unpriced: int


def totals_of(runs: list[Run], since: float | None = None) -> Totals:
    wanted = [run for run in runs if since is None or run.started_at >= since]
    priced = [run for run in wanted if run.dollars is not None]
    return Totals(
        dollars=sum(run.dollars or 0.0 for run in priced),
        solves=sum(run.solved for run in wanted),
        runs=len(wanted),
        unpriced=len(wanted) - len(priced),
    )


# --- the words ---------------------------------------------------------------
#
# All of it would live in `ui/messages.py` (ADR 0005). It is here because a
# prototype has no seam to cross, and the wording is half of what is being
# looked at.

ENDING_WORD = {
    ("stopped", None): "Stopped",
    ("stopped", "SERVICE_PAUSED"): "Stopped while the service was down",
    ("stopped", "NO_INTERNET"): "Stopped while offline",
    ("faulted", "BAD_API_KEY"): "Key was rejected",
    ("faulted", "NO_CREDIT"): "Ran out of credit",
    ("crashed", "UNKNOWN"): "Something went wrong",
}


def ending_word(run: Run) -> str:
    if run.interrupted:
        return "App was closed"
    return ENDING_WORD.get((run.ending, run.fault)) or "Stopped by an error"


def ending_class(run: Run) -> str:
    """Roles, not colours. An ending nobody chose is a warning, never an alarm."""
    if run.interrupted:
        return "fs-muted"
    if run.ending == "stopped" and run.fault is None:
        return "fs-ink"
    return "fs-warn"


def money(dollars: float | None) -> str:
    """Two decimals, and a dash for a run whose price was never read (#42)."""
    return "—" if dollars is None else f"${dollars:,.2f}"


def lasted(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 90:
        return f"{int(seconds)}s"
    if seconds < 3_600:
        return f"{int(seconds // 60)}m"
    return f"{int(seconds // 3600)}h {int(seconds % 3600 // 60):02d}m"


def when(at: float, year: bool = False) -> str:
    return time.strftime("%d %b %Y %H:%M" if year else "%d %b %H:%M", time.localtime(at))


NEWER_FILE = "This history was written by a newer version of the app."
EMPTY_TITLE = "No runs yet."
EMPTY_NOTE = "Every run you start is written here, with what it spent."


# --- the three screens -------------------------------------------------------


class Screen:
    """One variant: its control on Home, and the history screen it draws."""

    entry_icon = "history"
    entry_label = "History"

    def entry_point(self, go: Callable[[], None]) -> ui.element:
        """The control that sits next to the gear on Home."""
        button = ui.button(icon=self.entry_icon).props("flat round")
        with button:
            ui.tooltip(self.entry_label)
        button.on("click", go)
        return button

    def draw(self, runs: list[Run], newer: bool, go_home: Callable[[], None]) -> None:
        raise NotImplementedError


class Ledger(Screen):
    """A. One dense table, and every fact in a column of its own.

    The claim: this screen is a book-keeping screen, so it should look like one.
    Eight columns, nothing hidden, nothing to click. The totals are one line of
    small text rather than a display, because the table is the subject.

    All-time says how many runs it is summing, inline: `468 runs` next to the
    money is what turns `$412` from a number into a rate.

    Clear history is a text button up beside the title, where a destructive
    control is easiest to reach — which is the thing to argue about.

    What to look at: whether eight columns still read at 900px in Handheld, and
    whether the interrupted row's two dashes look like missing data or like a
    fact.
    """

    entry_icon = "history"
    entry_label = "History"

    COLUMNS = [
        {"name": "started", "label": "Started", "field": "started", "align": "left"},
        {"name": "lasted", "label": "Lasted", "field": "lasted", "align": "right"},
        {"name": "rounds", "label": "Rounds", "field": "rounds", "align": "right"},
        {"name": "joined", "label": "Joined", "field": "joined", "align": "right"},
        {"name": "solved", "label": "Solved", "field": "solved", "align": "right"},
        {"name": "failed", "label": "Could not check", "field": "failed", "align": "right"},
        {"name": "spent", "label": "Spent", "field": "spent", "align": "right"},
        {"name": "ending", "label": "Ended", "field": "ending", "align": "left"},
    ]

    ENDING_CELL = """
    <q-td :props="props"><span :class="props.row.endingClass">{{ props.value }}</span></q-td>
    """

    def draw(self, runs: list[Run], newer: bool, go_home: Callable[[], None]) -> None:
        confirm = _confirm_dialog(
            "Delete every run in your history?",
            f"That is {len(runs):,} runs, and it cannot be undone. Your keys are not touched.",
            "Delete them",
        )
        with ui.column().classes("w-full items-stretch gap-4 p-6"):
            with ui.row().classes("w-full items-center gap-3"):
                back = ui.button(icon="arrow_back").props("flat round")
                back.on("click", go_home)
                ui.label("History").classes("text-2xl font-bold")
                ui.space()
                clear = ui.button("Clear history").props("flat no-caps color=negative")
                clear.on("click", confirm.open)
                clear.set_enabled(bool(runs))

            if newer:
                ui.label(NEWER_FILE).classes("text-sm fs-warn")
            elif not runs:
                ui.label(EMPTY_TITLE).classes("text-base font-semibold")
                ui.label(EMPTY_NOTE).classes("text-sm fs-muted")
            else:
                self._totals(runs)
                ui.table(columns=self.COLUMNS, rows=self._rows(runs), row_key="key").props(
                    "dense flat"
                ).classes("w-full").add_slot("body-cell-ending", self.ENDING_CELL)

    def _totals(self, runs: list[Run]) -> None:
        all_time = totals_of(runs)
        week = totals_of(runs, since=NOW - 7 * DAY)
        with ui.column().classes("w-full gap-0"):
            ui.label(
                f"All time   {money(all_time.dollars)}   ·   "
                f"{all_time.solves:,} captchas solved   ·   {all_time.runs:,} runs"
            ).classes("text-sm fs-ink")
            ui.label(
                f"Last 7 days   {money(week.dollars)}   ·   "
                f"{week.solves:,} captchas solved   ·   {week.runs:,} runs"
            ).classes("text-sm fs-muted")

    def _rows(self, runs: list[Run]) -> list[dict[str, Any]]:
        return [
            {
                "key": index,
                "started": when(run.started_at, year=True),
                "lasted": lasted(run.seconds),
                "rounds": f"{run.rounds:,}",
                "joined": f"{run.joined:,}",
                "solved": f"{run.solved:,}",
                "failed": f"{run.failed:,}",
                "spent": money(run.dollars),
                "ending": ending_word(run),
                "endingClass": ending_class(run),
            }
            for index, run in enumerate(runs)
        ]


class Receipt(Screen):
    """B. No table at all: a stack of runs with the money on the right.

    The claim: this is a spending record, so it should read like a statement.
    Each run is a line with the date on the left and what it cost on the right,
    and the counts sit under the date in one quiet sentence. A table's grid buys
    nothing when seven of its eight columns are numbers nobody scans down.

    The totals are two figures the size of headings, because a person opening
    this screen is answering "how much has this cost me", not "what did the run
    on the 4th do".

    Clear history is at the very bottom, past the last run, on the argument that
    a control which deletes everything should take a scroll to reach.

    What to look at: whether losing the columns costs anything real, and whether
    the ending, as a chip under the date, reads as loudly as it should for a key
    that died at 2am.
    """

    entry_icon = "receipt_long"
    entry_label = "Spending"

    def entry_point(self, go: Callable[[], None]) -> ui.element:
        """A word, not an icon: `History` is a guess, `Spending` is a promise."""
        button = ui.button(self.entry_label, icon=self.entry_icon).props("flat no-caps")
        button.on("click", go)
        return button

    def draw(self, runs: list[Run], newer: bool, go_home: Callable[[], None]) -> None:
        confirm = _confirm_dialog(
            "Clear the whole history?",
            f"{len(runs):,} runs go for good. This is spending records, not your keys.",
            "Clear it",
        )
        with ui.column().classes("w-full items-stretch gap-4 p-6"):
            with ui.row().classes("w-full items-center gap-3"):
                back = ui.button(icon="arrow_back").props("flat round")
                back.on("click", go_home)
                ui.label("Spending").classes("text-2xl font-bold")

            if newer or not runs:
                with ui.column().classes("w-full items-center gap-1 pt-16"):
                    ui.label("Nothing to show" if newer else EMPTY_TITLE).classes(
                        "text-base font-semibold"
                    )
                    ui.label(NEWER_FILE if newer else EMPTY_NOTE).classes(
                        "text-sm fs-muted text-center"
                    )
                return

            self._totals(runs)
            ui.separator()
            for run in runs:
                self._run_line(run)

            ui.separator().classes("mt-4")
            with ui.row().classes("w-full justify-center py-4"):
                clear = ui.button("Clear history").props("outline no-caps color=negative")
                clear.on("click", confirm.open)

    def _totals(self, runs: list[Run]) -> None:
        all_time = totals_of(runs)
        week = totals_of(runs, since=NOW - 7 * DAY)
        with ui.row().classes("w-full items-start gap-10"):
            for title, figure in (("All time", all_time), ("Last 7 days", week)):
                with ui.column().classes("gap-0"):
                    ui.label(title).classes("text-sm fs-muted")
                    ui.label(money(figure.dollars)).classes("text-3xl font-bold fs-ink")
                    ui.label(
                        f"{figure.solves:,} captchas solved across {figure.runs:,} runs"
                    ).classes("text-xs fs-muted")

    def _run_line(self, run: Run) -> None:
        with ui.row().classes("w-full items-center flex-nowrap gap-3 py-2"):
            with ui.column().classes("gap-0 grow min-w-0"):
                with ui.row().classes("items-baseline gap-2 flex-nowrap"):
                    ui.label(when(run.started_at)).classes("text-sm font-semibold fs-ink")
                    ui.label(ending_word(run)).classes(f"text-xs {ending_class(run)}")
                rounds = f"{run.rounds:,} round" + ("" if run.rounds == 1 else "s")
                ui.label(
                    f"{lasted(run.seconds)}  ·  {rounds}  ·  "
                    f"{run.solved:,} solved  ·  {run.failed:,} could not check"
                ).classes("text-xs fs-muted")
            ui.label(money(run.dollars)).classes("text-base font-semibold fs-ink")


class SummaryFirst(Screen):
    """C. A totals band, four columns, and the rest of a run on click.

    The claim: eight columns is seven more than anyone reads down. Four carry the
    screen — when, how long, what it cost, how it ended — and the counts are one
    click away for the one run in fifty anybody interrogates.

    The totals are a band of separate figures rather than a sentence, so the
    all-time run count is a figure in its own right instead of a clause. That is
    the direct answer to whether all-time needs to say how many runs it is
    summing: here it cannot help but say it.

    Clear history hides in the overflow menu by the title, which is where an
    action nobody needs twice a year belongs.

    What to look at: whether the detail panel is worth the click, or whether
    hiding four numbers behind one just makes the screen slower to read.
    """

    entry_icon = "bar_chart"
    entry_label = "History"

    COLUMNS = [
        {"name": "started", "label": "Started", "field": "started", "align": "left"},
        {"name": "lasted", "label": "Lasted", "field": "lasted", "align": "right"},
        {"name": "spent", "label": "Spent", "field": "spent", "align": "right"},
        {"name": "ending", "label": "Ended", "field": "ending", "align": "left"},
    ]

    ENDING_CELL = Ledger.ENDING_CELL

    def draw(self, runs: list[Run], newer: bool, go_home: Callable[[], None]) -> None:
        confirm = _confirm_dialog(
            "Clear history?",
            f"{len(runs):,} runs, back to {when(runs[-1].started_at, year=True) if runs else '—'}."
            " Gone for good.",
            "Clear history",
        )
        with ui.column().classes("w-full items-stretch gap-4 p-6"):
            with ui.row().classes("w-full items-center gap-3"):
                back = ui.button(icon="arrow_back").props("flat round")
                back.on("click", go_home)
                ui.label("History").classes("text-2xl font-bold")
                ui.space()
                with ui.button(icon="more_vert").props("flat round dense"):
                    with ui.menu():
                        item = ui.menu_item("Clear history", on_click=confirm.open)
                        item.set_enabled(bool(runs))

            if newer:
                ui.label(NEWER_FILE).classes("text-sm fs-warn")
                return
            if not runs:
                ui.label(EMPTY_TITLE).classes("text-base font-semibold")
                ui.label(EMPTY_NOTE).classes("text-sm fs-muted")
                return

            self._band(runs)
            with ui.row().classes("w-full flex-nowrap items-start gap-4 min-w-0"):
                table = (
                    ui.table(columns=self.COLUMNS, rows=self._rows(runs), row_key="key")
                    .props("dense flat")
                    .classes("grow min-w-0")
                )
                table.add_slot("body-cell-ending", self.ENDING_CELL)
                detail = ui.column().classes("w-64 shrink-0 gap-0")

            with detail:
                ui.label("Pick a run to see what it did.").classes("text-sm fs-muted")

            def picked(event: Any) -> None:
                run = runs[event.args[1]["key"]]
                detail.clear()
                with detail:
                    self._detail(run)

            table.on("rowClick", picked)

    def _band(self, runs: list[Run]) -> None:
        all_time = totals_of(runs)
        week = totals_of(runs, since=NOW - 7 * DAY)
        with ui.row().classes("w-full items-end gap-8"):
            _figure("Spent all time", money(all_time.dollars), "text-2xl")
            _figure("Captchas solved", f"{all_time.solves:,}", "text-2xl")
            _figure("Runs", f"{all_time.runs:,}", "text-2xl")
            ui.separator().props("vertical")
            _figure("Last 7 days", money(week.dollars), "text-2xl")
            _figure("Runs", f"{week.runs:,}", "text-2xl")

    def _rows(self, runs: list[Run]) -> list[dict[str, Any]]:
        return [
            {
                "key": index,
                "started": when(run.started_at),
                "lasted": lasted(run.seconds),
                "spent": money(run.dollars),
                "ending": ending_word(run),
                "endingClass": ending_class(run),
            }
            for index, run in enumerate(runs)
        ]

    def _detail(self, run: Run) -> None:
        ui.label(when(run.started_at, year=True)).classes("text-sm font-semibold fs-ink")
        ui.label(ending_word(run)).classes(f"text-xs {ending_class(run)} pb-2")
        for label, value in (
            ("Lasted", lasted(run.seconds)),
            ("Rounds", f"{run.rounds:,}"),
            ("Joined", f"{run.joined:,}"),
            ("Captchas solved", f"{run.solved:,}"),
            ("Could not check", f"{run.failed:,}"),
            ("Speed", f"{run.speed_percent}%"),
            ("Price per 1,000", money(run.price_per_1k)),
            ("Spent", money(run.dollars)),
        ):
            with ui.row().classes("w-full justify-between items-baseline"):
                ui.label(label).classes("text-xs fs-muted")
                ui.label(value).classes("text-xs font-semibold fs-ink")


def _figure(title: str, value: str, size: str) -> None:
    with ui.column().classes("gap-0"):
        ui.label(title).classes("text-xs fs-muted")
        ui.label(value).classes(f"{size} font-bold fs-ink")


def _confirm_dialog(question: str, note: str, yes: str) -> ui.dialog:
    """Built once beside the button that opens it, the way Settings does it."""
    with ui.dialog() as dialog, ui.card().classes("items-stretch gap-3"):
        ui.label(question).classes("text-lg font-semibold")
        ui.label(note).classes("text-sm fs-muted")
        with ui.row().classes("justify-end gap-2"):
            ui.button("Cancel").props("flat").on("click", dialog.close)
            done = ui.button(yes).props("color=negative")
            done.on("click", lambda: _go(data="empty"))
    return dialog


SCREENS: dict[str, Callable[[], Screen]] = {"A": Ledger, "B": Receipt, "C": SummaryFirst}


# --- the page ----------------------------------------------------------------

_state = {"variant": "A", "theme": "modern", "screen": "history", "data": "full", "frame": "on"}


def _go(**changes: str) -> None:
    wanted = {**_state, **changes}
    ui.navigate.to(
        "/?" + "&".join(f"{name}={value}" for name, value in wanted.items())
    )


def _pick(**changes: str) -> Callable[[], None]:
    """A no-argument handler, so NiceGUI does not hand the click to `_go`."""
    return lambda: _go(**changes)


def _fake_balance(key: str, session: Any | None = None) -> dict[str, Any]:
    return {
        "estimated_solves": 82_873,
        "price_per_1k": 1.20,
        "balance": 124.31,
        "max_concurrent": 40,
    }


async def _no_update_check(self: update_offer.UpdateOffer) -> None:
    return None


def _marked(marker: str) -> ui.element | None:
    """The one element carrying a `mark()`, found without touching Home's code."""
    for element in ui.context.client.elements.values():
        if marker in getattr(element, "_markers", []):
            return element
    return None


def _home(screen: Screen) -> None:
    """The real Home, with the variant's entry point dropped in beside the gear."""
    home.build("prototype-key", "prototype-token", 100, lambda: None)

    gear = _marked("settings-gear")
    if gear is None:  # Home changed its markers; the prototype is not worth a crash
        return
    row = gear.parent_slot.parent  # type: ignore[union-attr]
    with gear.parent_slot:  # type: ignore[union-attr]
        entry = screen.entry_point(lambda: _go(screen="history"))
    entry.move(row, target_index=0)


def _bar() -> None:
    """The floating prototype bar. Deliberately ugly, so it reads as not-the-app."""
    with ui.row().classes(
        "fixed bottom-4 left-1/2 -translate-x-1/2 z-50 items-center gap-2 "
        "rounded-full bg-black text-white px-3 py-2 shadow-lg"
    ).style("font-family: ui-monospace, monospace; font-size: 12px"):
        variant = _state["variant"]
        index = VARIANTS.index(variant)

        def go(step: int) -> None:
            _go(variant=VARIANTS[(index + step) % len(VARIANTS)])

        arrows = "flat round dense color=white"
        ui.button(icon="chevron_left", on_click=lambda: go(-1)).props(arrows)
        ui.label(f"{variant} — {VARIANT_NAMES[variant]}").classes("px-1")
        ui.button(icon="chevron_right", on_click=lambda: go(1)).props(arrows)

        ui.label("|").classes("opacity-40")
        theme_index = THEMES.index(_state["theme"])
        ui.button(
            _state["theme"],
            on_click=lambda: _go(theme=THEMES[(theme_index + 1) % len(THEMES)]),
        ).props(FLAT)

        ui.label("|").classes("opacity-40")
        ui.button(
            "home" if _state["screen"] == "history" else "history",
            on_click=lambda: _go(
                screen="home" if _state["screen"] == "history" else "history"
            ),
        ).props(FLAT)

        ui.label("|").classes("opacity-40")
        for name in DATASETS:
            ui.button(name, on_click=_pick(data=name)).props(FLAT)

        ui.label("|").classes("opacity-40")
        ui.button(
            f"frame {_state['frame']}",
            on_click=lambda: _go(frame="off" if _state["frame"] == "on" else "on"),
        ).props(FLAT)

    def on_key(event: Any) -> None:
        if not event.action.keydown:
            return
        if event.key.arrow_left:
            go(-1)
        elif event.key.arrow_right:
            go(1)

    ui.keyboard(on_key=on_key)


def page(variant: str, theme_key: str, screen: str, data: str, frame: str) -> None:
    _state.update(
        variant=variant if variant in VARIANTS else "A",
        theme=theme_key if theme_key in THEMES else "modern",
        screen=screen if screen in ("home", "history") else "history",
        data=data if data in DATASETS else "full",
        frame=frame if frame in ("on", "off") else "on",
    )
    drawn = SCREENS[_state["variant"]]()
    runs = HISTORY if _state["data"] == "full" else []

    theme.install()
    theme.wear(_state["theme"])

    # The real window is 900x640 (`ui/app.py`). Held to that by default, and
    # scrolling inside itself, so nothing on screen is bigger than it can be.
    with ui.column().classes("w-full items-center p-4"):
        inside = ui.column().classes("w-full items-stretch gap-0")
        if _state["frame"] == "on":
            inside.classes("overflow-auto shrink-0").style(
                f"width: {WINDOW_WIDTH}px; height: {WINDOW_HEIGHT}px;"
                "border: 1px solid var(--fs-panel-edge)"
            )

    with inside:
        if _state["screen"] == "home":
            _home(drawn)
        else:
            drawn.draw(runs, newer=_state["data"] == "newer", go_home=lambda: _go(screen="home"))

    _bar()


def main() -> int:
    setattr(keys, "check_api_key", _fake_balance)
    setattr(update_offer.UpdateOffer, "check", _no_update_check)

    @ui.page("/")
    def _(
        variant: str = "A",
        theme: str = "modern",
        screen: str = "history",
        data: str = "full",
        frame: str = "on",
    ) -> None:
        page(variant, theme, screen, data, frame)

    ui.run(port=PORT, reload=False, show=True, title="PROTOTYPE — history screen (#44)")
    return 0


if __name__ in {"__main__", "__mp_main__"}:
    main()
