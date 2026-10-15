"""The port applies the register's classification to the values a module hands it (CR-33 T6).

`GuardedProvider.complete(fields=…)`, and so `run_chat` and `json_answer`, which pass them
through. Each test can go red for its own reason: a NONE key sent, a tokenised value sent as
itself, an internal key accepted on the public surface, an unknown key accepted, a refusal
that names the value or is not logged, a rendering that ignores the marker.

Proven red on 15 October 2026 by ADDING the violation: the NONE branch of `render_fields`
taken out → `test_a_none_key_is_refused_before_the_call_and_logged_by_its_key` fails with the
call made; the `TOKENISED` branch sending the value → the token test fails on the secret
string in the payload.
"""

import pytest

from app.domains.chatbot.answers import json_answer
from app.domains.chatbot.fields import FIELDS_MARK, Field, FieldRefused, place_fields, render_fields
from app.domains.chatbot.models import AiCapability
from app.domains.chatbot.providers.base import AssistantMessage, LLMProvider
from app.domains.chatbot.seam import GuardedProvider, admin_rules, public_rules
from app.domains.chatbot.service import run_chat
from app.kernel import attributes as reg
from app.kernel.attributes import AiExposure, Attribute


class Recorder(LLMProvider):
    name = "recorder"

    def __init__(self, answer: str = "ok") -> None:
        self.calls: list[list[dict]] = []
        self.answer = answer

    def complete(self, messages, tools=None, tool_choice=None, json_answer=False):
        self.calls.append([dict(m) for m in messages])
        return AssistantMessage(content=self.answer)


@pytest.fixture(autouse=True)
def probe_attributes(monkeypatch):
    monkeypatch.setattr(reg, "_REGISTRY", dict(reg._REGISTRY))
    for field, level, label in (
        ("pub", AiExposure.PUBLIC, "Openbaar"),
        ("internal", AiExposure.INTERNAL, "Intern"),
        ("token", AiExposure.TOKENISED, "Persoon"),
        ("none", AiExposure.NONE, "Geheim"),
    ):
        Attribute(
            key=f"probe.thing.{field}",
            columns=(),
            label=label,
            name_en=field,
            help=f"A probe datum, {field}.",
            ai_exposure=level,
        )


def _admin(inner, names=lambda: set(), sink=None):
    return GuardedProvider(
        inner,
        admin_rules(names, capability=AiCapability.ACTIVITY_DRAFTING, scan_prompt_names=False),
        sink,
    )


def _public(inner, sink=None):
    return GuardedProvider(inner, public_rules(), sink)


def _messages():
    return [
        {"role": "system", "content": "S"},
        {"role": "user", "content": f"Gegevens:\n{FIELDS_MARK}"},
    ]


def test_public_and_internal_values_pass_on_the_back_office_surface():
    inner = Recorder()
    _admin(inner).complete(
        _messages(), fields=[("probe.thing.pub", "een"), ("probe.thing.internal", "twee")]
    )
    sent = inner.calls[0][1]["content"]
    assert "Openbaar: een" in sent and "Intern: twee" in sent and FIELDS_MARK not in sent


def test_a_none_key_is_refused_before_the_call_and_logged_by_its_key():
    inner, logged = Recorder(), []
    provider = _admin(inner, sink=lambda **row: logged.append(row))
    with pytest.raises(FieldRefused) as refused:
        provider.complete(_messages(), fields=[("probe.thing.none", "WACHTWOORD-123")])
    assert inner.calls == [], "the call was made"
    assert refused.value.key == "probe.thing.none"
    assert "WACHTWOORD-123" not in str(refused.value), "a refusal never names the value"
    [row] = logged
    assert "probe.thing.none" in row["blocked_reason"]
    assert "WACHTWOORD-123" not in str(row), "the log row carries the key, not the value"


def test_a_tokenised_value_goes_as_its_token_and_never_as_itself():
    inner = Recorder()
    _admin(inner).complete(
        _messages(), fields=[Field("probe.thing.token", "Geheime Naam", token="persoon-90")]
    )
    sent = inner.calls[0][1]["content"]
    assert "Persoon: persoon-90" in sent and "Geheime Naam" not in sent


