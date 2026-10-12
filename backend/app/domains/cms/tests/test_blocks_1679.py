"""The blocks of phase 2, slice 1's rest (CR-17 #1679): columns, button,
callout — the renderer's branches, the shape rules the schema cannot say,
the adapter's derivation and the button's ONE resolver.

Every test here can go red (the gate convention): take the branch out and
the render asserts fail; take the shape rule out and the refusals pass
where they must fail. The red proofs named per test were run while
building, each additive and restored.

The button's four destinations are Koen's decision of 11 October 2026
("c, maar enkel \\"lid worden\\" als onderdeel van deze CR"): a page of the
site, an outside address, a form of the tenant, and one application
screen — Lid worden. Exactly one is set; the ONE resolver serves the
button and the card alike (the card joins in her commit).
"""

import pytest

from app.domains.cms.render import render_document
from app.domains.cms.schema import InvalidShape, UnknownAttribute, validate_document
from app.domains.cms.service import document_from_editor


def _doc(*blocks: dict) -> dict:
    return {"type": "doc", "content": list(blocks)}


def _par(tekst: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": tekst}]}


# ── The renderer's branches ─────────────────────────────────────────────────


def test_columns_render_two_equal_columns_with_the_align_as_a_class():
    """C4.6/C4.13: the wrapper carries the grid, the stored `align` becomes
    a class (the sanitiser allows no data attributes), the columns render
    their children bare. Red on the tip before this slice: 'columns'
    raised the unknown-block error."""
    document = _doc(
        {
            "type": "columns",
            "attrs": {"align": "top"},
            "content": [
                {"type": "column", "content": [_par("Links")]},
                {"type": "column", "content": [_par("Rechts")]},
            ],
        }
    )
    assert validate_document(document) == document
    html = render_document(document)
    assert html.count('class="prose-columns"') == 1
    assert html.count('class="prose-column"') == 2
    assert "Links" in html and "Rechts" in html
    middle = _doc(
        {
            "type": "columns",
            "attrs": {"align": "middle"},
            "content": [
                {"type": "column", "content": [_par("Links")]},
                {"type": "column", "content": [_par("Rechts")]},
            ],
        }
    )
    assert 'class="prose-columns prose-columns--middle"' in render_document(middle)


def test_a_callout_renders_her_words_in_the_box():
    """C4.13: text only, in the box the kit styles — the words are content,
    sanitised with everything else. Red on the tip before this slice."""
    document = _doc(
        {
            "type": "callout",
            "content": [{"type": "text", "text": "Let op: <b>dit</b> is een kader."}],
        }
    )
    html = render_document(document)
    assert 'class="prose-callout"' in html
    assert "Let op:" in html and "dit" in html
    assert "<script" not in html


def test_a_button_renders_the_kits_button_with_her_resolved_destination(db_session):
    """The one resolver, all four doors (Koen, 11 October 2026): a page of
    the site — her address follows a slug change, the reference is the id;
    a form — forms' own door decides; Lid worden — the one application
    screen of this CR; an outside address — escaped, with her rel. Red on
    the tip before this slice: 'button' raised the unknown-block error."""
    from app.domains.cms.api import CmsPage

    pagina = CmsPage(title="Doelwit", slug="doelwit-test", is_published=True)
    db_session.add(pagina)
    db_session.flush()

    # Een pagina van de site: de referentie is haar id, niet haar adres.
    knop = _doc(
        {
            "type": "button",
            "attrs": {"label": "Naar de pagina", "variant": "primary", "page_id": pagina.id},
        }
    )
    html = render_document(knop, db_session)
    assert 'class="prose-button prose-button--primary"' in html
    assert "/doelwit-test" in html and "Naar de pagina" in html

    # Een adres buiten: http(s), ge-escape-d, met haar rel.
    buiten = _doc(
        {
            "type": "button",
            "attrs": {"label": "Buiten", "variant": "secondary", "href": "https://example.test/x"},
        }
    )
    html = render_document(buiten)
    assert 'href="https://example.test/x"' in html and 'rel="noopener noreferrer"' in html

    # Lid worden: het ene app-scherm van deze CR.
    lid = _doc(
        {
            "type": "button",
            "attrs": {"label": "Word lid", "variant": "primary", "screen": "lid-worden"},
        }
    )
    assert "/lid-worden" in render_document(lid)

    # Een formulier: forms' eigen deur beslist (hier zonder formulier:
    # niets — nooit een knop die nergens heen leidt, A4's regel).
    leeg = _doc(
        {
            "type": "button",
            "attrs": {"label": "Vraag", "variant": "primary", "form_slug": "bestaat-niet"},
        }
    )
    assert render_document(leeg) == ""

    # Een pagina die niet bestaat: niets op de site, de woorden in de preview.
    weg = _doc(
        {"type": "button", "attrs": {"label": "Weg", "variant": "primary", "page_id": 999999}}
    )
    assert render_document(weg, db_session) == ""
    assert "niet (meer) bestaat" in render_document(weg, db_session, preview=True)


def test_the_page_target_follows_a_slug_change(db_session):
    """C4.13: a page reference survives a slug change — the address is
    derived at render, never stored. Measured: the button renders the new
    slug's address the moment the page moves."""
    import secrets

    from app.domains.cms.api import CmsPage, create_page, publish, save_document
    from app.schemas.cms import CmsPageCreate

    tag = secrets.token_hex(3)
    pagina = create_page(db_session, CmsPageCreate(title="Verhuizer", slug=f"verhuizer-{tag}"))
    page_id = pagina.id
    save_document(db_session, page_id, _doc(_par("Inhoud")))
    publish(db_session, page_id)
    db_session.commit()

    knop = _doc(
        {
            "type": "button",
            "attrs": {"label": "Naar de pagina", "variant": "primary", "page_id": page_id},
        }
    )
    eerste = render_document(knop, db_session)
    assert f"/verhuizer-{tag}" in eerste

    pagina = db_session.query(CmsPage).filter(CmsPage.id == page_id).first()
    pagina.slug = f"verhuisd-{tag}"
    db_session.commit()

    tweede = render_document(knop, db_session)
    assert f"/verhuisd-{tag}" in tweede, "de knop volgt de pagina niet"


def test_the_text_walker_keeps_the_words_of_columns_and_callouts():
    """B3 of the plan review: the chatbot's context reads the words — a
    paragraph in a column was silently gone before this walker learned
    her, and a callout's words are content, not attributes."""
    from app.domains.cms.render import render_document

    document = _doc(
        {
            "type": "columns",
            "attrs": {"align": "top"},
            "content": [
                {"type": "column", "content": [_par("Linkerwoorden")]},
                {"type": "column", "content": [_par("Rechterwoorden")]},
            ],
        },
        {"type": "callout", "content": [{"type": "text", "text": "Kaderwoorden"}]},
        {
            "type": "button",
            "attrs": {"label": "Knopwoorden", "variant": "primary", "href": "https://x.test"},
        },
    )
    tekst = render_document(document, target="text")
    for woorden in ("Linkerwoorden", "Rechterwoorden", "Kaderwoorden", "Knopwoorden"):
        assert woorden in tekst, f"de tekst loopt {woorden} kwijt"


# ── The shape rules the schema cannot say ────────────────────────────────────


def test_a_button_points_at_exactly_one_destination():
    """Koen's four doors are the button's own shape rule: two set is a
    document the resolver cannot resolve, none a button that leads
    nowhere. Red on the tip before this slice: both documents validated."""
    twee = _doc(
        {
            "type": "button",
            "attrs": {
                "label": "Klik",
                "variant": "primary",
                "page_id": 1,
                "href": "https://x.test",
            },
        }
    )
    with pytest.raises(InvalidShape):
        validate_document(twee)


def test_an_outside_address_is_https_only():
    """C4.11: nothing is stripped at render — the address is refused at the
    save, with her name. javascript: and a bare relative path both refuse."""
    for adres in ("javascript:alert(1)", "/intern-pad", "httpx://x.test"):
        with pytest.raises(UnknownAttribute, match="button.href"):
            validate_document(
                _doc(
                    {
                        "type": "button",
                        "attrs": {"label": "Klik", "variant": "primary", "href": adres},
                    }
                )
            )


def test_columns_inside_a_column_are_refused():
    """B5 of the design review: a column holds blocks, not a second columns
    block that breaks out of her column. Refused with both names at the
    save. Red on the tip before this slice: the document validated."""
    genest = _doc(
        {
            "type": "columns",
            "attrs": {"align": "top"},
            "content": [
                {"type": "column", "content": [_par("Links")]},
                {
                    "type": "column",
                    "content": [
                        {
                            "type": "columns",
                            "attrs": {"align": "top"},
                            "content": [
                                {"type": "column", "content": [_par("Genest")]},
                            ],
                        }
                    ],
                },
            ],
        }
    )
    with pytest.raises(InvalidShape, match="kolommen in een kolom"):
        validate_document(genest)


# ── The adapter's derivation (B4) ────────────────────────────────────────────


def test_the_adapter_derives_the_columns_alignment():
    """The alignment is not the author's own choice (C4.13: "in het midden
    wanneer één kolom alleen een afbeelding is") — derived at the save,
    one place, and the renderer renders the stored value. A figure beside
    her text is the one case; two text columns stay 'top'. Red on the tip
    before this slice: the adapter stored whatever the editor sent."""
    figuur_kolom = {"type": "column", "content": [{"type": "figure", "attrs": {"media_id": 1}}]}
    tekst_kolom = {"type": "column", "content": [_par("Woorden naast het beeld")]}

    midden = document_from_editor(
        _doc({"type": "columns", "attrs": {"align": "top"}, "content": [tekst_kolom, figuur_kolom]})
    )
    assert midden["content"][0]["attrs"]["align"] == "middle"

    boven = document_from_editor(
        _doc(
            {"type": "columns", "attrs": {"align": "middle"}, "content": [tekst_kolom, tekst_kolom]}
        )
    )
    assert boven["content"][0]["attrs"]["align"] == "top"


# ── The repair of the review of 12 October 2026 ─────────────────────────────


def test_a_button_on_a_site_block_leads_nowhere(db_session):
    """A2 of the review: the site's own blocks (the home intro, the footer)
    render inside other pages and stand at no address of their own — a
    button that points at her is refused by the ONE rule both the picker
    and the resolver ask (`serves_at_address`), so what the dialog offers
    is exactly what the site renders. Red on the tip before the repair:
    the resolver asked only `is_published`, and a site-block button stood
    on the site with a 404 for her address."""
    from app.domains.cms.api import CmsPage
    from app.domains.cms.service import serves_at_address

    # The seed carries the home intro herself (one per tenant): the block
    # the button may not point at is the real one, not a copy of her.
    intro = db_session.query(CmsPage).filter(CmsPage.slug == "home-intro").first()
    assert intro is not None, "de zaaisel draagt geen home-intro"
    # Published, so the refusal below can only come from her being a site
    # block — not from her draft state.
    intro.is_published = True
    gewoon = CmsPage(title="Een pagina", slug="een-pagina-test", is_published=True)
    db_session.add(gewoon)
    db_session.flush()

    assert serves_at_address(intro) is False
    assert serves_at_address(gewoon) is True

    knop = _doc(
        {
            "type": "button",
            "attrs": {"label": "Naar het intro", "variant": "primary", "page_id": intro.id},
        }
    )
    assert render_document(knop, db_session) == ""
    assert "siteblok" in render_document(knop, db_session, preview=True)


def test_the_screen_button_needs_the_membership_module(db_session):
    """A3 of the review: the one application screen is mounted behind the
    membership module (main.py), so for a tenant without her the button
    is offered nowhere and an existing one is unreachable — the same one
    rule as every unreachable target: nothing on the site, the words in
    the preview. Red on the tip before the repair: the resolver wrote the
    link without a question."""
    from app.kernel.modules import ModuleCode, current_modules

    knop = _doc(
        {
            "type": "button",
            "attrs": {"label": "Word lid", "variant": "primary", "screen": "lid-worden"},
        }
    )

    # A tenant without the module: offered nowhere, rendered nowhere.
    token = current_modules.set(frozenset())
    try:
        assert render_document(knop, db_session) == ""
        assert "niet aanbiedt" in render_document(knop, db_session, preview=True)
    finally:
        current_modules.reset(token)

    # A tenant with her: the screen stands.
    token = current_modules.set(frozenset({str(ModuleCode.MEMBERSHIP)}))
    try:
        assert "/lid-worden" in render_document(knop, db_session)
    finally:
        current_modules.reset(token)


def test_an_empty_callout_renders_nothing(db_session):
    """S5 of the review: an empty callout stood on the site as an empty box
    of 34 px. She renders NOTHING — the author sees her in the editor, the
    visitor sees no empty frame. Red on the tip before the repair."""
    leeg = _doc({"type": "callout", "content": []})
    assert render_document(leeg, db_session) == ""
    met_woorden = _doc({"type": "callout", "content": [{"type": "text", "text": "Wel woorden."}]})
    assert "Wel woorden." in render_document(met_woorden, db_session)


def test_one_column_comes_back_as_plain_blocks():
    """S4 of the review: the author reaches a columns block with one
    column by a Backspace in the empty second column, and on the site she
    left half the width empty. The save unwraps her into her plain blocks
    — chosen over a refusal because the editor has no command that adds a
    column back: a refused document could only be fixed by deleting the
    block and retyping her words. Red on the tip before the repair: the
    one-column shape stored as she came."""
    één = document_from_editor(
        _doc(
            {
                "type": "columns",
                "attrs": {"align": "top"},
                "content": [{"type": "column", "content": [_par("Enige kolom")]}],
            }
        )
    )
    assert [node["type"] for node in één["content"]] == ["paragraph"], één["content"]
    assert "Enige kolom" in één["content"][0]["content"][0]["text"]

    twee = document_from_editor(
        _doc(
            {
                "type": "columns",
                "attrs": {"align": "top"},
                "content": [
                    {"type": "column", "content": [_par("Links")]},
                    {"type": "column", "content": [_par("Rechts")]},
                ],
            }
        )
    )
    assert twee["content"][0]["type"] == "columns"
