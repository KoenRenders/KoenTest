"""A refusal of the guard says in which part of the payload the hit stands (#1969).

"Deze vraag is niet verstuurd … Herformuleer de vraag" was what every refusal
said, also when the author's question held nothing and the hit stood in a text
that was sent along — which the author cannot rephrase. Since #1969 the guard's
refusal names the place in the reader's words, says what the reader can do about
that place only where there is something to do, and never names what was found.
One rule, in the guard, for every surface.

Broken on purpose (13 October 2026, each put back):
- `_places`: every hit placed by its message's role (the declared parts not
  asked) → "in een voorbeeld van een eerdere brief" is missed and the question
  is blamed;
- `_places`: a part asked without looking whether it stands in the hit's own
  message → "a word in the question is blamed on the example";
- `refusal`: the found word put into the sentence → "the name stands on the
  screen";
- `GuardedProvider.complete`: the place left out of `blocked_reason` → "the log
  does not say where".
"""

from dataclasses import replace

import pytest

from app.domains.chatbot.models import AiCapability, AiSurface
from app.domains.chatbot.providers.base import AssistantMessage
from app.domains.chatbot.seam import (
    GuardedProvider,
    GuardRules,
    Part,
    SeamBlocked,
    public_rules,
    refusal,
)

NAME = "Vandersmissen"
STREET = "Kerkstraat"
NAMES = {NAME.lower(), STREET.lower()}

EXAMPLE = Part(
    where="een voorbeeld van een eerdere brief",
    text=f"VOORBEELDEN VAN EERDERE BRIEVEN\nBeste,\n{NAME} bakte wafels.",
    advice="Haal de doelgroep even weg: dan gaan er geen voorbeelden van eerdere brieven mee.",
)
ACTIVITY = Part(
    where="de tekst van een gekozen activiteit",
    text=f"## Activiteit 3\nInschrijven bij {NAME}.",
    advice="Haal die activiteit even uit de brief of pas haar tekst aan.",
)
REPORT_POINT = Part(
    where="een vergaderverslag sinds de vorige brief", text=f"- {NAME} regelt de bus"
)
RULES = GuardRules(
    surface=AiSurface.ADMIN,
    capability=AiCapability.NEWSLETTER_DRAFTING,
    match_names=True,
    match_email=True,
    names=lambda: NAMES,
    parts=lambda: [ACTIVITY, REPORT_POINT, EXAMPLE],
)
SYSTEM = {"role": "system", "content": "Schrijf een nieuwsbrief."}


def _sources(*parts: Part) -> dict:
    return {"role": "user", "content": "BRONNEN\n\n" + "\n\n".join(p.text for p in parts)}


def _refused(messages, rules=RULES) -> SeamBlocked:
    blocked = refusal(messages, rules)
    assert blocked is not None, "not refused"
    assert NAME not in str(blocked) and NAME.lower() not in str(blocked).lower(), (
        "the name stands on the screen"
    )
    assert STREET.lower() not in str(blocked).lower(), "the name stands on the screen"
    assert "niet verstuurd" in str(blocked)
    return blocked


def test_a_clean_payload_is_not_refused():
    clean = replace(EXAMPLE, text="VOORBEELDEN\nBeste,\nEven voorstellen.")
    assert (
        refusal([SYSTEM, _sources(clean), {"role": "user", "content": "nieuwsbrief?"}], RULES)
        is None
    )


@pytest.mark.parametrize("part", [EXAMPLE, ACTIVITY, REPORT_POINT])
def test_a_hit_in_a_text_that_was_sent_along_names_that_text_and_not_the_question(part):
    """What Koen met: the question held nothing, the example did."""
    blocked = _refused([SYSTEM, _sources(part), {"role": "user", "content": "nieuwsbrief?"}])
    assert blocked.places == (part.where,)
    assert f"in {part.where} staat" in str(blocked)
    assert "je vraag" not in str(blocked) and "Herformuleer" not in str(blocked)
    # Advice only where the author can do something about that part.
    if part.advice:
        assert str(blocked).endswith(part.advice)
    else:
        assert str(blocked).endswith("naar het taalmodel.")


def test_a_hit_in_the_question_names_the_question_also_when_a_part_holds_the_same_word():
    clean = replace(EXAMPLE, text="VOORBEELDEN\nBeste,\nEven voorstellen.")
    rules = replace(RULES, parts=lambda: [EXAMPLE])  # the declared part holds the name …
    blocked = _refused(
        [SYSTEM, _sources(clean), {"role": "user", "content": f"Wat doet {NAME}?"}], rules
    )  # … but it is not in this payload: the name was typed
    assert blocked.places == ("je vraag",), "a word in the question is blamed on the example"
    assert "Herformuleer je vraag" in str(blocked)


