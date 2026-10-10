"""One question to Raakje (CR-13 phase 4c, #1251).

"A question is not empty" stood at two doors, the public panel and the back-office
assistant, each with its own `if`; "a question has a length" stood at the public
door. Both are `chatbot.service.asked` now, which every surface that asks calls;
the doors show its refusal in the same words.

Proven red (8 October 2026): `if not text:` switched off in `asked` → the empty
questions are not refused; the cap's comparison turned around → a question of the
cap's own length is refused.
"""

import pytest

from app.domains.chatbot.service import QuestionRefused, asked

pytestmark = pytest.mark.ui_agnostisch


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_an_empty_question_is_refused(text):
    with pytest.raises(QuestionRefused, match="Typ eerst een vraag"):
        asked(text)
    with pytest.raises(QuestionRefused, match="Typ eerst een vraag"):
        asked(text, max_chars=10)


def test_a_question_is_trimmed():
    assert asked("  Wanneer is de quiz?\n") == "Wanneer is de quiz?"


def test_a_cap_refuses_what_is_longer_and_takes_what_is_as_long():
    assert asked("a" * 10, max_chars=10) == "a" * 10
    with pytest.raises(QuestionRefused, match="max 10 tekens"):
        asked("a" * 11, max_chars=10)
    # The cap counts what will be asked: the spaces around it are not the question.
    assert asked("  " + "a" * 10 + "  ", max_chars=10) == "a" * 10


def test_a_surface_without_a_cap_takes_a_long_question():
    assert len(asked("a" * 50_000)) == 50_000
