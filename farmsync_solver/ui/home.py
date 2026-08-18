"""The Home screen: credit header, key re-check, Start.

Spec 4.2 and 7. On every open the app makes one cheap cookie-free `/balance`
call. It is both the credit read and a key re-check: a key that died since the
last run becomes a red line before the run, not a mystery in the middle of one.

`read_credit` holds the whole rule and touches no NiceGUI, so it is tested
without a window. `build` is the thin screen on top of it.

Spec 4.4 shapes `build`: every control is created once, and the background check
only changes text, colour and the disabled flag.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from nicegui import run, ui

from .. import credit, keys
from ..errors import AppError, ErrorCode
from ..keys import KeyCheck
from . import messages

LOW_COLOUR = "text-orange-600"
NORMAL_COLOUR = "text-gray-900"
EMPTY: dict[str, Any] = {"estimated_solves": 0}

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


def read_credit(api_key: str, check_key: KeyCheck | None = None) -> Credit:
    """Re-check the key and turn the answer into header text and a red line."""
    # Looked up now, not in the signature, so a caller can swap it.
    check_key = check_key or keys.check_api_key

    try:
        balance = check_key(api_key)
    except AppError as error:
        return _refused(error.code)
    except Exception as error:  # a surprise must not take the window down
        return _refused(AppError.from_exception(error).code)

    return Credit(header=messages.credit_header(balance), low=credit.is_low(balance))


def build(api_key: str) -> None:
    """Draw the screen and start the background re-check.

    Takes the key, not the config: the screen reads one value, and spec 9.2 asks
    the same of the engine seam for the same reason.
    """
    with ui.column().classes("w-full items-center gap-6 p-8"):
        header = ui.label(messages.HOME_CHECKING).classes("text-2xl font-bold").mark("credit-header")
        error_line = ui.label().classes("text-sm text-red-600")

        # The tooltip hangs on the wrapper, not on the button: a disabled Quasar
        # button takes no pointer events, so a tooltip inside it would never show
        # in the one state spec 5.7 needs it for.
        with ui.element("div") as start_holder:
            start = ui.button(messages.HOME_START).props("size=xl")
            start.disable()  # nothing runs until the re-check answers
        with start_holder:
            tooltip = ui.tooltip(messages.HOME_CHECKING).mark("start-tooltip")

        # A fixed line for now: the real figures arrive with the engine, which is
        # the first thing able to finish a run.
        ui.label(messages.HOME_NO_RUNS).classes("text-sm text-gray-500")

        def show(state: Credit) -> None:
            header.set_text(state.header)
            header.classes(
                add=LOW_COLOUR if state.low else NORMAL_COLOUR,
                remove=NORMAL_COLOUR if state.low else LOW_COLOUR,
            )
            error_line.set_text(state.error)
            tooltip.set_text(state.error)
            tooltip.set_visibility(bool(state.error))  # no blank bubble when all is well
            start.set_enabled(state.can_start)

        async def recheck() -> None:
            # In a worker thread: a blocking network call on the event loop
            # would freeze the window it is supposed to be filling in.
            state = await run.io_bound(read_credit, api_key)
            if state is not None:  # NiceGUI answers None when it cancels the call
                show(state)

        # once=True: one call on open, not a poll. The 10 s run refresh of
        # spec 7 belongs to the run, and lands with the engine.
        ui.timer(0, recheck, once=True)


def _refused(code: ErrorCode) -> Credit:
    """A refused check. Only "no credit" knows a figure, and that figure is 0."""
    _log.info("home re-check refused code=%s", code.value)
    out_of_credit = code is ErrorCode.NO_CREDIT
    return Credit(
        header=messages.credit_header(EMPTY) if out_of_credit else messages.CREDIT_UNKNOWN,
        low=out_of_credit,
        error=messages.for_code(code),
    )
