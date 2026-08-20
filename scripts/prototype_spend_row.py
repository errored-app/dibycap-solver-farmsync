r"""PROTOTYPE — throwaway. Three spend rows in the real left panel (issue #42).

Three variants of "what this run has spent", rendered inside the real Home panel
with a scripted fake run behind it, switchable via `?variant=` and `?theme=`.

    uv run python -m scripts.prototype_spend_row

Run it as a module, not as a file: the project is not installed
(`package = false`), so only `-m` puts the repo root on the import path. It opens
a browser tab rather than the native window, so variants can be flipped and
screenshotted side by side.

Nothing here is production code. It monkeypatches `ui.home` on purpose, so the
variants sit in the panel the app really draws rather than in a mock of it, and
it invents no persistence: the run is a clock and a counter.

The question, from the ticket: the left panel already counts Round, Joined,
Captchas solved, Could not check. Spend adds money to a block that has only ever
held counts. How does that row read, what does it show before `price_per_1k` has
ever been read, and does it show the seam when the price changes mid-run?

    A  Fifth counter      one more `Round: 3` row, four decimals, 5 Hz
    B  Its own block      a rule, then a big figure and a working line, 1 Hz
    C  On the solve count the money rides the count it comes from, in cents

One tab at a time: the variant and the run are process-wide, so two tabs open at
once share one engine and fight over the same elements. Flip variants with the
bar, not with a second window.

Buttons on the bar force the two edge cases: **No price** (the balance call has
never answered with `price_per_1k`) and **Price change** (mid-run, so the figure
is a running sum of what was billed, not a multiplication of the final count).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any, Callable

from nicegui import ui

from farmsync_solver import keys
from farmsync_solver.engine import Engine
from farmsync_solver.engine.snapshot import AccountRow, Headline, Result, RunSnapshot, RunState
from farmsync_solver.ui import home, theme, update_offer

PORT = 8123

# The live account set of spec 2, at the pace prove_round measured: 132 accounts
# in about 72 s, then the fixed rest.
ROUND_SIZE = 132
ACCOUNTS_PER_SECOND = 1.8
DISCOVER_SECONDS = 3.0
REST_SECONDS = 15.0

# 4 solved, 1 joined, 2 failed out of every 7 — the 28.6% failure rate of spec
# 4.2, without a random number generator that would make two screenshots differ.
PATTERN = [Result.SOLVED] * 4 + [Result.JOINED] + [Result.FAILED] * 2

FIRST_PRICE = 1.50  # dollars per 1,000 solves
LATER_PRICE = 2.20  # what "the price changed mid-run" changes it to

VARIANTS = ["A", "B", "C"]
VARIANT_NAMES = {
    "A": "Fifth counter",
    "B": "Its own block",
    "C": "On the solve count",
}
FLAT = "flat dense color=white no-caps"
THEMES = ["modern", "handheld", "handheld-color", "console", "adventure"]


# --- the facts a spend row would get ---------------------------------------


@dataclass(frozen=True)
class Spend:
    """What the engine would send across the seam. Facts, never sentences.

    A running sum, not a multiplication: `dollars` is added to as solves land, so
    solves billed before a price change keep the price they were billed at.
    `prices_used` is how many different prices went into that sum, which is the
    only fact a variant needs to show the seam at all.
    """

    dollars: float = 0.0
    price_known: bool = False  # has `price_per_1k` ever been read?
    prices_used: int = 0
    price: float = 0.0  # what the last solve was billed at


# The knobs the bottom bar turns. Module state, because a prototype may.
_price: float | None = FIRST_PRICE
_spend = Spend()


def set_price(value: float | None) -> None:
    global _price
    _price = value


def bill(solves: int) -> None:
    """Add `solves` solves at whatever the price is right now."""
    global _spend
    if _price is None or solves <= 0:
        return
    changed = _spend.price_known and _price != _last_billed_price[0]
    _last_billed_price[0] = _price
    _spend = replace(
        _spend,
        dollars=_spend.dollars + solves * _price / 1000,
        price_known=True,
        price=_price,
        prices_used=(
            _spend.prices_used + 1
            if changed or not _spend.price_known
            else _spend.prices_used
        ),
    )


_last_billed_price = [FIRST_PRICE]


def reset_spend() -> None:
    global _spend
    _spend = Spend()
    _last_billed_price[0] = _price if _price is not None else FIRST_PRICE


# --- the fake run -----------------------------------------------------------


class ScriptedEngine(Engine):
    """A run made of a clock. No threads, no network, no dibycap.

    Subclasses the real `Engine` so Home is handed exactly the type it expects
    and every method it calls is the real signature.
    """

    def __init__(self) -> None:
        super().__init__()
        self._started_at: float | None = None
        self._counted = 0  # accounts finished across the whole run
        self._new_rows: list[AccountRow] = []
        self._snap = RunSnapshot()

    def start(self, api_key: str, farm_token: str, speed_percent: int) -> None:
        self._started_at = time.monotonic()
        self._counted = 0
        self._new_rows = []
        reset_spend()
        self._snap = RunSnapshot(state=RunState.DISCOVERING, headline=Headline.STARTING)

    def stop(self) -> None:
        self._started_at = None
        # `replace`, not a fresh snapshot: a stopped run keeps what it counted,
        # or the panel would show 0 solves beside a non-zero spend.
        self._snap = replace(self._snap, state=RunState.IDLE, headline=Headline.STOPPED)

    def snapshot(self) -> RunSnapshot:
        self._advance()
        return self._snap

    def latest(self) -> RunSnapshot:
        """The snapshot as it stands, without moving the clock on.

        The variant is painted from this rather than from `snapshot()`: a second
        `snapshot()` in the same refresh would bill another tick, and the money
        would sit one tick ahead of the counters beside it.
        """
        return self._snap

    def take_new_rows(self) -> list[AccountRow]:
        rows, self._new_rows = self._new_rows, []
        return rows

    def _advance(self) -> None:
        if self._started_at is None:
            return

        elapsed = time.monotonic() - self._started_at
        cycle = DISCOVER_SECONDS + ROUND_SIZE / ACCOUNTS_PER_SECOND + REST_SECONDS
        rounds_done = int(elapsed // cycle)
        into = elapsed - rounds_done * cycle
        round_number = rounds_done + 1

        if into < DISCOVER_SECONDS:
            self._snap = replace(
                self._snap,
                state=RunState.DISCOVERING,
                headline=Headline.DISCOVERING,
                round_number=round_number,
                done=0,
                total=0,
                seconds_left=None,
            )
            return

        solving = into - DISCOVER_SECONDS
        done = min(ROUND_SIZE, int(solving * ACCOUNTS_PER_SECOND))
        self._finish_up_to(rounds_done * ROUND_SIZE + done)

        if done < ROUND_SIZE:
            self._snap = replace(
                self._snap,
                state=RunState.SOLVING,
                headline=Headline.SOLVING,
                round_number=round_number,
                done=done,
                total=ROUND_SIZE,
                seconds_left=None,
            )
            return

        left = int(cycle - into) + 1
        self._snap = replace(
            self._snap,
            state=RunState.RESTING,
            headline=Headline.RESTING,
            round_number=round_number,
            done=ROUND_SIZE,
            total=ROUND_SIZE,
            seconds_left=max(0, left),
        )

    def _finish_up_to(self, target: int) -> None:
        """Land every account between what has finished and `target`."""
        snap = self._snap
        joined, solved, failed = snap.joined, snap.solved, snap.failed
        billed = 0
        now = time.time()

        while self._counted < target:
            outcome = PATTERN[self._counted % len(PATTERN)]
            if outcome is Result.SOLVED:
                solved += 1
                billed += 1
            elif outcome is Result.JOINED:
                joined += 1
            else:
                failed += 1
            self._new_rows.append(
                AccountRow(
                    username=f"account_{self._counted % 900 + 100}",
                    outcome=outcome,
                    detail="" if outcome is not Result.FAILED else "ERROR_CAPTCHA_UNSOLVABLE",
                    at=now,
                )
            )
            self._counted += 1

        bill(billed)
        self._snap = replace(
            snap,
            joined=joined,
            solved=solved,
            failed=failed,
            credit_left=124.31 - _spend.dollars,
            estimated_solves=82_873 - solved,
        )


# --- the three variants -----------------------------------------------------


class SpendRow:
    """One variant: what it builds into the panel, and what it writes each tick."""

    def build(self, state: home._Screen, column: ui.column, after: int) -> None:
        raise NotImplementedError

    def show(self, state: home._Screen, snapshot: RunSnapshot, spend: Spend) -> None:
        raise NotImplementedError


class FifthCounter(SpendRow):
    """A. One more counter, in the block with the other four.

    Money is just another number here, and the format is picked so it is never
    parked on `$0.00`: four decimals move on the very first solve. Whether that
    reads as precise or as broken is the thing to look at.

    No price yet: an em dash, which is what the block already does for a figure
    it does not have. Price change: nothing. The block has no room to say it.
    """

    def build(self, state: home._Screen, column: ui.column, after: int) -> None:
        with column:
            with ui.row().classes("w-full justify-between items-baseline") as row:
                ui.label("Spent").classes("text-sm fs-muted")
                self.figure = ui.label("—").classes("text-sm font-semibold fs-ink")
        row.move(column, target_index=after + 1)

    def show(self, state: home._Screen, snapshot: RunSnapshot, spend: Spend) -> None:
        self.figure.set_text(f"${spend.dollars:.4f}" if spend.price_known else "—")


class OwnBlock(SpendRow):
    """B. Below a rule, out of the count block, with its working shown.

    The claim: money is not a fifth count, it is the run's other subject, so it
    gets a heading-sized figure and a line saying where the figure came from.
    Rounded to the cent and settled once a second, because a big figure flickering
    at 5 Hz is the thing that makes a panel feel unstable.

    The line carries the price and not the solve count: the count is already three
    rows above it, and repeating it at a slower beat was the one place on the
    panel where two numbers disagreed.

    No price yet: the whole block stays off the screen. There is no half-answer
    worth a rule and a heading. Price change: the working line says so, which is
    the only variant here that shows the seam. No single price would multiply out
    to the figure above once two of them have been billed.
    """

    def build(self, state: home._Screen, column: ui.column, after: int) -> None:
        with column:
            self.block = ui.column().classes("w-full items-stretch gap-0 pt-2")
            with self.block:
                ui.separator().classes("mb-2")
                ui.label("Spent this run").classes("text-sm fs-muted")
                self.figure = ui.label("$0.00").classes("text-2xl font-bold fs-ink")
                self.working = ui.label("").classes("text-xs fs-muted")
        self.block.set_visibility(False)
        self._shown_at = 0.0

    def show(self, state: home._Screen, snapshot: RunSnapshot, spend: Spend) -> None:
        self.block.set_visibility(spend.price_known)
        if not spend.price_known:
            return

        # 1 Hz, not 5. The counters beside it still move at 5.
        now = time.monotonic()
        if now - self._shown_at < 1.0:
            return
        self._shown_at = now

        self.figure.set_text(f"${spend.dollars:,.2f}")
        self.working.set_text(
            "the price changed mid-run"
            if spend.prices_used > 1
            else f"at ${spend.price:.2f} per 1,000"
        )


class OnTheSolveCount(SpendRow):
    """C. No new row: the money rides the count it is made of.

    The claim: spend is not an independent fact, it is the solve count in another
    unit, so it belongs on that row and nowhere else. Cents while it is cents,
    which is most of a short run, and dollars once there are dollars to show.

    No price yet: the count alone, exactly as the panel looks today. Price change:
    nothing, and the suffix quietly stops being count times price.
    """

    def build(self, state: home._Screen, column: ui.column, after: int) -> None:
        pass  # it writes into a control the real panel already built

    def show(self, state: home._Screen, snapshot: RunSnapshot, spend: Spend) -> None:
        count = f"{snapshot.solved:,}"
        if not spend.price_known:
            state.solved.set_text(count)
            return
        state.solved.set_text(f"{count}   ·   {_short_money(spend.dollars)}")


def _short_money(dollars: float) -> str:
    """Cents until there is a dollar, then dollars. `42c`, then `$1.04`."""
    cents = round(dollars * 100)
    if cents < 100:
        return f"{cents}c"
    return f"${dollars:,.2f}"


ROWS: dict[str, Callable[[], SpendRow]] = {
    "A": FifthCounter,
    "B": OwnBlock,
    "C": OnTheSolveCount,
}


# --- putting a variant inside the real panel --------------------------------

_real_left_panel = home._left_panel
_real_show_panel = home._Screen._show_panel
_row: SpendRow = FifthCounter()


def _left_panel(state: home._Screen) -> None:
    """The real panel, then the variant's own elements moved into it."""
    _real_left_panel(state)

    failed_row = state.failed.parent_slot.parent  # type: ignore[union-attr]
    column = failed_row.parent_slot.parent  # type: ignore[union-attr]
    after = column.default_slot.children.index(failed_row)
    _row.build(state, column, after)  # type: ignore[arg-type]


