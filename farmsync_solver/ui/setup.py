"""The Setup screen: first-run key entry.

Spec 4.1. Shown only when the keys are missing or unusable. Both keys are checked
live before anything is saved, and a refusal is reported on the box it belongs
to, never as one general failure.

`verify_and_save` holds the whole rule and touches no NiceGUI, so it is tested
without a window. `build` is the thin screen on top of it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from nicegui import run, ui

from .. import config, keys
from ..errors import AppError
from . import messages

SUCCESS_PAUSE_SECONDS = 1.6

_log = logging.getLogger(__name__)


class KeyCheck(Protocol):
    def __call__(self, key: str, session: Any | None = ...) -> dict[str, Any]: ...


class TokenCheck(Protocol):
    def __call__(self, token: str, session: Any | None = ...) -> None: ...


@dataclass(frozen=True)
class SetupResult:
    """What the screen shows after one press of Check and save."""

    saved: bool
    note: str = ""
    api_key_error: str = ""
    farm_token_error: str = ""


def verify_and_save(
    api_key: str,
    farm_token: str,
    path: Path | None = None,
    check_key: KeyCheck | None = None,
    check_token: TokenCheck | None = None,
) -> SetupResult:
    """Check both keys, then save them only if both were accepted."""
    api_key, farm_token = api_key.strip(), farm_token.strip()
    # Looked up now, not in the signature, so a caller can swap either one.
    check_key = check_key or keys.check_api_key
    check_token = check_token or keys.check_farm_token

    # Both are checked on every press, even when the first fails, so a user with
    # two wrong keys is told about both at once instead of one after the other.
    balance, api_key_error = _check_key(api_key, check_key)
    farm_token_error = _check_token(farm_token, check_token)

    if api_key_error or farm_token_error:
        return SetupResult(
            saved=False, api_key_error=api_key_error, farm_token_error=farm_token_error
        )

    saved = config.Config(
        api_key=api_key,
        farm_token=farm_token,
        # Re-read rather than carry a copy: only the speed is being kept, and
        # the file is the newest word on it.
        speed_percent=config.load(path).speed_percent,
    )
    config.save(saved, path)
    _log.info("setup saved keys")
    return SetupResult(saved=True, note=messages.key_works(balance))


def build(on_done: Callable[[], None]) -> None:
    """Draw the screen. `on_done` is called once both keys are saved."""
    with ui.column().classes("absolute-center items-stretch w-96 gap-4"):
        ui.label(messages.SETUP_TITLE).classes("text-2xl font-bold")
        ui.label(messages.SETUP_INTRO).classes("text-sm text-gray-500")

        api_key_box = ui.input(label=messages.SETUP_API_KEY_LABEL, password=True).props(
            "outlined autofocus"
        )
        farm_token_box = ui.input(label=messages.SETUP_FARM_TOKEN_LABEL, password=True).props(
            "outlined"
        )
        note = ui.label().classes("text-sm text-green-700")
        button = ui.button(messages.SETUP_BUTTON).props("size=lg")

        async def press() -> None:
            # Built once, only text and colour change afterwards (spec 4.4).
            button.disable()
            note.set_text(messages.SETUP_CHECKING)
            try:
                # In a worker thread: both checks are blocking network calls, and
                # on the event loop they would freeze the window and swallow the
                # "Checking your keys..." line they are supposed to explain.
                result = await run.io_bound(
                    verify_and_save, api_key_box.value or "", farm_token_box.value or ""
                )
            finally:
                button.enable()

            _mark(api_key_box, result.api_key_error)
            _mark(farm_token_box, result.farm_token_error)
            note.set_text(result.note)
            if result.saved:
                # A short pause, so the credit line is read before Home replaces it.
                ui.timer(SUCCESS_PAUSE_SECONDS, on_done, once=True)

        button.on("click", press)


def _mark(box: ui.input, error: str) -> None:
    """Put the sentence under its own box, or clear the box when it is fine."""
    box.props(f'error={"true" if error else "false"}')
    box.props(f'error-message="{error}"')


def _check_key(api_key: str, check: KeyCheck) -> tuple[dict[str, Any], str]:
    if not api_key:
        return {}, messages.NEEDS_API_KEY
    try:
        return check(api_key), ""
    except AppError as error:
        _log.info("setup key refused code=%s", error.code.value)
        return {}, messages.for_code(error.code)
    except Exception as error:  # a surprise must not take the window down
        return {}, messages.for_code(AppError.from_exception(error).code)


def _check_token(farm_token: str, check: TokenCheck) -> str:
    if not farm_token:
        return messages.NEEDS_FARM_TOKEN
    try:
        check(farm_token)
    except AppError as error:
        _log.info("setup token refused code=%s", error.code.value)
        return messages.for_code(error.code)
    except Exception as error:
        return messages.for_code(AppError.from_exception(error).code)
    return ""
