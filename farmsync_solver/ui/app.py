"""Opens the native desktop window and picks the first screen.

Native mode only: `ui.run(native=True)` puts the page in a pywebview window with
no browser tab and no visible localhost URL. The port is auto-scanned by NiceGUI.

The config is read once, here, before the window opens (spec 10). Setup is shown
only when that read gives no usable pair of keys; every other launch lands on
Home.
"""
from __future__ import annotations

import logging
from typing import Callable

from nicegui import app as ui_app
from nicegui import ui

from .. import config, engine
from .._version import APP_NAME, VERSION
from . import close_guard, home, settings, setup

WINDOW_WIDTH = 900
WINDOW_HEIGHT = 640

_log = logging.getLogger(__name__)
_config = config.Config()


def load_config() -> config.Config:
    """Read the file once and keep it for the life of the process."""
    global _config
    _config = config.load()
    return _config


def current_config() -> config.Config:
    """The copy this process is holding. Re-read by `load_config`."""
    return _config


def first_screen(current: config.Config) -> str:
    """`setup` while the keys are missing or unusable, `home` after that."""
    return "home" if current.is_ready else "setup"


def register_pages() -> None:
    """Attach the page to the server.

    A call, not an import side effect: importing this module must never change
    the server, and a test harness that resets NiceGUI can register again.
    """
    ui.page("/")(build_page)
    # The door the window process knocks on when the user presses the X.
    ui_app.post(close_guard.CLOSE_ROUTE)(answer_close_request)


async def answer_close_request() -> dict[str, bool]:
    """Spec 5.3: the window's X, asking whether it may close.

    The window process cannot see the run, and the screen cannot see the X. This
    route is the round-trip between them.

    Async on purpose: it opens a dialog, and a dialog opened off the event loop
    would sit in the outbox until the next refresh pushed it out.
    """
    return {"close": home.close_or_ask()}


def build_page() -> None:
    """One page holding one screen at a time.

    Every hop back to Home re-reads the config first. Settings can change the
    keys, and one cheap file read is a smaller price than a screen showing a key
    the file no longer holds.
    """
    screen = ui.column().classes("w-full")

    def swap(draw: Callable[[], None]) -> None:
        # Home goes with the elements it drew. Its dialog cannot ask anything
        # once it is off the page, and a stale screen would refuse the X for
        # a run the user can no longer see (spec 5.3).
        home.forget_screen()
        screen.clear()
        with screen:
            draw()

    def show_home() -> None:
        swap(lambda: home.build(*_run_values(_config), show_settings))

    def show_settings() -> None:
        swap(lambda: settings.build(_config.speed_percent, back_to_home, forget_and_setup))

    def forget_and_setup() -> None:
        # Re-read first: the keys are gone from the file, and the copy this
        # process holds must go with them.
        load_config()
        swap(lambda: setup.build(back_to_home))

    def back_to_home() -> None:
        load_config()
        show_home()

    with screen:
        if first_screen(_config) == "home":
            home.build(*_run_values(_config), show_settings)
        else:
            setup.build(back_to_home)


def _run_values(current: config.Config) -> tuple[str, str, int]:
    """The three plain values a run needs, in `Engine.start` order (spec 9.2)."""
    return current.api_key, current.farm_token, current.speed_percent


def arm_close_question() -> None:
    """Let the window's X raise the close question before it closes (spec 5.3).

    NiceGUI hands `start_args` straight to `webview.start`, and pywebview calls
    that `func` in the window process once the GUI loop is up. It is the only
    way into a process this one only spawns.
    """
    ui_app.native.start_args["func"] = close_guard.bind


def _stop_run_on_shutdown() -> None:
    """A closing window must not orphan work that is already paid for (spec 5.2).

    The X asks first (spec 5.3), but the question is not the only way out: a
    crash, a Windows log-off or an update hand-over all end the process without
    one. This is the polite stop that catches every one of them.
    """
    engine.current().stop()


def start_window() -> None:
    """Open the window and block until the user closes it."""
    load_config()
    register_pages()
    arm_close_question()
    ui_app.on_shutdown(_stop_run_on_shutdown)
    _log.info("window open version=%s screen=%s", VERSION, first_screen(_config))
    ui.run(
        native=True,
        title=APP_NAME,
        window_size=(WINDOW_WIDTH, WINDOW_HEIGHT),
        reload=False,
        show=False,
        show_welcome_message=False,
    )
