"""The Settings screen: keys, Speed, Forget my keys, version.

Spec 4.3. There is no About screen; the version lives at the bottom of this one.
Check for updates is the manual half of spec 12: the silent check runs on
startup, and this button is what a support conversation can point at. Finding an
update here does not install it — the bar on Home does that, and only when no run
is going.

Copy diagnostics and Open log folder are the whole support path (spec 8.4), and
they stay live during a run: trouble is exactly when a user reaches for them.

Speed is the only face the thread count has (spec 5.4). The percentage is saved;
the derived thread count is never written down and never shown.

Spec 5.7 locks the keys and Speed while a run is going, but leaves the screen
open and readable: blocking the whole screen would teach the user the app is
stuck.

The key boxes open **empty**. The saved keys are never sent to the page: they
spend real money (spec 10), and a box the user must fill says "replace" more
plainly than a masked box full of dots.
"""
from __future__ import annotations

import logging
from typing import Callable

from nicegui import run, ui

from .. import config, diagnostics, engine, updater
from .._version import APP_NAME, VERSION
from ..errors import AppError
from . import home, messages, setup

GOOD_COLOUR = "text-green-700"
BAD_COLOUR = "text-red-600"

_log = logging.getLogger(__name__)


def is_running() -> bool:
    """Whether a run is going, which is what locks the keys and Speed (spec 5.7)."""
    return engine.current().snapshot().state is not engine.RunState.IDLE


def build(
    speed_percent: int, on_back: Callable[[], None], on_forget: Callable[[], None]
) -> None:
    """Draw the screen.

    Takes the speed, not the config: the screen reads one stored value, and the
    keys it writes are typed in, never read back out.

    `on_back` returns to Home. `on_forget` is called once the keys are gone, and
    sends the app to Setup.
    """
    locked = is_running()

    with ui.column().classes("w-full items-stretch gap-6 p-8"):
        with ui.row().classes("items-center gap-3"):
            back = ui.button(icon="arrow_back").props("flat round").mark("settings-back")
            with back:  # inside the button, or the tooltip covers the whole row
                ui.tooltip(messages.SETTINGS_BACK)
            back.on("click", on_back)
            ui.label(messages.SETTINGS_TITLE).classes("text-2xl font-bold")

        if locked:
            ui.label(messages.SETTINGS_LOCKED).classes("text-sm text-orange-600")

        _keys_section(on_forget, locked)
        _speed_section(speed_percent, locked)
        _updates_section(locked)
        _support_section()

        ui.label(f"{APP_NAME} {VERSION}").classes("text-xs text-gray-500")


def _keys_section(on_forget: Callable[[], None], locked: bool) -> None:
    """The two key boxes, their one save button, and Forget my keys."""
    ui.label(messages.SETTINGS_KEYS_TITLE).classes("text-lg font-semibold")
    ui.label(messages.SETTINGS_KEYS_NOTE).classes("text-sm text-gray-500")

    api_key_box = (
        ui.input(label=messages.SETUP_API_KEY_LABEL, password=True)
        .props("outlined")
        .mark("settings-api-key")
    )
    farm_token_box = (
        ui.input(label=messages.SETUP_FARM_TOKEN_LABEL, password=True)
        .props("outlined")
        .mark("settings-farm-token")
    )
    note = ui.label().classes("text-sm text-green-700")

    with ui.row().classes("items-center gap-3"):
        save = ui.button(messages.SETTINGS_SAVE_KEYS)
        forget = ui.button(messages.SETTINGS_FORGET).props("outline color=negative")

    async def press_save() -> None:
        result = await setup.check_and_save(api_key_box, farm_token_box, save, note)
        if result is None:
            return
        note.set_text(f"{messages.SETTINGS_SAVED} {result.note}" if result.saved else "")

    # Built once, beside the button that opens it: a dialog created on every
    # press would pile up a new copy on the page each time (spec 4.4).
    confirm = _forget_dialog(on_forget)
    save.on("click", press_save)
    forget.on("click", confirm.open)

    for element in (api_key_box, farm_token_box, save, forget):
        element.set_enabled(not locked)


def _speed_section(speed_percent: int, locked: bool) -> None:
    """The four Speed buttons. A percentage only — no raw thread number."""
    ui.label(messages.SETTINGS_SPEED_LABEL).classes("text-lg font-semibold")
    ui.label(messages.SETTINGS_SPEED_HELP).classes("text-sm text-gray-500")

    choices = {percent: messages.speed_choice(percent) for percent in config.SPEED_CHOICES}
    speed = ui.toggle(choices, value=speed_percent).mark("speed-toggle")
    note = ui.label().classes("text-sm").mark("speed-note")

    def pick() -> None:
        picked = speed.value
        if picked not in config.SPEED_CHOICES:  # a cleared toggle picks nothing
            return
        try:
            config.save_speed(picked)
        except Exception as error:  # a full disk must not make the click do nothing
            _say(note, _failure_text(error), good=False)
            return
        _say(note, messages.SETTINGS_SAVED, good=True)

    speed.on_value_change(pick)
    speed.set_enabled(not locked)