def test_two_places_are_both_named_once():
    blocked = _refused(
        [
            SYSTEM,
            _sources(ACTIVITY, EXAMPLE),
            {"role": "user", "content": "Mail naar a@example.org"},
        ]
    )
    assert blocked.places == (ACTIVITY.where, EXAMPLE.where, "je vraag")
    said = str(blocked)
    assert f"in {ACTIVITY.where}, {EXAMPLE.where} en je vraag staat" in said
    assert "een e-mailadres" in said and "a@example.org" not in said
    assert said.count(ACTIVITY.advice) == 1 and said.count(EXAMPLE.advice) == 1


def test_an_earlier_turn_and_the_instructions_are_places_without_advice():
    earlier = _refused(
        [
            SYSTEM,
            {"role": "user", "content": f"Wat doet {NAME}?"},
            {"role": "assistant", "content": "Dat weet ik niet."},
            {"role": "user", "content": "En nu?"},
        ]
    )
    assert earlier.places == ("het gesprek tot nu toe",)
    assert str(earlier).endswith("naar het taalmodel.")
    prompt = _refused(
        [
            {"role": "system", "content": f"Huisstijl van {NAME}."},
            {"role": "user", "content": "Doe."},
        ]
    )
    assert prompt.places == ("de vaste instructies van Raakje",)


def test_what_a_tool_brought_back_is_its_own_place():
    messages = [
        SYSTEM,
        {"role": "user", "content": "Welke activiteiten komen eraan?"},
        {
            "role": "tool",
            "name": "get_activities",
            "content": f'{{"rows": [{{"notes": "Bel {NAME}"}}]}}',
        },
    ]
    blocked = _refused(messages)
    assert blocked.places == ("wat Raakje opzocht om te antwoorden",)
    assert "je vraag" not in str(blocked) and blocked.link is None


def test_a_reports_result_says_the_question_was_fine_and_points_to_rapporten():
    """Koen, 13 October 2026 ("2a"): the guard stays strict on a report's values;
    the message is honest about what was held back."""
    report = Part(
        where="het resultaat van het rapport",
        advice="Je vraag zelf was in orde: je kan hetzelfde rapport met de hand samenstellen in Rapporten.",
        link=("/admin/rapporten", "Naar Rapporten"),
    )
    rules = replace(RULES, capability=AiCapability.REPORTING, parts=lambda: (), tool=report)
    messages = [
        SYSTEM,
        {"role": "user", "content": "Hoeveel leden hebben we per straat?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "type": "function",
                    "function": {"name": "run_report", "arguments": '{"groep": "straat"}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "1",
            "name": "run_report",
            "content": f'{{"columns": [{{"key": "straat", "name": "Straat"}}], "rows": [["{STREET}", 4], ["Molenweg", 2]]}}',
        },
    ]
    blocked = _refused(messages, rules)
    assert blocked.places == ("het resultaat van het rapport",)
    assert "in het resultaat van het rapport staat een woord dat ook een naam" in str(blocked)
    assert "Je vraag zelf was in orde" in str(blocked)
    assert blocked.link == ("/admin/rapporten", "Naar Rapporten")
    # Nothing is loosened: the same question without that value in the result goes out.
    messages[-1] = {**messages[-1], "content": '{"rows": [["Molenweg", 2]]}'}
    assert refusal(messages, rules) is None


def test_the_public_bot_names_the_visitors_message():
    blocked = refusal(
        [SYSTEM, {"role": "user", "content": "Bel me op 0473 12 34 56"}], public_rules()
    )
    assert blocked is not None and blocked.places == ("je bericht",)
    assert "in je bericht staat een telefoonnummer" in str(blocked)
    assert "0473" not in str(blocked)


def test_the_log_says_what_and_where_and_the_call_does_not_leave():
    class Inner:
        name = "mock"
        model = "scripted"
        calls = 0

        def complete(self, messages, tools=None, tool_choice=None, **more):
            Inner.calls += 1
            return AssistantMessage(content="ok")

    logged: list[dict] = []
    guarded = GuardedProvider(Inner(), RULES, lambda **row: logged.append(row))
    with pytest.raises(SeamBlocked) as refused:
        guarded.complete([SYSTEM, _sources(EXAMPLE), {"role": "user", "content": "nieuwsbrief?"}])
    assert refused.value.places == (EXAMPLE.where,)
    assert Inner.calls == 0, "the call left"
    reason = logged[-1]["blocked_reason"]
    assert reason == f"een naam uit de ledenadministratie (1x) — in: {EXAMPLE.where}", (
        "the log does not say where"
    )
    assert NAME.lower() not in reason.lower()
