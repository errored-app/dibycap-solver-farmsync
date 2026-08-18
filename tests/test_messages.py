"""§9.7: all user-facing wording lives in one table."""
from __future__ import annotations

import pytest

from farmsync_solver.errors import ErrorCode
from farmsync_solver.ui import messages


@pytest.mark.parametrize("code", list(ErrorCode))
def test_every_code_has_a_sentence(code: ErrorCode) -> None:
    sentence = messages.for_code(code)

    assert sentence
    assert code.value not in sentence  # no raw codes on screen
    assert sentence[0].isupper() and sentence.endswith((".", "!"))


def test_an_unknown_code_still_answers() -> None:
    assert messages.for_code(None) == messages.for_code(ErrorCode.UNKNOWN)


def test_the_success_note_shows_the_credit_with_separators() -> None:
    note = messages.key_works({"estimated_solves": 5662})

    assert note == "Key works — 5,662 captchas left"


def test_the_success_note_survives_a_missing_figure() -> None:
    assert messages.key_works({}) == "Key works — 0 captchas left"
