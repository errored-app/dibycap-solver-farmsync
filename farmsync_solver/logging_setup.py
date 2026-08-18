"""Configures stdlib logging once, at process start.

Two rules from spec 8.3 shape this module:

- Logging starts before config load and before any window, so an import-time
  crash still leaves evidence.
- A log failure never stops a run. Every failure here is swallowed and the app
  carries on with no log and no warning.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Callable

from ._version import APP_NAME

LINE_FORMAT = "%(asctime)s  %(levelname)s  %(message)s"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
FILE_STAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"
MAX_AGE = timedelta(days=7)
MAX_FILES = 20

ExceptHook = Callable[
    [type[BaseException], BaseException, TracebackType | None], None
]

_handler: logging.Handler | None = None
_log_file: Path | None = None
_previous_excepthook: ExceptHook | None = None


def default_log_dir() -> Path:
    r"""`%APPDATA%\FarmsyncSolver\logs`, beside config.json."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / APP_NAME / "logs"


def configure(log_dir: Path | None = None) -> Path | None:
    """Start one log file for this run. Returns its path, or None if logging is off."""
    global _handler, _log_file

    if _handler is not None:
        return _log_file

    _install_excepthook()

    folder = log_dir if log_dir is not None else default_log_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        _prune(folder)
        path = _free_path(folder)
        handler = logging.FileHandler(path, encoding="utf-8", delay=False)
    except OSError:
        return None

    handler.setFormatter(logging.Formatter(LINE_FORMAT, datefmt=TIME_FORMAT))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    _handler, _log_file = handler, path
    return path


def reset() -> None:
    """Undo `configure`. For tests and for a clean shutdown."""
    global _handler, _log_file, _previous_excepthook

    if _handler is not None:
        logging.getLogger().removeHandler(_handler)
        _handler.close()
    if _previous_excepthook is not None:
        sys.excepthook = _previous_excepthook

    _handler = _log_file = _previous_excepthook = None


def _install_excepthook() -> None:
    """Send uncaught exceptions to the log, then on to whatever ran before.

    Installed at most once per `configure`/`reset` cycle. Installing twice would
    make the hook its own predecessor and recurse for ever.
    """
    global _previous_excepthook

    if _previous_excepthook is not None:
        return

    previous: ExceptHook = sys.excepthook
    _previous_excepthook = previous

    def hook(
        kind: type[BaseException],
        value: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        logging.getLogger("crash").critical(
            "uncaught exception", exc_info=(kind, value, traceback)
        )
        previous(kind, value, traceback)

    sys.excepthook = hook


def _free_path(folder: Path) -> Path:
    """One file per run. Two runs in the same second get a suffix."""
    stamp = datetime.now().strftime(FILE_STAMP_FORMAT)
    path = folder / f"{stamp}.log"
    attempt = 1
    while path.exists():
        path = folder / f"{stamp}-{attempt}.log"
        attempt += 1
    return path


def _prune(folder: Path) -> None:
    """Drop files older than 7 days, then leave room for this run's own file.

    Runs before the new file is created, so it keeps MAX_FILES - 1: the new file
    takes the last slot and the folder ends at MAX_FILES.
    """
    try:
        files = sorted(folder.glob("*.log"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return

    cutoff = (datetime.now() - MAX_AGE).timestamp()
    kept: list[Path] = []
    for path in files:
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
            else:
                kept.append(path)
        except OSError:
            continue

    oldest_first = kept[: max(0, len(kept) - (MAX_FILES - 1))]
    for path in oldest_first:
        try:
            path.unlink()
        except OSError:
            continue
