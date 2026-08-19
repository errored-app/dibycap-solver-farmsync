"""One running copy at a time (spec 11.3).

Two copies would both open — the port is auto-picked, so nothing stops them —
and both would spend solves on the same accounts. A named Windows mutex, taken
at startup, is what stops that.

The same name is the installer's `AppMutex`: it is how Setup knows the app is
running. Change the name here and the installer stops seeing the app. Setup
*refuses to run* while the mutex is held, so the updater must exit the app
(which drops the mutex) before it starts Setup.
"""
from __future__ import annotations

import ctypes
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
    # use_last_error: ctypes may call Win32 itself between the two calls, so
    # kernel32.GetLastError() can read someone else's error, and a lost 183
    # would let a second copy start. This keeps the error ctypes saved.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    # Without these the HANDLE comes back truncated to a signed 32-bit int, and
    # a handle whose low half is zero would read as a failed call.
    create_mutex.restype = ctypes.c_void_p
    create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)

    handle = create_mutex(None, False, name)
    return (int(handle or 0), ctypes.get_last_error())


def _no_creator(name: str) -> tuple[int, int]:
    """Off Windows there is no mutex, so nothing is ever refused."""
    return (0, 0)


def _default_creator() -> Creator:
    return _windows_creator if sys.platform == "win32" else _no_creator


def claim(create: Creator | None = None, name: str = MUTEX_NAME) -> bool:
    """Take the mutex. False means another copy already holds it."""
    global _handle

    handle, error = (create or _default_creator())(name)
    if handle == 0:
        return True
    if error == ERROR_ALREADY_EXISTS:
        return False
    _handle = handle
    return True


def release() -> None:
    """Drop the mutex. The updater calls this before it starts Setup, which
    refuses to run while the name is taken."""
    global _handle

    if _handle is not None and sys.platform == "win32":
        ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(_handle))
    _handle = None
