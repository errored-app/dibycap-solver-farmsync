"""The entry file the NiceGUI `user` fixture loads.

It registers the page and calls `ui.run`, which the fixture stubs out. The real
`main.py` opens a native window, which a test must never do.
"""
from __future__ import annotations

from nicegui import ui

from farmsync_solver.ui import app

app.register_pages()
ui.run(reload=False, show=False)
