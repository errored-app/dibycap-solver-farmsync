"""Spec 5.3: the window's own X asks the app before it drops a run.

NiceGUI does not bridge pywebview's vetoable `closing` event — its
`native_mode.py` says so, because a veto needs a synchronous round-trip. So this
module hangs the handler on the event itself.

The window lives in its own spawned process, and the one hook into that process
is `app.native.start_args`: NiceGUI hands it straight to `webview.start`, and
pywebview calls that `func` once the GUI loop is up. `bind` is that `func`.

The handler knows nothing about the run. It asks the server over the same
localhost URL the window is already showing, and does what the answer says. An
app that does not answer gets its window closed: a window that cannot be closed
is worse than a question that is not asked, and the polite stop hung on shutdown
still catches the run either way.
"""
from __future__ import annotations

import logging

import requests

# Mounted on the NiceGUI server by `ui/app.py`. Underscored, because it is a
# door for the window process and not part of any page.
CLOSE_ROUTE = "/_window-closing"
ASK_TIMEOUT_SECONDS = 3.0

# pywebview cancels the close when a handler answers False, and lets it through
# on anything else.
VETO = False
ALLOW = None

_log = logging.getLogger(__name__)


def bind() -> None:
    """Hang the question on the window's X. Runs in the window process."""
    import webview  # here, not at the top: the server process has no window

    webview.windows[0].events.closing += ask_first
    _log.info("the window X now asks before it closes")


def ask_first(window: object) -> bool | None:
    """pywebview's `closing` handler. The parameter name is what feeds it the window."""
    return ALLOW if ask_the_app(_door(window)) else VETO


def _door(window: object) -> str:
    """The close route on the server the window is showing."""
    page_url = getattr(window, "original_url", "") or ""
    return page_url.rstrip("/") + CLOSE_ROUTE


def ask_the_app(url: str) -> bool:
    """Ask over HTTP. True closes the window, False leaves the question on screen."""
    try:
        answer = requests.post(url, timeout=ASK_TIMEOUT_SECONDS)
        if answer.status_code != 200:
            raise RuntimeError(f"the app answered {answer.status_code}")
        return bool(answer.json()["close"])
    except Exception:  # never raises: a raise here would close the window anyway
        _log.warning("the close question did not reach the app; closing", exc_info=True)
        return True
