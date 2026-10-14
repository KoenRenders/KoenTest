"""The cards block on the site (CR-17 phase 2, C4.9 and C4.13).

A card is a link: its title, one line, an icon of the kit or a picture,
labels as plain text, and the one destination — resolved by the resolver the
button uses. What the renderer owes the public page:

* one link per card, to the resolved address; every word of the author's
  escaped;
* the icon drawn — an `<svg>` the sanitiser would take out, so the block is
  placed after it — and the picture from media's own address;
* a card that leads nowhere left out on the site and named in the admin
  preview; a block with no card left renders nothing;
* the words of a card in the text the chatbot reads.

Broken on purpose (13 October 2026), each put back by the reverse edit:
`escape(` taken off the title in `_card_html` → the escape test red on the raw
`<script>`; the block returned straight into the HTML the sanitiser reads (no
`late` list) → three tests red, the icon's `<svg>` and the picture gone and a
`rel` added to an inside link.
"""

from __future__ import annotations

import re

from app.domains.cms.render import render_document
from app.domains.cms.schema import validate_document
from app.ui.kit.icons import icon_paths


def _cards(*cards: dict) -> dict:
    return {
        "type": "doc",
        "content": [{"type": "cards", "content": [{"type": "card", "attrs": c} for c in cards]}],
    }


def _render(document: dict, db=None, **kwargs) -> str:
    return render_document(validate_document(document), db, **kwargs)


def test_a_card_is_one_link_to_its_resolved_destination(db_session):
    from app.domains.cms.api import CmsPage

    page = CmsPage(title="Doelwit", slug="doelwit-kaart", is_published=True)
    db_session.add(page)
    db_session.flush()

    html = _render(
        _cards(
            {"title": "Naar de pagina", "line": "Lees verder", "page_id": page.id},
            {"title": "Buiten", "href": "https://voorbeeld.test/x"},
            {"title": "Word lid", "screen": "lid-worden"},
        ),
        db_session,
    )
    cards = re.findall(r'<div class="prose-card">.*?</div>', html, re.S)
    assert len(cards) == 3
    assert html.startswith('<div class="prose-cards">') and html.endswith("</div></div>")
    for card in cards:
        assert card.count("<a ") == 1, "a card holds exactly one link"
    assert 'href="/doelwit-kaart"' in cards[0] and ">Naar de pagina</a>" in cards[0]
    assert '<span class="prose-card-line">Lees verder</span>' in cards[0]
    assert 'href="https://voorbeeld.test/x" rel="noopener noreferrer"' in cards[1]
    assert 'href="/lid-worden"' in cards[2] and "rel=" not in cards[2]


def test_the_page_reference_follows_a_slug_change(db_session):
    from app.domains.cms.api import CmsPage

    page = CmsPage(title="Verhuist", slug="oud-adres", is_published=True)
    db_session.add(page)
    db_session.flush()
    document = _cards({"title": "Kaart", "page_id": page.id})
    assert 'href="/oud-adres"' in _render(document, db_session)
    page.slug = "nieuw-adres"
    db_session.flush()
    assert 'href="/nieuw-adres"' in _render(document, db_session)


def test_every_word_of_the_author_is_escaped():
    html = _render(
        _cards(
            {
                "title": "<script>alert(1)</script>",
                "line": '<img src=x onerror="alert(1)">',
                "labels": ["<b>vet</b>", "a & b"],
                "href": 'https://voorbeeld.test/?a=1&b="2"',
            }
        )
    )
    assert "<script>" not in html and "<img src=x" not in html and "<b>vet</b>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;vet&lt;/b&gt; · a &amp; b" in html
    assert 'href="https://voorbeeld.test/?a=1&amp;b=&quot;2&quot;"' in html


def test_the_icon_is_drawn_and_survives_the_sanitiser():
    html = _render(
        _cards({"title": "Met icoon", "icon": "users", "href": "https://voorbeeld.test"})
    )
    assert '<span class="prose-card-icon" aria-hidden="true"><svg ' in html
    assert icon_paths()["users"] in html


def test_a_picture_comes_from_media_s_own_address():
    from app.domains.media.api import media_url

    html = _render(_cards({"title": "Met foto", "media_id": 7, "href": "https://voorbeeld.test"}))
    assert f'<img class="prose-card-picture" src="{media_url(7)}" alt="" loading="lazy">' in html
    assert "prose-card-icon" not in html


def test_labels_stand_as_plain_text_with_a_middle_dot():
    html = _render(
        _cards({"title": "K", "labels": ["Gratis", "Elke week"], "href": "https://voorbeeld.test"})
    )
    assert '<span class="prose-card-labels">Gratis · Elke week</span>' in html
    bare = _render(_cards({"title": "K", "href": "https://voorbeeld.test"}))
    assert "prose-card-labels" not in bare and "prose-card-line" not in bare


def test_a_card_that_leads_nowhere_is_left_out_and_named_in_the_preview(db_session):
    document = _cards(
        {"title": "Blijft", "href": "https://voorbeeld.test"},
        {"title": "Weg", "page_id": 999_999},
        {"title": "Dicht", "form_slug": "bestaat-niet"},
    )
    site = _render(document, db_session)
    assert site.count('class="prose-card"') == 1 and "Blijft" in site
    assert "Weg" not in site and "Dicht" not in site
    preview = _render(document, db_session, preview=True)
    assert "Deze kaart wijst naar een pagina die niet (meer) bestaat." in preview
    assert "Deze kaart wijst naar een formulier dat geen inzendingen meer aanneemt." in preview
    assert "Blijft" in preview


def test_a_block_with_no_card_left_renders_nothing(db_session):
    document = _cards({"title": "Weg", "page_id": 999_999})
    assert _render(document, db_session) == ""


def test_cards_in_a_column_and_after_text_keep_their_place():
    document = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Ervoor."}]},
            {
                "type": "columns",
                "attrs": {"align": "top"},
                "content": [
                    {
                        "type": "column",
                        "content": [
                            {
                                "type": "cards",
                                "content": [
                                    {
                                        "type": "card",
                                        "attrs": {
                                            "title": "In de kolom",
                                            "href": "https://voorbeeld.test",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "type": "column",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "Ernaast."}]}
                        ],
                    },
                ],
            },
            {"type": "paragraph", "content": [{"type": "text", "text": "Erna."}]},
        ],
    }
    html = _render(document)
    assert (
        html.index("Ervoor.")
        < html.index("In de kolom")
        < html.index("Ernaast.")
        < html.index("Erna.")
    )
    assert '<div class="prose-column"><div class="prose-cards">' in html
    assert "" not in html, "a place mark of the cards was left in the page"


def test_text_that_looks_like_the_place_mark_stays_text():
    """The block is put where its mark stands after the sanitiser; an author
    who types the mark's own characters gets them back as text, not a block."""
    from app.domains.cms.render import _LATE

    document = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": f"{_LATE}0{_LATE}"}]},
            {
                "type": "cards",
                "content": [
                    {"type": "card", "attrs": {"title": "Echt", "href": "https://voorbeeld.test"}}
                ],
            },
        ],
    }
    html = _render(document)
    assert html.count('class="prose-cards"') == 1
    assert html.index("<p>") < html.index('class="prose-cards"')


def test_the_chatbot_reads_a_card_s_words():
    text = _render(
        _cards({"title": "Zaalverhuur", "line": "Huur de zaal", "href": "https://voorbeeld.test"}),
        target="text",
    )
    assert "Zaalverhuur Huur de zaal" in text
