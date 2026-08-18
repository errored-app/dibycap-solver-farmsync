r"""Copy diagnostics and Open log folder: the whole support path (spec 8.4).

Something went wrong, the user presses one button in Settings, and pastes the
result into a chat. What they paste is a short header plus the tail of the log
this run is writing — a copy for pasting, not the whole file.

Two rules shape this module:

- It never raises. A missing folder, a locked file or a dead Explorer still
  leaves the user with something to paste.
- It never reads a secret. The header takes plain display values from the
  screen, and the log has no cookie or key in it by construction (spec 8.2).
"""
from __future__ import annotations

import logging
import platform
import subprocess
from pathlib import Path

from ._version import APP_NAME, VERSION
from .logging_setup import current_file, default_log_dir

TAIL_LINES = 200
NO_LOG = "no log file for this run"

_log = logging.getLogger(__name__)


def tail(path: Path | None, limit: int = TAIL_LINES) -> list[str]:
    """The last `limit` lines of a log file. An unreadable file gives none.

    The file is read whole. A run log is pruned at 7 days and 20 files and holds
    one short line per account, so seeking backwards would buy nothing.
    """
    if path is None:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-limit:]


def bundle(
    run_state: str,
    key_check: str,
    credit: str,
    speed_percent: int,
    log_file: Path | None = None,
) -> str:
    """The header plus the log tail, ready for the clipboard.

    The four run facts are passed in as the words already on screen rather than
    read back out of the engine and the config: what the maintainer needs to see
    is what the user was looking at when they pressed the button.
    """
    path = log_file if log_file is not None else current_file()
    lines = tail(path)

    header = [
        f"{APP_NAME} {VERSION}",
        f"Windows: {_windows_version()}",
        f"Run state: {run_state}",
        f"Key check: {key_check}",
        f"Credit: {credit}",
        f"Speed: {speed_percent}%",
        f"Log: {path.name if path else NO_LOG}",
    ]
    if not lines:
        return "\n".join([*header, "", NO_LOG])
    return "\n".join([*header, "", *lines])


def open_log_folder(folder: Path | None = None) -> bool:
    """Open Explorer at the log folder, newest file selected. False if it did not.

    `explorer /select,<file>` is what puts the newest run at the top of what the
    user sees; with no file yet, the folder alone is opened. Explorer answers a
    non-zero exit code even when it worked, so the code is not checked — only a
    failure to launch it at all counts as a no.

    A folder that is not there is a no, not something to create: logging makes
    that folder, and a button that made it too would hide a run with no log.
    """
    target = folder if folder is not None else default_log_dir()
    if not target.is_dir():
        return False

    try:
        newest = _newest_log(target)
        command = ["explorer", f"/select,{newest}"] if newest else ["explorer", str(target)]
        subprocess.run(command, check=False)
    except OSError as error:
        _log.warning("open log folder failed error=%s", type(error).__name__)
        return False
    return True


def _newest_log(folder: Path) -> Path | None:
    try:
        files = sorted(folder.glob("*.log"), key=lambda path: path.stat().st_mtime)
    except OSError:
        return None
    return files[-1] if files else None


def _windows_version() -> str:
    """The Windows build, for a bug that only happens on one of them."""
    try:
        return platform.platform()
    except Exception:  # platform reads the registry; it must not break a paste
        return "unknown"
