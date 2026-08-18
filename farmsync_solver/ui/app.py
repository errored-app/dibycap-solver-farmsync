"""Opens the native desktop window and picks the first screen.

Native mode only: `ui.run(native=True)` puts the page in a pywebview window with
no browser tab and no visible localhost URL. The port is auto-scanned by NiceGUI.

The config is read once, here, before the window opens (spec 10). Setup is shown
only when that read gives no usable pair of keys; every other launch lands on
Home.
"""
from __future__ import annotations

import logging

from nicegui import ui

from .. import config
from .._version import APP_NAME, VERSION
from . import home, setup

WINDOW_WIDTH = 900
WINDOW_HEIGHT = 640

_log = logging.getLogger(__name__)
_config = config.Config()


def load_config() -> config.Config:
    """Read the file once and keep it for the life of the process."""
    global _config
    _config = config.load()
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


def build_page() -> None:
    """One page holding one screen at a time."""
    screen = ui.column().classes("w-full")

    def show_home() -> None:
        screen.clear()
        with screen:
            home.build(_config.api_key)

    def after_setup() -> None:
        load_config()
        show_home()

    with screen:
        if first_screen(_config) == "home":
            home.build(_config.api_key)
        else:
            setup.build(after_setup)


def start_window() -> None:
    """Open the window and block until the user closes it."""
    load_config()
    register_pages()
    _log.info("window open version=%s screen=%s", VERSION, first_screen(_config))
    ui.run(
        native=True,
        title=APP_NAME,
        window_size=(WINDOW_WIDTH, WINDOW_HEIGHT),
        reload=False,
        show=False,
        show_welcome_message=False,
    )
