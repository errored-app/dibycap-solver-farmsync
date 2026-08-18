"""Stand-ins for a requests/curl_cffi session, shared by the client tests."""
from __future__ import annotations

from typing import Any


class FakeResponse:
    """Stands in for a requests/curl_cffi response."""

    def __init__(self, status_code: int = 200, payload: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class Queue:
    """Answers a different response on each call, then holds the last one.

    For a call that polls: `solve` asks `/getTask` until the task is finished.
    """

    def __init__(self, *responses: FakeResponse) -> None:
        self._responses = list(responses)

    def __call__(self) -> FakeResponse:
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


class FakeSession:
    """Records what it was asked for and answers from one canned response.

    An answer may be a response, an exception to raise, a `Queue`, or a
    URL -> answer table for a call that makes more than one request.
    """

    def __init__(self, answers: FakeResponse | Exception | dict[str, Any]) -> None:
        self.answers = answers
        self.response = answers  # the single-answer name, for readability
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []
        self.bodies: list[Any] = []
        self.trust_env = True

    @property
    def urls(self) -> list[str]:
        return [url for _, url in self.calls]

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.sent_headers = kwargs.get("headers", {})
        self.bodies.append(kwargs.get("json"))
        return self._answer("POST", url)

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._answer("GET", url)

    def _answer(self, method: str, url: str) -> FakeResponse:
        self.calls.append((method, url))
        answer = self.answers[url] if isinstance(self.answers, dict) else self.answers
        if callable(answer):
            answer = answer()
        if isinstance(answer, Exception):
            raise answer
        return answer
