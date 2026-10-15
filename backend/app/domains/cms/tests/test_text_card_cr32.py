"""CR-32 phase 2: the text card — a card with no destination (R4, F6, C4.3).

Broken on purpose (15 October 2026), each red for its own reason: the renderer
resolving a card with no destination (so leaving it out as unreachable) → the
text card is missing; the `<a>` written for a text card → the no-link test
fails; `number` or `text` written unescaped → the escape test fails; the
validator's `optional` taken off the card → a card with no destination is
refused again; the `text` words dropped from the chatbot's walk → the text test
fails.
"""

import re

import pytest

from app.domains.cms.render import render_document
from app.domains.cms.schema import InvalidShape, UnknownAttribute, validate_document

pytestmark = pytest.mark.ui_serverrendered


def _cards(*cards: dict) -> dict:
    return {
        "type": "doc",
        "content": [
            {"type": "cards", "content": [{"type": "card", "attrs": card} for card in cards]}
        ],
    }


def test_a_card_with_a_number_a_heading_and_a_paragraph_and_no_destination_validates():
    assert validate_document(_cards({"title": "Tijd", "number": "01", "text": "Elke week."}))


def test_a_text_card_renders_its_number_heading_and_paragraph_and_no_link():
    html = render_document(
        validate_document(_cards({"title": "Tijd", "number": "01", "text": "Elke week."}))
    )
    assert html == (
        '<div class="prose-cards"><div class="prose-card prose-card--text">'
        '<span class="prose-card-number">01</span>'
        '<span class="prose-card-title">Tijd</span>'
        '<p class="prose-card-text">Elke week.</p></div></div>'
    )
    assert "<a " not in html


def test_a_card_with_a_destination_is_a_link_as_before_and_may_carry_a_text_too():
    html = render_document(
        validate_document(
            _cards({"title": "Lees", "href": "https://example.test/x", "text": "Meer uitleg."})
        )
    )
    card = re.search(r'<div class="prose-card">.*?</div>', html, re.S).group(0)
    assert card.count("<a ") == 1 and 'href="https://example.test/x"' in card
    assert '<p class="prose-card-text">Meer uitleg.</p>' in card
    assert "prose-card--text" not in card


def test_two_destinations_are_still_refused_and_a_bad_address_too():
    with pytest.raises(InvalidShape, match="precies één bestemming"):
        validate_document(_cards({"title": "X", "page_id": 3, "href": "https://example.test"}))
    with pytest.raises(UnknownAttribute, match="card.href"):
        validate_document(_cards({"title": "X", "href": "javascript:alert(1)"}))


def test_the_number_and_the_text_are_escaped():
    html = render_document(
        validate_document(_cards({"title": "X", "number": "<b>1</b>", "text": "<i>a</i> & b"}))
    )
    assert "<b>1</b>" not in html and "&lt;b&gt;1&lt;/b&gt;" in html
    assert "<i>a</i>" not in html and "&lt;i&gt;a&lt;/i&gt; &amp; b" in html


def test_a_card_with_an_unreachable_destination_is_still_left_out_on_the_site():
    document = validate_document(_cards({"title": "Weg", "text": "Tekst", "page_id": 999999}))
    assert render_document(document) == ""
    assert "niet (meer) bestaat" in render_document(document, preview=True)


def test_the_chatbot_reads_a_cards_number_title_and_text():
    text = render_document(
        validate_document(_cards({"title": "Tijd", "number": "01", "text": "Elke week."})),
        target="text",
    )
    assert text == "01 Tijd Elke week."


def test_an_empty_address_is_no_destination_for_every_reader():
    """CR-32 Z1: one rule for "has a destination". A card with `href: ""` is a
    text card to the validator, the renderer and the editor's configuration
    alike; it was a link that vanished from the site (`is not None`) while the
    editor read it as "Nergens heen"."""
    from app.domains.cms.schema import destinations_set, schema_for

    card = {"title": "Tijd", "text": "Elke week.", "href": ""}
    assert destinations_set(card) == []
    assert destinations_set({"href": "https://example.test"}) == ["href"]
    assert destinations_set({"form_slug": "", "page_id": 4}) == ["page_id"]
    html = render_document(validate_document(_cards(card)))
    assert "prose-card--text" in html and "<a " not in html
    assert schema_for("page")["cards"]["destinations"] == ["page_id", "href", "form_slug", "screen"]


def test_a_button_with_an_empty_address_is_still_refused():
    button = {"type": "button", "attrs": {"label": "Ga", "variant": "primary", "href": ""}}
    with pytest.raises(InvalidShape, match="precies één bestemming"):
        validate_document({"type": "doc", "content": [button]})
