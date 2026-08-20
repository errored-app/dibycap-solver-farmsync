"""§5.3: the close question, from the window's own X to the dialog on screen.

Nothing here renders a page. The question is a plain object with three
constructor arguments — is a run going, how to stop it, how to close the window
— so the whole of spec 5.3 is tested without a window and without an engine.

`tests/test_home_control_room.py` keeps the half that needs a rendered Home: the
dialog Home builds and the two buttons in it.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from farmsync_solver.engine.snapshot import RunState
from farmsync_solver.ui import closing
from tests.fakes import FakeResponse

PAGE_URL = "http://127.0.0.1:8123/"


class FakeDialog:
    """The two members of a NiceGUI dialog the question touches."""

    def __init__(self, is_deleted: bool = False) -> None:
        self.opens = 0
        self.is_deleted = is_deleted

    def open(self) -> None:
        self.opens += 1


def _question(running: bool = False) -> tuple[closing.CloseQuestion, list[str]]:
    """A question and the list its two dangerous steps write into."""
    done: list[str] = []
    question = closing.CloseQuestion(
        is_running=lambda: running,
        stop=lambda: done.append("stop"),
        shutdown=lambda: done.append("close"),
    )
    return question, done


def _ctrl(key: str, keydown: bool = True, ctrl: bool = True) -> Any:
    """One `ui.keyboard` event, down to the three members `on_key` reads."""
    return SimpleNamespace(
        action=SimpleNamespace(keydown=keydown),
        modifiers=SimpleNamespace(ctrl=ctrl),
        key=SimpleNamespace(name=key),
    )


# --- which runs are asked about ---------------------------------------------


def test_an_idle_app_closes_without_a_question() -> None:
    assert closing.should_confirm_close(RunState.IDLE) is False


@pytest.mark.parametrize(
    "state",
    [RunState.DISCOVERING, RunState.SOLVING, RunState.RESTING, RunState.WAITING, RunState.STOPPING],
)
def test_a_run_in_progress_is_asked_about_first(state: RunState) -> None:
    assert closing.should_confirm_close(state) is True


# --- the question itself -----------------------------------------------------


def test_an_idle_app_lets_the_window_go() -> None:
    question, _ = _question(running=False)
    dialog = FakeDialog()
    question.register(dialog)

    assert question.close_or_ask() is True
    assert dialog.opens == 0


def test_a_run_puts_the_question_on_screen_instead() -> None:
    question, _ = _question(running=True)
    dialog = FakeDialog()
    question.register(dialog)

    assert question.close_or_ask() is False
    assert dialog.opens == 1


def test_no_screen_yet_means_nothing_to_ask() -> None:
    """Setup is on screen, or the window is still opening. The X just closes."""
    question, _ = _question(running=True)

    assert question.close_or_ask() is True


def test_a_screen_that_has_left_the_page_asks_nothing() -> None:
    question, _ = _question(running=True)
    question.register(FakeDialog())

    question.forget_screen()

    assert question.close_or_ask() is True


def test_a_deleted_dialog_never_traps_the_window() -> None:
    """A window nobody can close is the worse of the two failures."""
    question, _ = _question(running=True)
    question.register(FakeDialog(is_deleted=True))

    assert question.close_or_ask() is True


def test_the_answer_already_given_holds() -> None:
    """Closing the window fires `closing` again, and by then the run is Stopping."""
    question, _ = _question(running=True)
    question.register(FakeDialog())
    question.stop_and_close()

    assert question.close_or_ask() is True


# --- answering it ------------------------------------------------------------


def test_stop_and_close_stops_the_run_before_the_window_goes() -> None:
    question, done = _question(running=True)

    question.stop_and_close()

    assert done == ["stop", "close"]


# --- Ctrl+W, the gesture the window does not handle --------------------------


def test_ctrl_w_closes_an_idle_app() -> None:
    question, done = _question(running=False)

    question.on_key(_ctrl("w"))

    assert done == ["close"]


def test_ctrl_w_raises_the_same_question_the_x_does() -> None:
    question, done = _question(running=True)
    dialog = FakeDialog()
    question.register(dialog)

    question.on_key(_ctrl("w"))

    assert dialog.opens == 1
    assert done == []


@pytest.mark.parametrize(
    "event",
    [_ctrl("q"), _ctrl("w", ctrl=False), _ctrl("w", keydown=False)],
)
def test_every_other_key_is_left_alone(event: Any) -> None:
    question, done = _question(running=False)

    question.on_key(event)

    assert done == []


# --- the one question this process holds -------------------------------------


def test_the_process_holds_one_question() -> None:
    closing.forget()

    assert closing.current() is closing.current()


def test_forgetting_it_starts_a_fresh_one() -> None:
    """One test's answered question must not outlive it."""
    closing.forget()
    first = closing.current()

    closing.forget()

    assert closing.current() is not first


