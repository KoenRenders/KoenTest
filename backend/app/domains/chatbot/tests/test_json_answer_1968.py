"""An answer in a fixed shape: asked for as JSON, retried once, logged without content (#1968).

Raakje answered "geen bruikbaar voorstel" twice in a row on production
(13 October 2026): the calls were fine, the answers short, and nothing had
asked the provider for JSON, tried again or kept a trace of what was wrong.
`chatbot/answers.py` is the one rule since; this file holds it, with the
provider scripted — no call leaves the machine.

Broken on purpose (13 October 2026, each put back):
- `json_answer`: the second `_ask` taken out, the first answer parsed twice →
  "asked once more" fails (one call where two are expected);
- `json_answer`: the retry made a loop of three → "one retry, not a loop";
- the log line given the answer's text (`fault.reason` replaced by `text`) →
  "the answer's text is in the log";
- `MistralProvider.complete`: the `response_format` line out → "the JSON setting
  is not in the request";
- `GuardedProvider.complete`: the setting sent on every call → "a free-text
  chat's request changed".
"""

import json
import logging

import pytest

from app.domains.chatbot import answers
from app.domains.chatbot.answers import UnusableAnswer, json_answer, parse_json_object
from app.domains.chatbot.models import AiCapability, AiSurface
from app.domains.chatbot.providers.base import AssistantMessage
from app.domains.chatbot.providers.mistral import MistralProvider
from app.domains.chatbot.seam import GuardedProvider, GuardRules

MARKER = "kersenvlaai"
MESSAGES = [{"role": "system", "content": "Antwoord in JSON."}, {"role": "user", "content": "Doe."}]


class Scripted:
    """Answers in order and keeps how each call was asked."""

    name = "mock"
    model = "scripted"
    log_name = "admin/newsletter_drafting"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def complete(self, messages, tools=None, tool_choice=None, json_answer=False):
        self.calls.append({"messages": list(messages), "tools": tools, "json_answer": json_answer})
        return AssistantMessage(content=self.replies.pop(0))


# ── the parser, with its reason ──────────────────────────────────────────────


def test_an_object_parses_also_inside_prose_or_a_code_fence():
    assert parse_json_object('{"reply": "ok"}') == {"reply": "ok"}
    assert parse_json_object('Hier is het:\n```json\n{"reply": "ok"}\n```\nSucces!') == {
        "reply": "ok"
    }


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (f"Dat weet ik niet, {MARKER}.", "no object found"),
        ("", "no object found"),
        (None, "no object found"),
        (f'["{MARKER}"]', "not an object"),
        (f'[{{"reply": "{MARKER}"}}]', "not an object"),
        ("12", "not an object"),
        (f'{{"reply": "{MARKER}", "paragraphs": ["een", }}', "invalid at position"),
        (f'{{"reply": "{MARKER}', "no object found"),
    ],
)
def test_what_is_no_object_says_why_and_never_what(text, reason):
    with pytest.raises(UnusableAnswer) as refused:
        parse_json_object(text)
    assert refused.value.reason.startswith(reason)
    assert MARKER not in str(refused.value) and MARKER not in refused.value.reason


def test_the_position_of_an_invalid_object_counts_from_the_answers_start():
    text = 'Zie: {"a": 1, }'
    with pytest.raises(UnusableAnswer) as refused:
        parse_json_object(text)
    position = int(refused.value.reason.rsplit(" ", 1)[1])
    # Where exactly the parser stops differs per Python version (the comma or
    # the brace after it); that it counts the five characters before the object
    # does not.
    assert text[:position].startswith('Zie: {"a": 1') and position < len(text), (
        "the position points into the answer as it was received"
    )


# ── asked for as JSON, retried once ──────────────────────────────────────────


def test_a_good_answer_is_one_call_that_asks_for_json_without_tools():
    provider = Scripted('{"reply": "ok"}')
    assert json_answer(provider, MESSAGES) == {"reply": "ok"}
    assert provider.calls == [{"messages": MESSAGES, "tools": None, "json_answer": True}]


@pytest.mark.parametrize(
    "bad", ["Dat weet ik niet.", '{"reply": "half', '["een", "twee"]', '{"a": 1, }']
)
def test_an_answer_that_does_not_parse_is_asked_once_more(bad):
    provider = Scripted(bad, '{"reply": "tweede keer"}')
    assert json_answer(provider, MESSAGES) == {"reply": "tweede keer"}
    assert len(provider.calls) == 2, "asked once more"
    assert provider.calls[0] == provider.calls[1], "the same request, the second time"


def test_the_second_failure_is_the_end_one_retry_not_a_loop():
    provider = Scripted("Nee.", "Nog altijd niet.", '{"reply": "te laat"}')
    with pytest.raises(UnusableAnswer):
        json_answer(provider, MESSAGES)
    assert len(provider.calls) == 2, "one retry, not a loop"


