"""#1899 (CR-11 roll-out, slice 1): the kit's person card in read mode.

One card per person — the name as the heading with the relation at its right,
and under it the lines without a label: the icon says what a value is, an
empty one reads "—" (`docs/design-system-end-state.md` §2.2, §5.2; CR-11 B10
of 10 October 2026). These tests render the macro itself; what only a browser
shows stands on the design-system page and in the measurement baseline.

Proven red (each on this branch, restored after):
- the `emails|length > 1` taken off the tag → the one-address test fails;
- the `pending` branch taken off → the waiting-address test fails;
- "—" for an empty mobile number replaced by nothing → the empty test fails.
"""

from __future__ import annotations

import re

import pytest

from app.ui import templates

pytestmark = pytest.mark.ui_serverrendered

CARD = (
    "{{ ui.person_card(name, relation=relation, main=main, birth=birth, gender=gender,"
    " mobile=mobile, phone=phone, emails=emails) }}"
)


def _render(**context) -> str:
    given = {
        "name": "Lore Voorbeeld",
        "relation": "Hoofdlid",
        "main": True,
        "birth": "14-03-1978",
        "gender": "Vrouw",
        "mobile": "",
        "phone": "",
        "emails": [],
    }
    given.update(context)
    return templates.env.from_string('{% import "_macros.html" as ui %}' + CARD).render(**given)


def _address(value: str, *, primary: bool = False, pending: bool = False) -> dict:
    return {"value": value, "primary": primary, "pending": pending}


def _email_lines(html: str) -> list[str]:
    return re.findall(r"<p data-person-email.*?</p>", html, re.S)


def test_the_name_is_the_heading_and_the_relation_its_badge():
    html = _render()
    assert html.count("data-person-card") == 1
    heading = re.search(r"<h2 data-person-name[^>]*>(.*?)</h2>", html, re.S)
    assert heading and heading.group(1).strip() == "Lore Voorbeeld"
    relation = re.search(r"<span data-person-relation.*?</span>\s*</span>", html, re.S)
    assert relation and "Hoofdlid" in relation.group(0)
    assert "° 14-03-1978 · Vrouw" in html
    # No labels: the card says no "Mobiel", "Telefoon" or "E-mail".
    assert not re.search(r"<label|Mobiel|Telefoon|E-mail", html)


def test_a_person_without_a_household_carries_no_relation():
    assert "data-person-relation" not in _render(relation=None)


def test_an_empty_value_reads_a_dash_behind_its_icon():
    html = _render()
    facts = re.findall(r"<span data-icon-fact.*?</span></span>", html, re.S)
    # Mobile, phone and the one e-mail line: three icons, three dashes.
    assert len(facts) == 3, facts
    assert all("<svg" in fact and ">—<" in fact for fact in facts), facts
    assert "mailto:" not in html


def test_one_address_carries_no_tag_and_is_a_mail_link():
    html = _render(emails=[_address("lore@voorbeeld.test", primary=True)])
    lines = _email_lines(html)
    assert len(lines) == 1
    assert 'href="mailto:lore@voorbeeld.test"' in lines[0]
    assert "hoofdadres" not in html


def test_the_primary_of_several_addresses_is_tagged_and_only_that_one():
    html = _render(
        emails=[_address("lore@voorbeeld.test", primary=True), _address("werk@voorbeeld.test")]
    )
    lines = _email_lines(html)
    assert ["hoofdadres" in line for line in lines] == [True, False]


def test_an_address_that_waits_for_its_code_says_so():
    html = _render(
        emails=[
            _address("lore@voorbeeld.test", primary=True),
            _address("nieuw@voorbeeld.test", pending=True),
        ]
    )
    lines = _email_lines(html)
    assert ["wacht op bevestiging" in line for line in lines] == [False, True]


def test_a_phone_number_is_shown_readable():
    html = _render(mobile="0470123456")
    assert "0470 12 34 56" in html
