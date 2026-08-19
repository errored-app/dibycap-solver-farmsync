"""§5.3: the window's own X asks the app first, in the window's own process."""
from __future__ import annotations

from typing import Any

import pytest

from farmsync_solver.ui import close_guard
from tests.fakes import FakeResponse

PAGE_URL = "http://127.0.0.1:8123/"


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


# --- binding the handler ----------------------------------------------------


def test_binding_hangs_the_question_on_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    import webview

    window = FakeWindow()
    monkeypatch.setattr(webview, "windows", [window])

    close_guard.bind()

    assert window.events.closing.handlers == [close_guard.ask_first]


def test_the_handler_takes_the_window_pywebview_hands_it() -> None:
    """pywebview passes the window only to a handler whose parameter says so."""
    import inspect

    assert "window" in inspect.signature(close_guard.ask_first).parameters


def test_the_binding_survives_the_spawn_to_the_window_process() -> None:
    """NiceGUI pickles `start_args`, and drops any value that will not go."""
    import pickle

    assert pickle.loads(pickle.dumps(close_guard.bind)) is close_guard.bind


# --- what the handler answers -----------------------------------------------


def test_a_run_in_progress_keeps_the_window_open(monkeypatch: pytest.MonkeyPatch) -> None:
    _answer(monkeypatch, FakeResponse(payload={"close": False}))

    assert close_guard.ask_first(FakeWindow()) is False


def test_an_idle_app_lets_the_window_go(monkeypatch: pytest.MonkeyPatch) -> None:
    _answer(monkeypatch, FakeResponse(payload={"close": True}))

    assert close_guard.ask_first(FakeWindow()) is None


# --- how it asks ------------------------------------------------------------


def test_it_asks_the_page_the_window_is_showing(monkeypatch: pytest.MonkeyPatch) -> None:
    post = _answer(monkeypatch, FakeResponse(payload={"close": True}))

    close_guard.ask_first(FakeWindow("http://127.0.0.1:8123/"))

    assert post.calls == [("http://127.0.0.1:8123" + close_guard.CLOSE_ROUTE, close_guard.ASK_TIMEOUT_SECONDS)]


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

    assert close_guard.ask_first(FakeWindow()) is None


def _answer(monkeypatch: pytest.MonkeyPatch, answer: Any) -> FakePost:
    """Put `answer` behind the one HTTP call this module makes."""
    post = FakePost(answer)
    monkeypatch.setattr(close_guard.requests, "post", post)
    return post
