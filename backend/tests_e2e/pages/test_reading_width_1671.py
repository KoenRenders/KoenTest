"""E2E: a page reads at her width (CR-17 #1671, slice 4; C6 11).

In a browser, because reading width is a measurement of the rendered page:
the column the visitor reads (768 px on a desktop, left-aligned like a
record page — design-system-end-state §1.4 — and the viewport minus her
gutters on a phone), a table wider than the phone scrolls INSIDE her block
while the page does not scroll sideways (CR-11 Q14's declared exception),
and a figure carries her radius and her shadow as computed styles, not as
promises in a stylesheet.

The record form's growth (Koen, 9 October 2026: "links houden, maar het
scherm benutten") is measured here too: on a wide screen the form column
reaches her cap of 1 056 px — red on the old 768 cap, which left most of a
wide screen empty.
"""

import io
import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

_DOC = {
    "type": "doc",
    "content": [
        {
            "type": "heading",
            "attrs": {"level": 2},
            "content": [{"type": "text", "text": "Wat er te doen is"}],
        },
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Een alinea met "},
                {"type": "text", "marks": [{"type": "bold"}], "text": "vette"},
                {"type": "text", "text": " woorden, zodat de prose-regels zichtbaar meedraaien."},
            ],
        },
        {
            "type": "table",
            "content": [
                {
                    "type": "tableRow",
                    "attrs": {"section": "head"},
                    "content": [
                        {
                            "type": "tableHeader",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Onderdeel"}],
                                }
                            ],
                        },
                        {
                            "type": "tableHeader",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Wat het kost"}],
                                }
                            ],
                        },
                        {
                            "type": "tableHeader",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Wanneer"}],
                                }
                            ],
                        },
                        {
                            "type": "tableHeader",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "Waar"}]}
                            ],
                        },
                        {
                            "type": "tableHeader",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Inschrijven"}],
                                }
                            ],
                        },
                    ],
                },
                {
                    "type": "tableRow",
                    "attrs": {"section": "body"},
                    "content": [
                        {
                            "type": "tableCell",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Wandeling"}],
                                }
                            ],
                        },
                        {
                            "type": "tableCell",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "€ 3,00"}],
                                }
                            ],
                        },
                        {
                            "type": "tableCell",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {"type": "text", "text": "zondagochtend, bij goed weer"}
                                    ],
                                }
                            ],
                        },
                        {
                            "type": "tableCell",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "aan de kerk"}],
                                }
                            ],
                        },
                        {
                            "type": "tableCell",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "aan de balie"}],
                                }
                            ],
                        },
                    ],
                },
            ],
        },
    ],
}


def _photo() -> int:
    """A photo with real bytes, so the browser really loads her."""
    from PIL import Image

    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.media.models import MediaAsset

    buf = io.BytesIO()
    Image.new("RGB", (320, 200), (40, 60, 180)).save(buf, format="PNG")
    png = buf.getvalue()
    db = SessionLocal()
    try:
        asset = MediaAsset(
            kind="activity_photo",
            title=f"Leesbreedte {secrets.token_hex(2)}",
            data=png,
            content_type="image/png",
            thumbnail=png,
            thumb_content_type="image/png",
            width=320,
            height=200,
            byte_size=len(png),
            sort_order=0,
            is_active=True,
        )
        db.add(asset)
        db.commit()
        return asset.id
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    import copy

    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.cms.api import create_page, publish, save_document
    from app.schemas.cms import CmsPageCreate
    from tests.conftest import SEEDED_ADMIN_EMAIL

    tag = secrets.token_hex(3)
    doc = copy.deepcopy(_DOC)
    doc["content"].append(
        {
            "type": "figure",
            "attrs": {
                "media_id": _photo(),
                "alt": "Een probeerbeeld in verenigingskleur",
                "caption": "De figuur draagt haar radius en schaduw.",
                "placement": "full",
            },
        }
    )
    db = SessionLocal()
    page = create_page(db, CmsPageCreate(title="Leesbreedte", slug=f"leesbreedte-{tag}"))
    page_id, slug = page.id, page.slug
    db.close()
    s = SessionLocal()
    save_document(s, page_id, doc)
    publish(s, page_id)
    s.close()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, page_id, slug, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