def test_a_tokenised_key_without_a_token_is_refused():
    inner = Recorder()
    with pytest.raises(FieldRefused, match="token"):
        _admin(inner).complete(_messages(), fields=[("probe.thing.token", "Geheime Naam")])
    assert inner.calls == []


def test_the_public_surface_takes_public_keys_only():
    inner = Recorder()
    _public(inner).complete(_messages(), fields=[("probe.thing.pub", "open")])
    assert "Openbaar: open" in inner.calls[0][1]["content"]
    for key in ("probe.thing.internal", "probe.thing.token", "probe.thing.none"):
        with pytest.raises(FieldRefused):
            _public(inner).complete(_messages(), fields=[Field(key, "x", token="t-1")])
    assert len(inner.calls) == 1, "a refused key was sent"


def test_an_unknown_key_is_refused():
    inner = Recorder()
    with pytest.raises(FieldRefused, match="register"):
        _admin(inner).complete(_messages(), fields=[("probe.thing.nothing", "x")])
    assert inner.calls == []


def test_run_chat_and_json_answer_carry_the_fields_through():
    inner = Recorder(answer='{"a": 1}')
    provider = _admin(inner)
    out = run_chat(
        None,
        _messages(),
        provider,
        tools=[],
        dispatch=lambda *a: "",
        fields=[("probe.thing.pub", "via de lus")],
    )
    assert out == '{"a": 1}' and "via de lus" in inner.calls[0][1]["content"]
    assert json_answer(provider, _messages(), fields=[("probe.thing.pub", "json")]) == {"a": 1}
    assert "Openbaar: json" in inner.calls[1][1]["content"]
    with pytest.raises(FieldRefused):
        json_answer(provider, _messages(), fields=[("probe.thing.none", "x")])


def test_the_block_takes_the_place_of_the_mark_or_the_end_of_the_reader_s_message():
    marked = place_fields(_messages(), "BLOK")
    assert marked[1]["content"] == "Gegevens:\nBLOK" and _messages()[1]["content"].endswith(
        FIELDS_MARK
    )
    plain = place_fields([{"role": "user", "content": "vraag"}], "BLOK")
    assert plain[0]["content"] == "vraag\n\nBLOK"


def test_known_name_parts_are_scrubbed_from_a_back_office_block():
    rules = admin_rules(
        lambda: {"van den broeck"} | {"broeck"},
        capability=AiCapability.ACTIVITY_DRAFTING,
        scan_prompt_names=False,
    )
    rules.match_names = True
    text = render_fields([("probe.thing.internal", "Gezin Broeck uitgenodigd")], rules)
    assert "Broeck" not in text and "[naam]" in text


# ── the surfaces are a closed table (review of #2053) ────────────────────────


def _on(surface):
    from dataclasses import replace

    return replace(
        admin_rules(
            lambda: set(), capability=AiCapability.ACTIVITY_DRAFTING, scan_prompt_names=False
        ),
        surface=surface,
    )


def test_a_surface_the_table_does_not_name_is_shown_nothing_at_all():
    """Proven red by ADDING: `.get(rules.surface, frozenset())` replaced by the old test
    `rules.surface is AiSurface.PUBLIC and …` → this goes green on an internal value."""
    with pytest.raises(FieldRefused):
        render_fields([("probe.thing.internal", "x")], _on("a-surface-nobody-decided"))
    with pytest.raises(FieldRefused):
        render_fields([("probe.thing.pub", "x")], _on("a-surface-nobody-decided"))


def test_the_named_surfaces_show_what_the_table_says():
    from app.domains.chatbot.models import AiSurface

    assert "Intern: x" in render_fields(
        [("probe.thing.internal", "x")], _on(AiSurface.DESIGNSTUDIO)
    )
    assert "Intern: x" in render_fields([("probe.thing.internal", "x")], _on(AiSurface.ADMIN))
    with pytest.raises(FieldRefused):
        render_fields([("probe.thing.internal", "x")], _on(AiSurface.PUBLIC))
    assert "Openbaar: x" in render_fields([("probe.thing.pub", "x")], _on(AiSurface.PUBLIC))
