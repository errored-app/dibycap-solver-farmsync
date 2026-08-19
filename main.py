"""nicegui-pack entry point.

`freeze_support()` must be the first statement in the `__main__` block, or the
frozen exe respawns itself forever on Windows (spec 3).
"""
from __future__ import annotations

import logging
import multiprocessing
import sys
from pathlib import Path

from farmsync_solver import logging_setup, single_instance
from farmsync_solver._version import APP_NAME, VERSION
from farmsync_solver.errors import AppError

SELFTEST_FLAG = "--selftest"

_log = logging.getLogger(__name__)


def run(argv: list[str], log_dir: Path | None = None) -> int:
    """Start the app. Returns the process exit code."""
    logging_setup.configure(log_dir=log_dir)
    selftest = SELFTEST_FLAG in argv
    _log.info("start app=%s version=%s selftest=%s", APP_NAME, VERSION, selftest)

    # Before the window. --selftest opens no window and spends nothing, so it
    # takes no mutex and never trips over a copy that is already running.
    if not selftest and not single_instance.claim():
        _log.warning("second launch refused: the app is already running")
        return 0

    try:
        # Imported here, not at module top: the UI pulls in NiceGUI, and an
        # import-time failure there must land in a log file that already exists.
        from farmsync_solver.ui import app

        if selftest:
            _log.info("selftest ok")
            return 0
        app.start_window()
    except Exception as error:  # a crash must leave evidence, then exit non-zero
        _log.critical("startup failed code=%s", AppError.from_exception(error).code.value, exc_info=error)
        return 1
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(run(sys.argv[1:]))
