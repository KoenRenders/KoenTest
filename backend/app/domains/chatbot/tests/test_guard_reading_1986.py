"""Three refinements of the guard's reading (#1986), each kept to the rule of
#1969: one reading, used by the guard and by the writer's cleaning alike.

1. The e-mail pattern answers within a bound on a long text, and an ordinary
   address is still found and cleaned.
2. A name part is found whatever Unicode form it was typed or stored in, and
   with a character without width inside it.
3. The label fields of a tool's result (#1154) are read as labels only for the
   tools that declare them.

All names are made up.
"""

from __future__ import annotations

import json
import time

import pytest

from app.domains.chatbot.models import AiCapability
from app.domains.chatbot.seam import admin_rules, findings, redact, scrub_names

pytestmark = pytest.mark.ui_agnostisch

NAMES = {"peeters", "renée"}
RULES = admin_rules(
    lambda: NAMES,
    capability=AiCapability.REPORTING,
    scan_prompt_names=False,
    label_tools=frozenset({"run_report"}),
)

#: What a reader is told for a name part and for an address.
NAME = "een naam uit de ledenadministratie (1x)"
EMAIL = "een e-mailadres"


def _user(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


# 1. The e-mail pattern ---------------------------------------------------------

#: 200 kB with no whitespace, no `@` and no bracket.
LONG_TEXT = '{"a":' * 40_000
BOUND_SECONDS = 2.0


def _seconds(call) -> float:
    start = time.perf_counter()
    call()
    return time.perf_counter() - start


def test_the_e_mail_pattern_answers_within_a_bound_on_a_long_text():
    """The guard and the cleaning both answer within the bound on 200 kB.

    Proven red by taking the bound of the part before the `@` away again (`+`
    for `{1,64}`): the cleaning does not answer within the bound."""
    assert len(LONG_TEXT) == 200_000
    assert _seconds(lambda: redact(LONG_TEXT)) < BOUND_SECONDS
    assert _seconds(lambda: findings(_user(LONG_TEXT), RULES)) < BOUND_SECONDS


@pytest.mark.parametrize("local", ["post", "a" * 64, "voor.naam+lid_2"])
def test_an_address_up_to_64_characters_before_the_at_is_found_and_cleaned(local):
    address = f"{local}@example.org"
    text = f"Mail {address} vandaag."
    assert findings(_user(text), RULES) == [EMAIL]
    assert redact(text) == "Mail [e-mailadres] vandaag."


# 2. One Unicode form -------------------------------------------------------------

COMPOSED = "Renée"  # é as one character
DECOMPOSED = "Renée"  # e followed by a combining acute accent


@pytest.mark.parametrize(
    ("stored", "typed"),
    [
        ({"renée"}, DECOMPOSED),
        ({"renée"}, COMPOSED),
        ({"peeters"}, "Pee​ters"),  # zero-width space
        ({"peeters"}, "Pee­ters"),  # soft hyphen
        ({"peeters"}, "Pee‍ters"),  # zero-width joiner
        ({"peeters"}, "Pee⁠ters"),  # word joiner
    ],
    ids=["stored-composed", "stored-decomposed", "zwsp", "shy", "zwj", "wj"],
)
def test_a_name_part_is_found_in_any_unicode_form_and_cleaned(stored, typed):
    """Is found as a typed text and in a tool's result, and the cleaning removes
    it so the guard finds nothing in what it returns.

    Proven red by making `normal_text` return its argument, and by making
    `normal_names` return the parts as stored."""
    rules = admin_rules(lambda: stored, capability=AiCapability.REPORTING)
    text = f"Komt {typed} ook?"
    assert findings(_user(text), rules) == [NAME], typed
    tool = [{"role": "tool", "name": "lookup", "content": json.dumps({"notes": text})}]
    assert findings(tool, rules) == [NAME], typed
    cleaned = scrub_names(text, stored, "[naam]")
    assert cleaned == "Komt [naam] ook?"
    assert findings(_user(cleaned), rules) == []


# 3. Label fields per declaring tool ---------------------------------------------


def _tool_result(tool: str) -> list[dict]:
    result = {"columns": [{"key": "peeters", "name": "Peeters"}], "rows": [{"peeters": 3}]}
    return [
        {"role": "user", "content": "Hoeveel?"},
        {"role": "tool", "tool_call_id": "1", "name": tool, "content": json.dumps(result)},
    ]


def test_a_declaring_tool_s_labels_are_read_as_labels():
    """Today's behaviour for the reporting assistant's tools (#1154)."""
    assert findings(_tool_result("run_report"), RULES) == []


def test_the_same_label_fields_in_another_tool_s_result_are_read():
    """Proven red by passing every tool as a label tool."""
    assert findings(_tool_result("lookup_activity"), RULES) == [NAME]
