"""Opens the native desktop window.

Native mode only: `ui.run(native=True)` puts the page in a pywebview window with
no browser tab and no visible localhost URL. The port is auto-scanned by NiceGUI.
"""
from __future__ import annotations

import logging

from nicegui import ui

from .._version import APP_NAME, VERSION

WINDOW_WIDTH = 900
WINDOW_HEIGHT = 640

_log = logging.getLogger(__name__)


@ui.page("/")
def build_page() -> None:
    """The whole window, for now: the app name and its version."""
    with ui.column().classes("absolute-center items-center"):
        ui.label(APP_NAME).classes("text-3xl font-bold")
        ui.label(f"Version {VERSION}").classes("text-sm text-gray-500")


def start_window() -> None:
    """Open the window and block until the user closes it."""
    _log.info("window open version=%s", VERSION)
    ui.run(
        native=True,
        title=APP_NAME,
        window_size=(WINDOW_WIDTH, WINDOW_HEIGHT),
        reload=False,
        show=False,
        show_welcome_message=False,
    )