# --- the HTTP adapter: the door the window process knocks on ------------------


async def test_the_route_hands_the_window_the_question_s_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question, _ = _question(running=True)
    question.register(FakeDialog())
    monkeypatch.setattr(closing, "current", lambda: question)

    assert await closing.answer_close_request() == {"close": False}


async def test_an_app_with_nothing_to_ask_says_close(monkeypatch: pytest.MonkeyPatch) -> None:
    question, _ = _question(running=False)
    monkeypatch.setattr(closing, "current", lambda: question)

    assert await closing.answer_close_request() == {"close": True}


def test_mounting_opens_both_doors(monkeypatch: pytest.MonkeyPatch) -> None:
    """The route the window knocks on, and the hook that makes it knock."""
    from nicegui import app as ui_app

    monkeypatch.setattr(ui_app.native, "start_args", {})
    closing.mount()

    routes = {getattr(route, "path", "") for route in ui_app.routes}
    assert closing.CLOSE_ROUTE in routes
    assert ui_app.native.start_args["func"] is closing.bind


# --- the webview adapter: the handler in the window process -------------------


class FakeEvent:
    """pywebview's `Event`, down to the `+=` the binding uses."""

    def __init__(self) -> None:
        self.handlers: list[Any] = []

    def __iadd__(self, handler: Any) -> "FakeEvent":
        self.handlers.append(handler)
        return self


class FakeEvents:
    def __init__(self) -> None:
        self.closing = FakeEvent()


class FakeWindow:
    """The two members of a pywebview window this module touches."""

    def __init__(self, url: str = PAGE_URL) -> None:
        self.original_url = url
        self.events = FakeEvents()


class FakePost:
    """Stands in for `requests.post`. Answers the same thing every time."""

    def __init__(self, answer: Any) -> None:
        self.answer = answer
        self.calls: list[tuple[str, float | None]] = []

    def __call__(self, url: str, timeout: float | None = None, **kwargs: Any) -> Any:
        self.calls.append((url, timeout))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_binding_hangs_the_question_on_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    import webview

    window = FakeWindow()
    monkeypatch.setattr(webview, "windows", [window])

    closing.bind()

    assert window.events.closing.handlers == [closing.ask_first]


def test_the_handler_takes_the_window_pywebview_hands_it() -> None:
    """pywebview passes the window only to a handler whose parameter says so."""
    import inspect

    assert "window" in inspect.signature(closing.ask_first).parameters


def test_the_binding_survives_the_spawn_to_the_window_process() -> None:
    """NiceGUI pickles `start_args`, and drops any value that will not go."""
    import pickle

    assert pickle.loads(pickle.dumps(closing.bind)) is closing.bind


def test_a_run_in_progress_keeps_the_window_open(monkeypatch: pytest.MonkeyPatch) -> None:
    _answer(monkeypatch, FakeResponse(payload={"close": False}))

    assert closing.ask_first(FakeWindow()) is False


def test_an_app_that_says_close_lets_the_window_go(monkeypatch: pytest.MonkeyPatch) -> None:
    _answer(monkeypatch, FakeResponse(payload={"close": True}))

    assert closing.ask_first(FakeWindow()) is None


def test_it_asks_the_page_the_window_is_showing(monkeypatch: pytest.MonkeyPatch) -> None:
    post = _answer(monkeypatch, FakeResponse(payload={"close": True}))

    closing.ask_first(FakeWindow("http://127.0.0.1:8123/"))

    assert post.calls == [
        ("http://127.0.0.1:8123" + closing.CLOSE_ROUTE, closing.ASK_TIMEOUT_SECONDS)
    ]


@pytest.mark.parametrize(
    "answer",
    [
        RuntimeError("no server"),
        FakeResponse(status_code=500, payload={"close": False}),
        FakeResponse(payload=None),
        FakeResponse(payload={}),
    ],
)
def test_an_app_that_does_not_answer_never_traps_the_window(
    answer: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A window that cannot be closed is worse than a question that is not asked."""
    _answer(monkeypatch, answer)

    assert closing.ask_first(FakeWindow()) is None


def _answer(monkeypatch: pytest.MonkeyPatch, answer: Any) -> FakePost:
    """Put `answer` behind the one HTTP call this module makes."""
    post = FakePost(answer)
    monkeypatch.setattr(closing.requests, "post", post)
    return post
