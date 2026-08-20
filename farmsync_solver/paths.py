r"""Where the app writes: one folder, named here and nowhere else.

Spec 9.1. Everything the app leaves on disk — the config file, the log folder,
the downloaded installer — sits under `%APPDATA%\FarmsyncSolver`. That is one
fact about the whole app, so it is written down once. The modules that own each
file still own its name and its shape; they just ask this one where to put it.

`APPDATA` is set on every Windows the app supports. The fallback is there for the
one that is not: a missing variable must not stop the app starting.
"""
from __future__ import annotations

import os
from pathlib import Path

from ._version import APP_NAME


def app_data_dir() -> Path:
    r"""`%APPDATA%\FarmsyncSolver`, per Windows user."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / APP_NAME
