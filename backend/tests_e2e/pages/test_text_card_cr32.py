"""E2E: the text card, built through the dialog and measured (CR-32 phase 2,
AC3 and AC4).

The walk: the author inserts a card block, fills Titel, Nummer and Tekst and
chooses "Nergens heen"; saves and publishes; the site shows a card that says
something and is not a link. The measurement: three cards stand in one row at
1 280 px and under each other at 390 px; two cards stand in two columns.

Broken on purpose (15 October 2026): the dialog's "Nergens heen" removed → the
walk cannot make a text card; the `:has(>:nth-child(3))` rule of the kit taken
out → three cards no longer share a row and the row test is red.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63f8cfc0f01f0005000201a3c8c3a60000000049454e44ae426082"
)
SEEN: dict = {}
EDITOR = "#cp-document"
_MENU = f"{EDITOR} details.de-menu-insert"


def _cards(count: int) -> dict:
    return {
        "type": "cards",
        "content": [
            {
                "type": "card",
                "attrs": {
                    "title": f"Kaart {i + 1}",
                    "number": f"0{i + 1}",
                    "text": "Een alinea die iets zegt, lang genoeg om af te breken.",
                },
            }
            for i in range(count)
        ],
    }


@pytest.fixture(scope="module")
def setup():
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.cms.api import CmsPage, publish, save_document
    from app.domains.cms.service import create_page
    from app.domains.media.api import MediaAsset
    from app.schemas.cms import CmsPageCreate
    from tests.conftest import SEEDED_ADMIN_EMAIL

    tag = secrets.token_hex(3)
    db = SessionLocal()
    walk = create_page(db, CmsPageCreate(title="Kaartwandeling", slug=f"kaart-{tag}"))
    save_document(
        db,
        walk.id,
        {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Kaarten hieronder."}]}
            ],
        },
    )
    publish(db, walk.id)
    grid = create_page(db, CmsPageCreate(title="Kaartenrooster", slug=f"rooster-{tag}"))
    save_document(db, grid.id, {"type": "doc", "content": [_cards(3), _cards(2)]})
    publish(db, grid.id)
    picture = MediaAsset(
        kind="sponsor", title="Kaartbeeld", data=_PNG, content_type="image/png", byte_size=len(_PNG)
    )
    db.add(picture)
    db.flush()
    with_picture = _cards(3)
    # no number: it stands above the picture, which then starts below the card's top edge
    with_picture["content"][0]["attrs"] |= {"media_id": picture.id, "number": ""}
    bleed = create_page(db, CmsPageCreate(title="Kaartbeeld", slug=f"beeld-{tag}"))
    save_document(db, bleed.id, {"type": "doc", "content": [with_picture]})
    publish(db, bleed.id)
    db.commit()
    ids = [walk.id, grid.id, bleed.id]
    walk_id, walk_slug, grid_slug = walk.id, walk.slug, grid.slug
    SEEN["bleed"], SEEN["picture"] = bleed.slug, picture.id
    db.close()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, walk_id, walk_slug, grid_slug, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()
    cleanup = SessionLocal()
    try:
        cleanup.query(CmsPage).filter(CmsPage.id.in_(ids)).delete(synchronize_session=False)
        cleanup.query(MediaAsset).filter(MediaAsset.id == SEEN["picture"]).delete(
            synchronize_session=False
        )
        cleanup.commit()
    finally:
        cleanup.close()


def test_the_author_makes_a_text_card_through_the_dialog(setup):
    b, page_id, slug, _grid, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")
        page.locator(f"{_MENU} summary").click()
        page.locator(f"{_MENU} button", has_text="Kaarten").click()
        dialog = page.locator("[data-card-dialog]")
        page.wait_for_selector("[data-card-dialog] input[type=text] >> nth=0", state="visible")
        page.fill("#cp-document-card-title", "Wat wij doen")
        page.fill("#cp-document-card-number", "01")
        page.fill("#cp-document-card-text", "Wij bouwen en onderhouden.")
        dialog.locator("[data-destination-none]").click()
        dialog.locator("[data-card-apply]").click()
        page.wait_for_selector(f"{EDITOR} .tiptap .prose-card--text")
        assert page.locator(f"{EDITOR} .tiptap .prose-card-number").inner_text() == "01"

        page.locator("[data-action-bar] button[data-form-save]").click()
        page.wait_for_url(f"**/admin/paginas/{page_id}*opgeslagen=1*", timeout=15000)
        pagina_klaar(page)
        page.locator("button", has_text="Publiceren").click()
        page.wait_for_function(
            "() => document.querySelector('[data-record-head]') && "
            "!document.querySelector('[data-record-head]').textContent.includes('Concept gewijzigd')",
            timeout=15000,
        )
        page.goto(f"/{slug}")
        pagina_klaar(page)
        card = page.locator(".cms-page .prose-card--text")
        assert card.count() == 1
        assert card.locator("a").count() == 0, "a text card is not a link"
        text = card.inner_text()
        assert "Wat wij doen" in text and "Wij bouwen en onderhouden." in text and "01" in text
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


_ROWS = """() => [...document.querySelectorAll('.cms-page .prose-cards')].map(block =>
  [...block.querySelectorAll('.prose-card')].map(c => { const r = c.getBoundingClientRect();
    return {left: Math.round(r.left), top: Math.round(r.top), width: Math.round(r.width)}; }))"""


def test_three_cards_share_a_row_at_1280_and_stack_at_390(setup):
    b, _id, _slug, grid, _session = setup
    wide = b.new_page(base_url=BASE, viewport={"width": 1280, "height": 900})
    try:
        wide.goto(f"/{grid}")
        pagina_klaar(wide)
        three, two = wide.evaluate(_ROWS)
        print("MEASURE text cards 1280", three, two)
        assert len({c["top"] for c in three}) == 1 and len({c["left"] for c in three}) == 3
        assert len({c["top"] for c in two}) == 1 and len({c["left"] for c in two}) == 2
    finally:
        wide.close()
    phone = b.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    try:
        phone.goto(f"/{grid}")
        pagina_klaar(phone)
        three, two = phone.evaluate(_ROWS)
        print("MEASURE text cards 390", three, two)
        for block in (three, two):
            assert len({c["left"] for c in block}) == 1, "the cards do not stand under each other"
            assert len({c["top"] for c in block}) == len(block)
        assert phone.evaluate("document.documentElement.scrollWidth === innerWidth")
    finally:
        phone.close()


_LOOK = """() => { const card = document.querySelector('.cms-page .prose-card--text');
  const n = getComputedStyle(card.querySelector('.prose-card-number'));
  const c = getComputedStyle(card);
  const t = getComputedStyle(card.querySelector('.prose-card-title'));
  const soft = getComputedStyle(card.querySelector('.prose-card-text')).color;
  return {number: [n.fontSize, n.fontWeight, n.color === soft], padding: [c.paddingTop, c.paddingRight,
    c.paddingBottom, c.paddingLeft], title: t.fontSize}; }"""

_BLEED = """() => { const card = document.querySelector('.cms-page .prose-card');
  const img = card.querySelector('img.prose-card-picture');
  const a = card.getBoundingClientRect(), b = img.getBoundingClientRect();
  return {left: Math.round(b.left - a.left), top: Math.round(b.top - a.top),
    right: Math.round(a.right - b.right), picture: Math.round(b.width), card: Math.round(a.width)}; }"""


@pytest.mark.parametrize("width", [390, 1100])
def test_the_text_card_is_quieter_roomier_and_its_title_larger(setup, width):
    """#2170: the number 12 px, normal weight, the muted text colour (the card text's own); the padding
    24 px; the title 20 px; a picture still bleeds to the card's edges.

    Broken on purpose: the number back to 14 px bold brand colour, the padding
    back to 16 px, the picture's negative margin left at -16 px → this is red."""
    b, _id, _slug, grid, _session = setup
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        page.goto(f"/{grid}")
        pagina_klaar(page)
        look = page.evaluate(_LOOK)
        print("MEASURE text card", width, look)
        # True: the number has the colour of the card's own text
        assert look["number"] == ["12px", "400", True], look
        assert look["padding"] == ["24px"] * 4, look
        assert look["title"] == "20px", look
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
        page.goto(f"/{SEEN['bleed']}")
        pagina_klaar(page)
        bleed = page.evaluate(_BLEED)
        print("MEASURE picture bleed", width, bleed)
        assert (bleed["left"], bleed["top"], bleed["right"]) == (1, 1, 1), bleed  # the 1 px border
        assert bleed["picture"] == bleed["card"] - 2, bleed
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
    finally:
        page.close()
