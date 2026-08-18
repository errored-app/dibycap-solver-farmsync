"""The Home screen: start, stop, progress, counters.

A placeholder for now: the credit header, the key re-check and the Start button
land with the Home ticket. It exists so Setup has somewhere to go.
"""
from __future__ import annotations

from nicegui import ui

from .._version import APP_NAME, VERSION


def build() -> None:
    """Draw the screen."""
    with ui.column().classes("absolute-center items-center"):
        ui.label(APP_NAME).classes("text-3xl font-bold")
        ui.label(f"Version {VERSION}").classes("text-sm text-gray-500")
