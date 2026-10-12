"""#1900 (CR-11 roll-out, slice 2): what the kit gained for the activity record.

- `label_fact`: a value that keeps its label in read mode — the label, a colon,
  the value;
- `flow_heading`: the heading row above a run of cards;
- `rare_line`: what is rarely set, as a closed line in the card of its object,
  counting what is filled;
- `field(..., beside_switch=True)`: an e-mail field is half only beside the
  switch it belongs to — anywhere else its kind decides and it is full;
- the record head's facts carry their separator in front, one per fact.

These tests render the macros themselves; what only a browser shows — that a
separator at the start of a line is clipped away — is measured in
`tests_e2e/members/test_household_record.py`.

Proven red (locally, restored), each by an addition:
- `and false` behind the macro's `kind == "email" and beside_switch` → the
  half-width test fails on "full";
- `or true` there → the default test fails on "half";
- `open` written on the `<details>` of `rare_line` → "the line starts open";
- the count's `{% if count %}` replaced by `{% if true %}` → "an empty line
  counts".
"""

from __future__ import annotations

import re

import pytest

from app.ui import templates

pytestmark = pytest.mark.ui_serverrendered


def _render(source: str, **context) -> str:
    return templates.env.from_string('{% import "_macros.html" as ui %}' + source).render(**context)


def _words(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _span(html: str, field: str) -> str:
    found = re.search(rf'data-field="{re.escape(field)}"[^>]*data-span="(\w+)"', html)
    assert found, f"no field {field} — the test looks nowhere"
    return found.group(1)


def test_an_email_field_is_half_only_beside_its_switch():
    beside = _render(
        '{{ ui.field("o.1.email_override", "Ander e-mailadres", kind="email", beside_switch=True) }}'
    )
    assert _span(beside, "o.1.email_override") == "half"


def test_an_email_field_is_full_everywhere_else():
    plain = _render('{{ ui.field("email", "E-mailadres", kind="email") }}')
    assert _span(plain, "email") == "full"
    # The parameter is the e-mail field's: no other full kind gets narrower by it.
    url = _render('{{ ui.field("site", "Website", kind="url", beside_switch=True) }}')
    assert _span(url, "site") == "full"


def test_a_label_fact_reads_label_colon_value():
    html = _render('{{ ui.label_fact("Maximum", 40) }}')
    assert _words(html) == "Maximum: 40"
    assert 'class="text-ink-soft">Maximum:</span>' in html, "the label is not the soft one"


def test_the_flow_heading_is_a_heading_of_the_page():
    html = _render('{{ ui.flow_heading("Onderdelen", id="x") }}')
    assert re.fullmatch(r'<h2 data-flow-heading id="x"[^>]*>Onderdelen</h2>', html.strip())


RARE = (
    '{% call ui.rare_line("Externe koppelingen", count=count) %}'
    '{{ ui.field("poster_url", "Poster-URL", kind="url", value=value) }}{% endcall %}'
)


def test_a_rare_line_is_closed_holds_its_fields_and_counts_what_is_filled():
    filled = _render(RARE, count=2, value="https://example.org/a.png")
    assert not re.match(r"\s*<details[^>]*\bopen\b", filled), "the line starts open"
    summary = re.search(r"<summary.*?</summary>", filled, re.S).group(0)
    assert _words(summary) == "Externe koppelingen · 2 ingevuld"
    assert 'name="poster_url"' in filled and 'value="https://example.org/a.png"' in filled
    assert 'data-span="full"' in filled.split(">", 1)[0], "the line does not take the card's width"

    empty = _render(RARE, count=0, value="")
    summary = re.search(r"<summary.*?</summary>", empty, re.S).group(0)
    assert _words(summary) == "Externe koppelingen", "an empty line counts"


def test_every_fact_of_the_record_head_carries_its_separator_in_front():
    html = _render(
        '{{ ui.record_header("Gezin Voorbeeld", facts=facts) }}',
        facts=[
            {"text": "Voorbeeldstraat 1, Mol"},
            {"text": "an@example.com", "kind": "mail"},
            {"text": "Lid 12", "kind": "reference", "href": "/x"},
        ],
    )
    line = html[html.index("data-facts") :].split("</p>", 1)[0]
    facts = re.findall(r"<span data-fact .*?(?=<span data-fact |\Z)", line, re.S)
    assert len(facts) == 3
    for fact in facts:
        assert fact.count("data-fact-dot") == 1, "a fact without its separator, or with two"
        assert fact.index("data-fact-dot") < fact.index("</span>"), "the separator stands behind"
    assert "overflow-x-clip" in line.split(">", 1)[0], "nothing clips the first separator away"
    assert 'href="mailto:an@example.com"' in line and 'href="/x"' in line