def test_a_tool_loops_answer_is_the_first_attempt_and_the_retry_has_no_tools():
    """The newsletter's proposal: its answer came from the loop, which offers the
    tools. Parsed as it is when it parses — no call; else one call without tools
    and with the JSON setting."""
    provider = Scripted('{"reply": "uit de retry"}')
    assert json_answer(provider, MESSAGES, first='{"reply": "uit de lus"}') == {
        "reply": "uit de lus"
    }
    assert provider.calls == []
    assert json_answer(provider, MESSAGES, first="Hier is je brief!") == {"reply": "uit de retry"}
    assert provider.calls == [{"messages": MESSAGES, "tools": None, "json_answer": True}]


# ── logged without content ───────────────────────────────────────────────────


def _lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == answers.logger.name]


def test_a_failure_is_logged_with_its_reason_and_length_and_none_of_the_answer(caplog):
    first = f"Dat weet ik niet, {MARKER}."
    second = f'{{"reply": "{MARKER}", }}'
    with caplog.at_level(logging.WARNING, logger=answers.logger.name):
        with pytest.raises(UnusableAnswer):
            json_answer(Scripted(first, second), MESSAGES)
    lines = _lines(caplog)
    assert len(lines) == 2
    assert "admin/newsletter_drafting" in lines[0] and "attempt 1 of 2" in lines[0]
    assert f"{len(first)} characters" in lines[0] and "no object found" in lines[0]
    assert "attempt 2 of 2" in lines[1] and f"{len(second)} characters" in lines[1]
    assert "invalid at position" in lines[1]
    assert MARKER not in "\n".join(lines), "the answer's text is in the log"
    assert MARKER not in json.dumps([str(r.args) for r in caplog.records])


def test_a_failure_the_retry_repaired_is_in_the_log_too(caplog):
    with caplog.at_level(logging.WARNING, logger=answers.logger.name):
        json_answer(Scripted(f"Geen JSON, {MARKER}.", '{"reply": "ok"}'), MESSAGES)
    lines = _lines(caplog)
    assert len(lines) == 2 and "attempt 1 of 2" in lines[0]
    assert "parsed on the retry" in lines[1] and "admin/newsletter_drafting" in lines[1]
    assert MARKER not in "\n".join(lines)


def test_a_good_answer_logs_nothing(caplog):
    with caplog.at_level(logging.WARNING, logger=answers.logger.name):
        json_answer(Scripted('{"reply": "ok"}'), MESSAGES)
    assert _lines(caplog) == []


# ── the seam sends the setting, and only when asked ──────────────────────────


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"id": "r1", "choices": [{"message": {"content": "{}"}}], "usage": {}}


def _requests(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    def post(url, headers=None, json=None, timeout=None):
        sent.append(json)
        return _Response()

    monkeypatch.setattr("app.domains.chatbot.providers.mistral.httpx.post", post)
    return sent


def test_the_provider_asks_for_a_json_object_only_for_a_json_answer(monkeypatch):
    sent = _requests(monkeypatch)
    provider = MistralProvider(api_key="test-sleutel", model="klein")
    provider.complete(MESSAGES, json_answer=True)
    provider.complete(MESSAGES)
    provider.complete(MESSAGES, tools=[{"type": "function", "function": {"name": "x"}}])
    assert sent[0]["response_format"] == {"type": "json_object"}, (
        "the JSON setting is not in the request"
    )
    assert "response_format" not in sent[1] and "response_format" not in sent[2], (
        "a free-text chat's request changed"
    )
    assert "tools" not in sent[0] and sent[2]["tool_choice"] == "auto"


def test_the_guard_passes_the_setting_on_and_leaves_a_chat_as_it_was():
    """The guarded provider is what every caller holds. A stand-in that knows
    nothing of the setting still answers a free-text chat: nothing is sent it
    did not get before."""

    class Old:
        name = "mock"
        model = "oud"

        def __init__(self):
            self.kwargs: list[dict] = []

        def complete(self, messages, tools=None, tool_choice=None, **more):
            self.kwargs.append(more)
            return AssistantMessage(content="{}")

    inner = Old()
    rules = GuardRules(surface=AiSurface.ADMIN, capability=AiCapability.NEWSLETTER_DRAFTING)
    guarded = GuardedProvider(inner, rules)
    guarded.complete(MESSAGES)
    guarded.complete(MESSAGES, json_answer=True)
    assert inner.kwargs == [{}, {"json_answer": True}], "a free-text chat's request changed"
    assert guarded.log_name == "admin/newsletter_drafting"
    assert json_answer(guarded, MESSAGES) == {}