_COLUMN = "() => { const r = document.querySelector('.doc-page').getBoundingClientRect(); return {x: Math.round(r.x), w: Math.round(r.width)} }"


def test_the_page_reads_at_768_left_aligned(setup):
    """C6 11: the column is 768 px of reading width, left-aligned against
    the shell's margin — never centred (design-system-end-state §1.4)."""
    b, _page_id, slug, _session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    try:
        page.goto(f"/{slug}")
        pagina_klaar(page)
        col = page.evaluate(_COLUMN)
        main = page.evaluate(
            "() => { const r = document.querySelector('main').getBoundingClientRect(); return {x: Math.round(r.x), w: Math.round(r.width)} }"
        )
        assert col["w"] == 768, f"the reading column is {col['w']} px, not 768"
        assert col["x"] == main["x"], "the reading column is not left-aligned"
    finally:
        page.close()


def test_on_a_phone_the_column_is_the_viewport_minus_her_gutters(setup):
    """C6 11: on a 390 px phone the column is the viewport minus her 32 px
    of gutters — the shell's <main> gives them."""
    b, _page_id, slug, _session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    try:
        page.goto(f"/{slug}")
        pagina_klaar(page)
        col = page.evaluate(_COLUMN)
        assert col["w"] == 358, f"the phone column is {col['w']} px, not 358"
        widths = page.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
        assert widths == [390, 390], "the page scrolls sideways on a phone"
    finally:
        page.close()


def test_a_wide_table_scrolls_inside_her_block_on_a_phone(setup):
    """C6 11: the table is wider than the phone; her BLOCK scrolls inside
    itself and the page does not scroll sideways."""
    b, _page_id, slug, _session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    try:
        page.goto(f"/{slug}")
        pagina_klaar(page)
        table = page.evaluate(
            "() => { const t = document.querySelector('.doc-page table'); return {sw: t.scrollWidth, cw: t.clientWidth} }"
        )
        assert table["sw"] > table["cw"], "the wide table does not scroll inside her block"
        widths = page.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
        assert widths == [390, 390], "the page scrolls sideways with her table"
    finally:
        page.close()


def test_the_figure_carries_her_radius_and_shadow(setup):
    """C6 11: the radius and the card shadow are computed styles of the
    picture the visitor gets, not promises in a stylesheet."""
    b, _page_id, slug, _session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    try:
        page.goto(f"/{slug}")
        pagina_klaar(page)
        fig = page.evaluate(
            "() => { const i = document.querySelector('.doc-page figure img'); const s = getComputedStyle(i); return {r: s.borderTopLeftRadius, sh: s.boxShadow} }"
        )
        assert fig["r"] == "14px", f"the figure's radius is {fig['r']}, not 14px"
        assert fig["sh"] != "none", "the figure lost her shadow"
    finally:
        page.close()


def test_the_record_form_grows_with_the_screen(setup):
    """Koen, 9 October 2026: "links houden, maar het scherm benutten" — on
    a wide screen the form column reaches her cap of 1 056 px (the summary
    stays 300 px beside her). Red on the old 768 cap."""
    b, page_id, _slug, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1920, "height": 1080})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        widths = page.evaluate(
            "() => { const f = document.querySelector('[data-form-column]').getBoundingClientRect();"
            " const a = document.querySelector('[data-summary-column]');"
            " const ar = a ? a.getBoundingClientRect().width : 0;"
            " return {form: Math.round(f.width), aside: Math.round(ar)} }"
        )
        assert widths["form"] == 1056, f"the form column is {widths['form']} px, not her 1056 cap"
        assert widths["aside"] == 300, f"the summary column is {widths['aside']} px, not 300"
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()
