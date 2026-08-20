"""Stand-ins for a requests/curl_cffi session, shared by the client tests."""
from __future__ import annotations

from typing import Any


class FakeResponse:
    """Stands in for a requests/curl_cffi response."""

    def __init__(
        self,
        status_code: int = 200,
        payload: Any = None,
        text: str = "",
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.content = content
        self.headers = headers if headers is not None else {}

    def iter_content(self, chunk_size: int = 1) -> Any:
        """A download, in chunks, like requests. The body is `content`."""
        for start in range(0, len(self.content), max(1, chunk_size)):
            yield self.content[start : start + chunk_size]

    def close(self) -> None:
        return None

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class Script:
    """Answers a different thing on each call, then holds the last one.

    An answer that is an exception is raised instead of returned, so one script
    covers "works, then stops working" and "fails twice, then works".
    """

    def __init__(self, *answers: Any) -> None:
        self._answers = list(answers)
        self.calls = 0

    def __call__(self) -> Any:
        self.calls += 1
        answer = self._answers[min(self.calls, len(self._answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer


class Queue(Script):
    """The same replay, named for the call that polls.

    `solve` asks `/getTask` until the task is finished, so its script is a queue
    of responses rather than a list of outcomes.
    """


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
        answer: Any = self.answers[url] if isinstance(self.answers, dict) else self.answers
        if callable(answer):
            answer = answer()
        if isinstance(answer, Exception):
            raise answer
        return answer
