r"""The only reader of %APPDATA%\FarmsyncSolver\config.json and DPAPI.

Spec 10. Three rules shape this module:

- Nothing else in the app knows the path, the file shape, or DPAPI.
- The file holds exactly five fields. `place_id`, `threads` and `round_delay`
  are gone: two were dead, and the thread count is derived, never stored.
- Missing, unparseable and undecryptable all collapse to one behaviour: the bad
  value becomes empty, the app shows Setup. `load` never raises.
"""
from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
from ctypes import wintypes
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from . import looks
from ._version import APP_NAME

CONFIG_VERSION = 1
DEFAULT_SPEED_PERCENT = 100
SPEED_CHOICES = (25, 50, 75, 100)

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    """What the app remembers between launches. Keys are plain text in memory."""

    api_key: str = ""
    farm_token: str = ""
    speed_percent: int = DEFAULT_SPEED_PERCENT
    theme: str = looks.DEFAULT

    @property
    def is_ready(self) -> bool:
        """True when both keys are present, so Setup can be skipped."""
        return bool(self.api_key and self.farm_token)


def default_path() -> Path:
    r"""`%APPDATA%\FarmsyncSolver\config.json`, per Windows user."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / APP_NAME / "config.json"


def load(path: Path | None = None) -> Config:
    """Read the file once at startup. Any trouble reads as an empty value."""
    target = _target(path)

    try:
        raw: Any = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Config()

    if not isinstance(raw, dict):
        _log.warning("config is not an object; starting fresh")
        return Config()

    return Config(
        api_key=_read_secret(raw.get("api_key"), "api_key"),
        farm_token=_read_secret(raw.get("farm_token"), "farm_token"),
        speed_percent=_read_speed(raw.get("speed_percent")),
        theme=_read_theme(raw.get("theme")),
    )


def save(config: Config, path: Path | None = None) -> None:
    """Write the file atomically: a temp file beside it, then a replace."""
    target = _target(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    body = json.dumps(
        {
            "version": CONFIG_VERSION,
            "api_key": _protect(config.api_key),
            "farm_token": _protect(config.farm_token),
            "speed_percent": config.speed_percent,
            "theme": config.theme,
        },
        indent=2,
    )

    temporary = target.with_name(target.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(body)
    temporary.replace(target)


def save_speed(percent: int, path: Path | None = None) -> Config:
    """Spec 4.3: save one of the four Speed choices, keeping the keys as they are.

    The file is re-read rather than taken from a caller's copy: only the speed is
    changing, and the file is the newest word on the keys.
    """
    if percent not in SPEED_CHOICES:
        raise ValueError(f"speed_percent={percent!r} is not one of {SPEED_CHOICES}")

    saved = replace(load(path), speed_percent=percent)
    save(saved, path)
    _log.info("speed saved percent=%s", percent)
    return saved


def save_theme(theme: str, path: Path | None = None) -> Config:
    """Save the picked look, keeping everything else as it is.

    Same shape as `save_speed`, and same reason for re-reading the file: only
    the theme is changing, and the file is the newest word on the rest.

    Unlike the keys and Speed this one is allowed to change mid-run (ADR 0004):
    a theme touches nothing the engine is doing.
    """
    if theme not in looks.LOOKS:
        raise ValueError(f"theme={theme!r} is not one of {tuple(looks.LOOKS)}")

    saved = replace(load(path), theme=theme)
    save(saved, path)
    _log.info("theme saved theme=%s", theme)
    return saved


def forget_keys(path: Path | None = None) -> Config:
    """Spec 4.3: drop both keys, keep the speed, and answer with what survives.

    A rewrite rather than a delete: the file keeps the speed the user picked, and
    the app lands on Setup because the keys are gone, not because a file is.
    """
    kept = load(path)
    remaining = Config(speed_percent=kept.speed_percent, theme=kept.theme)
    save(remaining, path)
    _log.info("keys forgotten")
    return remaining


def _target(path: Path | None) -> Path:
    return path if path is not None else default_path()


def _read_secret(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        return ""
    plain = _unprotect(value)
    if plain is None:
        _log.warning("config %s could not be decrypted; asking for it again", field)
        return ""
    return plain


def _read_speed(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value in SPEED_CHOICES:
        return value
    return DEFAULT_SPEED_PERCENT


def _read_theme(value: object) -> str:
    """A theme nobody ships reads as the default rather than as a broken file.

    A file written by a newer version, or edited by hand, must not leave the app
    with no look at all: the worst it can do is put the user back on Modern.
    """
    if isinstance(value, str) and value in looks.LOOKS:
        return value
    return looks.DEFAULT


# --- Windows DPAPI, current-user scope, value level -------------------------
#
# ctypes rather than a dependency: two calls, both in crypt32.dll, both on every
# supported Windows. The blob is base64'd so the file itself stays readable JSON.


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


# Loaded with use_last_error so a failure carries a real Windows error number,
# and with the pointer types spelled out so nothing is truncated on 64-bit.
_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_crypt32.CryptProtectData.restype = wintypes.BOOL
_crypt32.CryptUnprotectData.restype = wintypes.BOOL
_kernel32.LocalFree.argtypes = [ctypes.c_void_p]
_kernel32.LocalFree.restype = ctypes.c_void_p


def _blob_bytes(blob: _Blob) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _free(blob: _Blob) -> None:
    if blob.pbData:
        _kernel32.LocalFree(blob.pbData)


def _protect(plain: str) -> str:
    """Encrypt a key for this Windows user. Empty stays empty."""
    if not plain:
        return ""

    data = plain.encode("utf-8")
    source = _Blob(len(data), ctypes.create_string_buffer(data, len(data)))
    result = _Blob()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), "CryptProtectData failed")

    try:
        return base64.b64encode(_blob_bytes(result)).decode("ascii")
    finally:
        _free(result)


def _unprotect(stored: str) -> str | None:
    """Decrypt a stored key. None when the value is not ours to read."""
    try:
        data = base64.b64decode(stored, validate=True)
    except (ValueError, TypeError):
        return None

    source = _Blob(len(data), ctypes.create_string_buffer(data, len(data)))
    result = _Blob()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)
    )
    if not ok:
        return None

    try:
        return _blob_bytes(result).decode("utf-8")
    except UnicodeDecodeError:
        return None
    finally:
        _free(result)