def _updates_section(locked: bool) -> None:
    """Spec 12's manual check. It reports; it never installs from this screen.

    Locked during a run with the keys and Speed: spec 12 asks for no check at all
    while a run is going, and the bar that would install what it found is refused
    mid-run anyway.
    """
    ui.label(messages.SETTINGS_UPDATES_TITLE).classes("text-lg font-semibold")
    ui.label(messages.SETTINGS_UPDATES_NOTE).classes("text-sm text-gray-500")

    check = ui.button(messages.SETTINGS_CHECK_UPDATES).props("outline").mark("check-updates")
    note = ui.label().classes("text-sm").mark("update-note")

    async def press_check() -> None:
        # The button goes dead while the call is out, so a second press cannot
        # start a second check (spec 13, "disabled buttons").
        check.set_enabled(False)
        _say(note, messages.SETTINGS_CHECKING_UPDATE, good=True)
        answer = await run.io_bound(updater.check)
        check.set_enabled(True)
        _say(note, _update_answer(answer), good=answer is not None and answer.reached_github)

    check.on("click", press_check)
    check.set_enabled(not locked)


def _update_answer(answer: updater.CheckAnswer | None) -> str:
    """The one sentence a manual check leaves behind.

    A check nobody could make must not read as "you have the newest version": the
    user pressed a button and is owed the difference.
    """
    if answer is None or not answer.reached_github:
        return messages.SETTINGS_CHECK_FAILED
    if answer.update is None:
        return messages.SETTINGS_UP_TO_DATE
    return messages.update_found(answer.update.version)


def _support_section() -> None:
    """Spec 8.4: one button to copy a report, one to open the folder of logs.

    Neither is locked during a run. Both are silent about failure in the log and
    plain about it on screen, because this is the screen a stuck user is on.
    """
    ui.label(messages.SETTINGS_SUPPORT_TITLE).classes("text-lg font-semibold")
    ui.label(messages.SETTINGS_SUPPORT_NOTE).classes("text-sm text-gray-500")

    with ui.row().classes("items-center gap-3"):
        copy = ui.button(messages.SETTINGS_COPY_DIAGNOSTICS).mark("copy-diagnostics")
        open_logs = ui.button(messages.SETTINGS_OPEN_LOGS).props("outline").mark("open-logs")
    note = ui.label().classes("text-sm").mark("support-note")

    async def press_copy() -> None:
        await ui.clipboard.write(diagnostics_text())
        _say(note, messages.SETTINGS_COPIED, good=True)

    def press_open() -> None:
        opened = diagnostics.open_log_folder()
        _say(note, "" if opened else messages.SETTINGS_LOGS_FAILED, good=opened)

    copy.on("click", press_copy)
    open_logs.on("click", press_open)


def diagnostics_text() -> str:
    """The report the Copy button puts on the clipboard.

    Every value is read at press time. Speed especially: the toggle above saves
    to the file the moment it is clicked, and a value closed over when the screen
    was drawn would report the percentage the user just changed away from.

    The key check and the credit come from the last Home re-check rather than
    from a fresh call, so pressing Copy while nothing works still produces
    something to paste.
    """
    snapshot = engine.current().snapshot()
    answer = home.last_credit()
    return diagnostics.bundle(
        run_state=snapshot.state.value,
        key_check=answer.check_note if answer else messages.DIAGNOSTICS_KEY_UNCHECKED,
        credit=answer.header if answer else messages.CREDIT_UNKNOWN,
        speed_percent=config.load().speed_percent,
    )


def _forget_dialog(on_forget: Callable[[], None]) -> ui.dialog:
    """Ask before deleting. The keys cost money to get wrong."""
    with ui.dialog().mark("forget-dialog") as dialog, ui.card().classes("items-stretch gap-3"):
        ui.label(messages.SETTINGS_FORGET_QUESTION).classes("text-lg font-semibold")
        ui.label(messages.SETTINGS_FORGET_NOTE).classes("text-sm text-gray-500")
        failure = ui.label().classes("text-sm text-red-600")
        with ui.row().classes("justify-end gap-2"):
            ui.button(messages.SETTINGS_CANCEL).props("flat").on("click", dialog.close)
            confirm = ui.button(messages.SETTINGS_FORGET_YES).props("color=negative")

    def forget() -> None:
        # A write that failed must leave the user here, still holding their keys,
        # rather than drop them on Setup with the file untouched.
        try:
            config.forget_keys()
        except Exception as error:
            failure.set_text(_failure_text(error))
            return
        # The remembered re-check goes with the keys it was made against, or the
        # diagnostics header would still report a key that is no longer there.
        home.forget_credit()
        dialog.close()
        on_forget()

    confirm.on("click", forget)
    return dialog


def _say(note: ui.label, text: str, good: bool) -> None:
    """Green for a save that landed, red for one that did not."""
    note.set_text(text)
    note.classes(
        add=GOOD_COLOUR if good else BAD_COLOUR,
        remove=BAD_COLOUR if good else GOOD_COLOUR,
    )


def _failure_text(error: Exception) -> str:
    """A failed write, in the one place user-facing wording comes from."""
    code = AppError.from_exception(error).code
    _log.warning("settings write failed code=%s", code.value, exc_info=error)
    return messages.for_code(code)
