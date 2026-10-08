"""E2E: the page screen as a record page (CR-17 #1671, slice 3; C6 15).

In a browser, because the screen is what the eye gets: the editor on her
own record page, the insert menu, the save through the record form's bar,
and the phone's 390 px — the page's width and the bar's cover of the
fields are pixels, not templates.

The flow the assignment names, measured: the editor OPENS with the page's
own document, the insert menu ADDS a table, the bar's Opslaan SAVES her,
the reload shows the saved draft as the editor's document (C6 1's round
trip through the real save), the record says "concept gewijzigd" (C6 4),
and nothing scrolls sideways on a phone.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

EDITOR = "#cp-document"


@pytest.fixture(scope="module")
def setup():
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.cms.api import CmsPage
    from tests.conftest import SEEDED_ADMIN_EMAIL

    tag = secrets.token_hex(3)
    db = SessionLocal()
    page = CmsPage(
        title="Schermtest",
        slug=f"scherm-{tag}",
        content="<p>De woorden die er vandaag staan.</p>",
        is_published=True,
    )
    db.add(page)
    db.commit()
    page_id, slug = page.id, page.slug
    db.close()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, page_id, slug, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


_TABLES = "() => document.querySelectorAll('#cp-document .tiptap table').length"
_WIDTH = "() => [document.documentElement.scrollWidth, innerWidth]"


@pytest.mark.parametrize("width", [1440, 390])
def test_the_editor_saves_a_block_on_the_record_page(setup, width):
    """Open, insert, save — the round trip of C6 1 through the real route,
    on a phone's width too: the page stays exactly as wide as her screen."""
    b, page_id, slug, session = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")
        assert "De woorden die er vandaag staan." in page.locator(f"{EDITOR}").inner_text()

        before = page.evaluate(_TABLES)
        page.locator(f"{EDITOR} summary").click()
        page.locator(f"{EDITOR} details button", has_text="Tabel").click()
        page.wait_for_function(f"{_TABLES} === {before + 1}")

        # Opslaan through the record form's bar: the one save of the whole
        # screen (§3.6), with her busy state — the redirect follows.
        page.locator("[data-action-bar] button[data-form-save]").click()
        page.wait_for_url(f"**/admin/paginas/{page_id}*opgeslagen=1*", timeout=15000)
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")

        # The saved draft is what the editor opens after the reload — the
        # table survived the round trip through the real save (C6 1).
        assert page.evaluate(_TABLES) == before + 1, "the saved table is gone after the reload"
        # C6 4: the site keeps her published words; the record carries her
        # changed-draft badge.
        assert "Concept gewijzigd" in page.locator("[data-record-head]").inner_text()
        page.goto(f"/{slug}")
        pagina_klaar(page)
        assert "De woorden die er vandaag staan." in page.locator("body").inner_text()

        # Nothing scrolls sideways — on the public page too (AC6).
        assert page.evaluate(_WIDTH) == [width, width], "the page scrolls sideways"
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


def test_the_sticky_bar_covers_no_field_on_a_phone(setup):
    """C6 15: at 390 px the record form's bar — sticky above the window's
    bottom while the form is longer than the screen — may cover no field.
    Measured as a visitor works: a real tap on the slug field (the
    browser's own focus scroll, not a forced scroll to the bottom edge),
    then the two rectangles."""
    b, page_id, _slug, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")

        # A real tap: scroll the field into reach by hand first (the screen
        # opens at the top), then click — the browser does her own focus
        # scroll, exactly what a thumbs works with.
        page.locator("#cp-slug").scroll_into_view_if_needed()
        page.locator("#cp-slug").click()
        overlap = page.evaluate(
            """() => { const field = document.getElementById('cp-slug');
              const bar = document.querySelector('[data-action-bar]');
              const f = field.getBoundingClientRect();
              const r = bar.getBoundingClientRect();
              return {field: [f.top, f.bottom], bar: [r.top, r.bottom],
                      covers: f.bottom > r.top && f.top < r.bottom}; }"""
        )
        print("MEASURE record bar cover", overlap)
        assert not overlap["covers"], f"the sticky bar covers the slug field: {overlap}"
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


def test_a_page_created_through_the_screen_opens_and_saves(setup):
    """The author's first minute with a new page, through the real app.

    The create screen was the one door without an e2e — and the one that
    broke (Koen, 8 October 2026, on the local version): the app's session
    does not autoflush, so the create's double translation row died at the
    commit and the author read "Er ging iets mis; je wijziging is niet
    bewaard." A pytest could not see it — the test session autoflushes,
    the app session does not. Create through the screen, land on her
    record page, write a block, save: the new page works like a saved one.
    """
    import re as _re

    b, _page_id, _slug, session = setup
    tag = secrets.token_hex(3)
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto("/admin/paginas/nieuw")
        pagina_klaar(page)
        page.fill("#title", "E2e aanmaak")
        page.fill("#slug", f"e2e-aanmaak-{tag}")
        page.locator('form[hx-post="/admin/paginas"] button[type="submit"]').click()
        page.wait_for_url(_re.compile(r"/admin/paginas/\d+"), timeout=15000)
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")

        page.click(f"{EDITOR} .tiptap")
        page.keyboard.type("Het eerste blok van een nieuwe pagina.")
        page.locator("[data-action-bar] button[data-form-save]").click()
        page.wait_for_url(_re.compile(r"opgeslagen=1"), timeout=15000)
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")
        assert "Het eerste blok van een nieuwe pagina." in page.locator(EDITOR).inner_text(), (
            "the typed words are gone after the save"
        )
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()