def _show_panel(self: home._Screen, panel: home.Panel) -> None:
    """The real write, then the variant's, from the same snapshot."""
    _real_show_panel(self, panel)
    _row.show(self, _worker.latest(), _spend)


def _fake_balance(key: str, session: Any | None = None) -> dict[str, Any]:
    return {
        "estimated_solves": 82_873,
        "price_per_1k": FIRST_PRICE,
        "balance": 124.31,
        "max_concurrent": 40,
    }


async def _no_update_check(self: update_offer.UpdateOffer) -> None:
    return None


# --- the page and the switcher ----------------------------------------------


def _bar(variant: str, theme_key: str, worker: ScriptedEngine) -> None:
    """The floating prototype bar. Deliberately ugly, so it reads as not-the-app."""
    with ui.row().classes(
        "fixed bottom-4 left-1/2 -translate-x-1/2 z-50 items-center gap-2 "
        "rounded-full bg-black text-white px-3 py-2 shadow-lg"
    ).style("font-family: ui-monospace, monospace; font-size: 12px"):
        index = VARIANTS.index(variant)

        def go(step: int) -> None:
            wanted = VARIANTS[(index + step) % len(VARIANTS)]
            ui.navigate.to(f"/?variant={wanted}&theme={theme_key}")

        arrows = "flat round dense color=white"
        ui.button(icon="chevron_left", on_click=lambda: go(-1)).props(arrows)
        ui.label(f"{variant} — {VARIANT_NAMES[variant]}").classes("px-1")
        ui.button(icon="chevron_right", on_click=lambda: go(1)).props(arrows)

        ui.label("|").classes("opacity-40")
        theme_index = THEMES.index(theme_key)
        ui.button(
            THEMES[theme_index],
            on_click=lambda: ui.navigate.to(
                f"/?variant={variant}&theme={THEMES[(theme_index + 1) % len(THEMES)]}"
            ),
        ).props(FLAT)

        ui.label("|").classes("opacity-40")
        ui.button("no price", on_click=lambda: set_price(None)).props(FLAT)
        ui.button("price $1.50", on_click=lambda: set_price(FIRST_PRICE)).props(FLAT)
        ui.button("price change", on_click=lambda: set_price(LATER_PRICE)).props(FLAT)
        ui.button("run", on_click=lambda: worker.start("", "", 100)).props(FLAT)

    def on_key(event: Any) -> None:
        if not event.action.keydown:
            return
        if event.key.arrow_left:
            go(-1)
        elif event.key.arrow_right:
            go(1)

    ui.keyboard(on_key=on_key)


_worker = ScriptedEngine()


def page(variant: str = "A", theme_key: str = "modern") -> None:
    global _row
    variant = variant.upper() if variant.upper() in VARIANTS else "A"
    theme_key = theme_key if theme_key in THEMES else "modern"
    _row = ROWS[variant]()

    theme.install()
    theme.wear(theme_key)

    # One engine for the whole process, not one per page load: flipping variant
    # or theme must not restart the run being looked at.
    with ui.column().classes("w-full"):
        home.build("prototype-key", "prototype-token", 100, lambda: None, run_engine=_worker)
    _bar(variant, theme_key, _worker)


def main() -> int:
    setattr(keys, "check_api_key", _fake_balance)
    setattr(home, "_left_panel", _left_panel)
    setattr(home._Screen, "_show_panel", _show_panel)
    setattr(update_offer.UpdateOffer, "check", _no_update_check)

    @ui.page("/")
    def _(variant: str = "A", theme: str = "modern") -> None:
        page(variant, theme)

    ui.run(port=PORT, reload=False, show=True, title="PROTOTYPE — spend row (#42)")
    return 0


if __name__ in {"__main__", "__mp_main__"}:
    main()
