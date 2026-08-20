"""The close question: one module, from the window's X to the dialog on screen.

Spec 5.3 asks one thing — *"A run is going. Stop it and close?"* — and asking it
crosses two processes. The question itself lives here, and the two ways in are
adapters on top of it:

- **webview**, in the window process: `bind` hangs `ask_first` on the window's
  own `closing` event, which posts to the route below and does what it says.
- **HTTP**, on the server: `answer_close_request` is that route, and it is the
  only door the window process has into this one.

Ctrl+W is not a third way in. It reaches the same `CloseQuestion` through
`on_key`, so the keystroke and the X cannot drift apart.

Which runs are asked about is not this module's rule to keep: a run is on
when `RunSnapshot.is_running` says so, and `engine.a_run_is_going` is the
default behind the `is_running` argument below.

One question lives for the life of the process, because Home is rebuilt on every
hop back from Settings while the window's X and the run behind it are older than
any screen. Home does one thing with it: registers the dialog to ask in, and
drops it again when it leaves the page.

The dangerous steps are constructor arguments — whether a run is going, how to
stop it, how to close the window — so the whole of spec 5.3 is tested without a
rendered page.

NiceGUI does not bridge pywebview's vetoable `closing` event: its
`native_mode.py` says so, because a veto needs a synchronous round-trip. The one
hook into the spawned window process is `app.native.start_args`, which NiceGUI
hands straight to `webview.start` — pywebview calls that `func` once the GUI loop
is up, and `bind` is that `func`.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import requests
from nicegui import app as native_app
from nicegui.events import KeyEventArguments

from .. import engine

# Mounted on the NiceGUI server by `mount`. Underscored, because it is a door
# for the window process and not part of any page.
CLOSE_ROUTE = "/_window-closing"
ASK_TIMEOUT_SECONDS = 3.0

# pywebview cancels the close when a handler answers False, and lets it through
# on anything else.
VETO = False
ALLOW = None

_log = logging.getLogger(__name__)


def stop_the_run() -> None:
    """The polite stop of spec 5.2, on whatever engine this process is running."""
    engine.current().stop()


def close_the_window() -> None:
    """Shut the app down.

    Wrapped rather than named in the signature below, so the call is looked up
    when it is made and a test can put its own behind it.
    """
    native_app.shutdown()


class CloseQuestion:
    """One close question, from the gesture that raises it to the app closing."""

    def __init__(
        self,
        is_running: Callable[[], bool] = engine.a_run_is_going,
        stop: Callable[[], Any] = stop_the_run,
        shutdown: Callable[[], Any] = close_the_window,
    ) -> None:
        self._is_running = is_running
        self._stop = stop
        self._shutdown = shutdown
        self._dialog: Any | None = None
        self._answered = False

    def register(self, dialog: Any) -> None:
        """The dialog this screen asks in. Home calls it; nothing else needs to."""
        self._dialog = dialog

    def forget_screen(self) -> None:
        """The screen has left the page. Called before another is drawn over it.

        A stale dialog would refuse the X for a run the user can no longer see.
        """
        self._dialog = None

    def close_or_ask(self) -> bool:
        """Spec 5.3: True closes the window, False puts the question on screen.

        An answer already given holds. Closing the window raises the question a
        second time, and by then the polite stop has left the run Stopping, not
        Idle — asking again would trap the window inside its own dialog. A dialog
        that is no longer on the page cannot ask anything either, and a window
        nobody can close is the worse of the two failures.
        """
        if self._answered or self._dialog is None or self._dialog.is_deleted:
            return True
        if not self._is_running():
            return True
        self._dialog.open()
        return False

    def on_key(self, event: KeyEventArguments) -> None:
        """Ctrl+W is the close gesture the window itself does not handle."""
        if event.action.keydown and event.modifiers.ctrl and event.key.name == "w":
            self.request_close()

    def request_close(self) -> None:
        """A close asked for inside the page: a run is asked about, an idle app goes."""
        if self.close_or_ask():
            self._shutdown()

    def stop_and_close(self) -> None:
        """The user said yes. The polite stop of spec 5.2, then the window goes."""
        self._answered = True
        self._stop()
        self._shutdown()


_question: CloseQuestion | None = None


def current() -> CloseQuestion:
    """The one question this process holds, made on first use."""
    global _question
    if _question is None:
        _question = CloseQuestion()
    return _question


def forget() -> None:
    """Drop the question, so one test's answer cannot outlive it."""
    global _question
    _question = None


def mount() -> None:
    """Open both doors into the question, before the window opens.

    The route and the arming go together: a window armed to knock on a door
    nobody opened would hang for `ASK_TIMEOUT_SECONDS` on every X.
    """
    native_app.post(CLOSE_ROUTE)(answer_close_request)
    native_app.native.start_args["func"] = bind


async def answer_close_request() -> dict[str, bool]:
    """Spec 5.3: the window's X, asking whether it may close.

    The window process cannot see the run, and the screen cannot see the X. This
    route is the round-trip between them.

    Async on purpose: it opens a dialog, and a dialog opened off the event loop
    would sit in the outbox until the next refresh pushed it out.
    """
    return {"close": current().close_or_ask()}


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
    """Ask over HTTP. True closes the window, False leaves the question on screen.

    An app that does not answer gets its window closed: a window that cannot be
    closed is worse than a question that is not asked, and the polite stop hung
    on shutdown still catches the run either way.
    """
    try:
        answer = requests.post(url, timeout=ASK_TIMEOUT_SECONDS)
        if answer.status_code != 200:
            raise RuntimeError(f"the app answered {answer.status_code}")
        return bool(answer.json()["close"])
    except Exception:  # never raises: a raise here would close the window anyway
        _log.warning("the close question did not reach the app; closing", exc_info=True)
        return True
