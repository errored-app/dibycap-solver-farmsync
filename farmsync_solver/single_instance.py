"""One running copy at a time (spec 11.3).

Two copies would both open — the port is auto-picked, so nothing stops them —
and both would spend solves on the same accounts. A named Windows mutex, taken
at startup, is what stops that.

The same name is the installer's `AppMutex`: it is how a silent update knows the
app is running. Change the name here and the installer stops seeing the app.
"""
from __future__ import annotations

import sys
from typing import Callable

MUTEX_NAME = "FarmsyncSolverSingleInstance"
ERROR_ALREADY_EXISTS = 183

# Kept for the life of the process. Closing the handle frees the name, and the
# installer would then see no app running.
_handle: int | None = None

# Takes the mutex name, returns (handle, last error). A zero handle means the
# call failed and nothing can be said about other copies.
Creator = Callable[[str], tuple[int, int]]


def _windows_creator(name: str) -> tuple[int, int]:
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.CreateMutexW(None, False, name)
    return (int(handle or 0), int(kernel32.GetLastError()))


def _no_creator(name: str) -> tuple[int, int]:
    """Off Windows there is no mutex, so nothing is ever refused."""
    return (0, 0)


def claim(create: Creator | None = None) -> bool:
    """Take the mutex. False means another copy already holds it."""
    global _handle

    creator = create or (_windows_creator if sys.platform == "win32" else _no_creator)
    handle, error = creator(MUTEX_NAME)
    if handle == 0:
        return True
    if error == ERROR_ALREADY_EXISTS:
        return False
    _handle = handle
    return True
