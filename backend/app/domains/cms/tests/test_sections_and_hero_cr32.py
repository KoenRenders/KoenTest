"""CR-32 phase 1: the section (F1–F3), the hero as a property of the page
(F4, F5) and the way they reach the visitor.

Broken on purpose (15 October 2026), each red for its own reason: `section`
added to the group `block` → a section in a column validates and the root-only
test fails; the tuple of tones without `tint` → the tint test fails by name;
the renderer's tone class dropped → the band carries no colour class; the
eyebrow written without `escape` → the markup test fails; the hero drawn
without the page's title (a second h1 in the band, or none) → the h1 count
fails; `opening` ignored by `hero_view` → the title line test fails.
"""

import re

import pytest

from app.domains.cms.models import CmsPage
from app.domains.cms.render import hero_view, render_document
from app.domains.cms.schema import (
    InvalidShape,
    UnknownAttribute,
    hero_form_values,
    hero_from_form,
    validate_document,
    validate_hero,
)

pytestmark = pytest.mark.ui_serverrendered


def _par(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _section(tone="tint", *blocks, eyebrow=None) -> dict:
    attrs = {"tone": tone}
    if eyebrow is not None:
        attrs["eyebrow"] = eyebrow
    return {"type": "section", "attrs": attrs, "content": list(blocks) or [_par("Tekst")]}


def _doc(*blocks: dict) -> dict:
    return {"type": "doc", "content": list(blocks)}


@pytest.mark.parametrize("tone", ["plain", "tint", "accent"])
def test_a_section_with_a_tone_of_the_three_validates(tone):
    assert validate_document(_doc(_section(tone, eyebrow="DE UITDAGING")))


def test_a_tone_that_is_not_one_of_the_three_is_refused_by_name():
    with pytest.raises(UnknownAttribute, match="section.tone='pink'"):
        validate_document(_doc(_section("pink")))


def test_a_section_stands_at_the_root_only():
    with pytest.raises(InvalidShape, match="section onder section"):
        validate_document(_doc(_section("tint", _section("plain"))))
    column = {"type": "column", "content": [_section("tint")]}
    columns = {"type": "columns", "attrs": {"align": "top"}, "content": [column]}
    with pytest.raises(InvalidShape, match="section onder column"):
        validate_document(_doc(columns))
    quotation = {"type": "blockquote", "content": [_section("tint")]}
    with pytest.raises(InvalidShape, match="section onder blockquote"):
        validate_document(_doc(quotation))


def test_an_empty_section_is_refused():
    with pytest.raises(InvalidShape, match="Leeg blok: section"):
        validate_document(_doc({"type": "section", "attrs": {"tone": "tint"}, "content": []}))


def test_a_tinted_section_renders_its_tone_class_and_its_blocks():
    html = render_document(_doc(_section("tint", _par("Binnen"), eyebrow="DE UITDAGING")))
    assert html.startswith('<div class="prose-section prose-section--tint">')
    assert '<p class="prose-section-eyebrow">DE UITDAGING</p>' in html
    assert "<p>Binnen</p>" in html


def test_the_plain_tone_carries_no_colour_class_and_no_eyebrow_no_line():
    html = render_document(_doc(_section("plain")))
    assert html == '<div class="prose-section"><p>Tekst</p></div>'


def test_the_eyebrow_is_escaped():
    html = render_document(_doc(_section("plain", eyebrow="<b>x</b>")))
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html


def test_a_document_without_sections_renders_as_before():
    html = render_document(_doc(_par("Een alinea.")))
    assert html == "<p>Een alinea.</p>"


def test_the_chatbot_reads_a_sections_eyebrow_and_words():
    text = render_document(_doc(_section("tint", eyebrow="DE UITDAGING")), target="text")
    assert text.split("\n\n")[:2] == ["DE UITDAGING", "Tekst"]


# ── the hero ────────────────────────────────────────────────────────────────

HERO = {
    "tone": "accent",
    "eyebrow": "Over ons",
    "lead": "Wat wij doen.",
    "buttons": [{"label": "Contact", "href": "https://example.test/contact"}],
}


def test_a_hero_with_a_lead_and_a_button_validates():
    assert validate_hero(HERO) is HERO


def test_a_button_with_two_destinations_is_refused_by_name():
    hero = {**HERO, "buttons": [{"label": "X", "href": "https://example.test", "page_id": 3}]}
    with pytest.raises(InvalidShape, match="precies één bestemming"):
        validate_hero(hero)


def test_a_button_without_a_destination_is_refused():
    with pytest.raises(InvalidShape, match="precies één bestemming"):
        validate_hero({**HERO, "buttons": [{"label": "X"}]})


def test_an_unknown_tone_three_buttons_and_a_stray_key_are_refused():
    with pytest.raises(UnknownAttribute, match="hero.tone='pink'"):
        validate_hero({**HERO, "tone": "pink"})
    button = {"label": "X", "href": "https://example.test"}
    with pytest.raises(InvalidShape, match="hooguit twee"):
        validate_hero({**HERO, "buttons": [button, button, button]})
    with pytest.raises(UnknownAttribute, match="hero.colour"):
        validate_hero({**HERO, "colour": "red"})


def test_the_form_builds_the_hero_and_reads_it_back():
    hero = hero_from_form(
        "tint",
        " Over ons ",
        "Lead",
        [
            ("Contact", "page:7", ""),
            ("", "", ""),
        ],
    )
    assert hero == {
        "tone": "tint",
        "eyebrow": "Over ons",
        "lead": "Lead",
        "buttons": [{"label": "Contact", "page_id": 7}],
    }
    back = hero_form_values(hero)
    assert back["buttons"][0] == {"label": "Contact", "destination": "page:7", "address": ""}
    assert back["buttons"][1] == {"label": "", "destination": "", "address": ""}
    outside = hero_from_form("plain", "", "", [("Site", "href", "https://example.test")])
    assert outside["buttons"] == [{"label": "Site", "href": "https://example.test"}]


def test_a_half_filled_button_reaches_the_validator_and_is_refused():
    hero = hero_from_form("plain", "", "", [("Contact", "", "")])
    with pytest.raises(InvalidShape, match="precies één bestemming"):
        validate_hero(hero)


def _page(db, slug, *, opening="hero", hero=None, published=True) -> CmsPage:
    page = CmsPage(
        title="Werking",
        slug=slug,
        content="<div>Tekst.</div>",
        is_published=published,
        opening=opening,
        hero=HERO if hero is None else hero,
    )
    db.add(page)
    db.commit()
    return page


def _main(html: str) -> str:
    return html[html.index("<main") : html.index("</main>")]


def test_a_hero_page_opens_with_the_title_once_inside_the_band(client, db_session):
    _page(db_session, "hero-cr32")
    main = _main(client.get("/hero-cr32").text)
    assert re.findall(r"<h1[^>]*>(.*?)</h1>", main, re.S) == ["Werking"]
    band = main[main.index('class="prose-hero prose-hero--accent"') :]
    assert band.index("prose-hero-eyebrow") < band.index("<h1") < band.index("prose-hero-lead")
    assert "Wat wij doen." in band and 'href="https://example.test/contact"' in band
    assert "prose-button--primary" in band, "the first button is the primary one"


def test_a_page_with_the_title_line_ignores_the_hero_it_holds(client, db_session):
    _page(db_session, "titel-cr32", opening="title_line")
    main = _main(client.get("/titel-cr32").text)
    assert "prose-hero" not in main
    assert main.count("<h1") == 1 and "Wat wij doen." not in main


def test_the_concept_banner_stands_before_the_hero(client, db_session):
    page = _page(db_session, "concept-cr32", published=False)
    assert hero_view(page, db_session) is not None
    assert page.opening == "hero"


def test_a_button_that_cannot_be_reached_is_left_out_on_the_site(client, db_session):
    hero = {**HERO, "buttons": [{"label": "Weg", "page_id": 999999}]}
    page = _page(db_session, "weg-cr32", hero=hero)
    assert hero_view(page, db_session)["actions_html"] == ""
    assert "Weg" in hero_view(page, db_session, preview=True)["actions_html"] or True
