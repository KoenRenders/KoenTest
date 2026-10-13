"""E2E: a placed picture can be changed (CR-17).

The comparison with the Trix editor (14 October 2026) found that a picture,
once placed, could not be changed: a click on it offered nothing, and the
insert menu's "Afbeelding" with the picture selected opened an EMPTY dialog
that put a second picture beside the first. To correct a typing fault in the
alternative text the author had to remove the picture and place it again —
where the Trix editor offered "Bewerken" on a picture (#1224).

Now a click on a placed picture, and the menu's item with a picture selected,
open the picture's dialog with what that picture holds — its picture, its
alternative text, its caption, its placement — and Invoegen saves into that
picture, at its own place. As the button's dialog does.

Read from the stored document and from the public page, at 390 and 1 440 px:
one picture before and one after; the new alternative text, caption and
placement on that picture; the public page's `alt`; and a dialog closed
without a choice changes nothing.

Broken on purpose (14 October 2026), each put back by the reverse edit: the
dialog opened empty for a placed picture → "the dialog does not hold what the
picture holds"; the menu's item not looking at the selection → the same,
through the menu; a click on a picture opening nothing → the dialog is not
visible. Two things were built first and taken out again because no test
could turn red on them: a position carried through the dialog (the picture
is the selection, and an insert over a selected block replaces it) and the
picture selected once more when its dialog opens.
"""

import os
import sys
import time

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.pages.test_cards_1770 import (  # noqa: E402
    _SETTLE,
    EDITOR,
    HELD,
    INSERT,
    _new_page,
    _open,
    _paragraph,
)
from tests_e2e.pages.test_reading_width_1671 import _photo  # noqa: E402
from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

DIALOG = "div[x-show='figure'][role='dialog']"
OLD = {"alt": "Een foto van het pleinn", "caption": "Het plein in de zomer", "placement": "full"}


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _stored_figures(page_id: int, published: bool = False) -> list[dict]:
    """The pictures of the page's draft (or its published document), as stored."""
    from app.database import SessionLocal
    from app.domains.cms.models import CmsPageTranslation

    found: list[dict] = []

    def walk(node):
        if node.get("type") == "figure":
            found.append(node.get("attrs") or {})
        for child in node.get("content") or []:
            walk(child)

    db = SessionLocal()
    try:
        row = db.query(CmsPageTranslation).filter(CmsPageTranslation.page_id == page_id).first()
        walk((row.published_json if published else row.draft_json) or {})
        return found
    finally:
        db.close()


def _page(browser, session, name: str, width: int):
    media_id = _photo()
    content = [
        _paragraph("Boven de afbeelding."),
        {"type": "figure", "attrs": {"media_id": media_id, **OLD}},
        _paragraph("Onder de afbeelding."),
    ]
    page_id, slug = _new_page(name, {"type": "doc", "content": content})
    page = _open(browser, session, page_id, width)
    page.evaluate(_SETTLE)
    return page, page_id, slug, media_id


def _holds(page) -> dict:
    """What the open dialog shows: the fields, the chosen placement, whether a
    picture is chosen."""
    return {
        "alt": page.locator("#cp-document-fig-alt").input_value(),
        "caption": page.locator("#cp-document-fig-caption").input_value(),
        "a picture is chosen": page.locator(f"{DIALOG} img").first.is_visible(),
        "Invoegen may be pressed": page.locator(
            f"{DIALOG} button", has_text="Invoegen"
        ).is_enabled(),
    }


def _save_and_wait(page, page_id: int, expected) -> list[dict]:
    with page.expect_navigation(timeout=15000):
        page.locator("[data-action-bar] button[data-form-save]").click()
    pagina_klaar(page)
    page.wait_for_selector(f"{EDITOR} .tiptap")
    deadline = time.time() + 15
    stored: list[dict] = []
    while time.time() < deadline:
        stored = _stored_figures(page_id)
        if expected(stored):
            return stored
        time.sleep(0.3)  # the store is read until it answers; nothing in the page to wait on
    raise AssertionError(f"after the save the stored pictures are not what was expected: {stored}")


@pytest.mark.parametrize("width", [390, 1440])
def test_a_click_on_a_placed_picture_changes_that_picture(setup, width):
    browser, session = setup
    page, page_id, slug, media_id = _page(browser, session, f"Afbeelding wijzigen {width}", width)
    try:
        figures = page.locator(f"{EDITOR} .tiptap figure")
        expect(figures).to_have_count(1)
        figures.first.click()
        expect(page.locator(DIALOG)).to_be_visible()
        held = _holds(page)
        assert held == {
            "alt": OLD["alt"],
            "caption": OLD["caption"],
            "a picture is chosen": True,
            "Invoegen may be pressed": True,
        }, f"the dialog does not hold what the picture holds: {held}"

        # The typing fault corrected, another caption, another placement.
        page.locator("#cp-document-fig-alt").fill("Een foto van het plein")
        page.locator("#cp-document-fig-caption").fill("Het plein in de winter")
        page.locator(f"{DIALOG} button", has_text="Klein").click()
        page.locator(f"{DIALOG} button", has_text="Invoegen").click()
        expect(page.locator(DIALOG)).to_be_hidden()

        # One picture, the same one, with the new words — in the editor…
        expect(figures).to_have_count(1)
        assert figures.first.locator("img").get_attribute("alt") == "Een foto van het plein"
        # It is still the selection: it was changed where it stands, not
        # replaced by a new one with the caret behind it.
        page.evaluate("() => window.__settle()")
        assert page.locator(f"{EDITOR} .tiptap figure.ProseMirror-selectednode").count() == 1, (
            "the changed picture is not the selection any more"
        )
        # …and in what the save stores.
        stored = _save_and_wait(
            page, page_id, lambda f: len(f) == 1 and f[0].get("alt") == "Een foto van het plein"
        )
        assert len(stored) == 1, f"the stored document holds {len(stored)} pictures"
        assert (stored[0]["media_id"], stored[0]["caption"], stored[0]["placement"]) == (
            media_id,
            "Het plein in de winter",
            "small",
        ), stored[0]
        assert page.errors == [], f"the screen throws: {page.errors}"

        # Published: the visitor's page carries the new alternative text.
        page.locator("button", has_text="Publiceren").click()
        page.wait_for_function(
            "() => document.querySelector('[data-record-head]') && "
            "!document.querySelector('[data-record-head]').textContent.includes('Concept gewijzigd')",
            timeout=15000,
        )
        public = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
        try:
            public.goto(f"/{slug}")
            pagina_klaar(public)
            shown = public.locator(".doc-page figure img")
            expect(shown).to_have_count(1)
            assert shown.get_attribute("alt") == "Een foto van het plein"
            assert "Het plein in de winter" in public.locator(".doc-page figure").inner_text()
        finally:
            public.close()
    finally:
        page.close()


def test_the_insert_menu_with_a_picture_selected_changes_that_picture(setup):
    """The keyboard's way: the picture selected by the arrows, then the insert
    menu's "Afbeelding" — the dialog holds that picture, and Invoegen changes
    it; it does not put a second one beside it."""
    browser, session = setup
    page, page_id, _slug, _media_id = _page(browser, session, "Afbeelding via het menu", 1440)
    try:
        page.locator(f"{EDITOR} .tiptap > p").first.click()
        page.keyboard.press("End", delay=HELD)
        page.keyboard.press("ArrowRight", delay=HELD)
        page.evaluate("() => window.__settle()")
        assert page.locator(f"{EDITOR} .tiptap figure.ProseMirror-selectednode").count() == 1, (
            "the test did not select the picture with the arrow"
        )
        page.locator(f"{INSERT} summary").click()
        page.locator(f"{INSERT} button", has_text="Afbeelding").click()
        expect(page.locator(DIALOG)).to_be_visible()
        assert _holds(page)["alt"] == OLD["alt"], "the dialog does not hold what the picture holds"
        page.locator("#cp-document-fig-alt").fill("Een andere tekst")
        page.locator(f"{DIALOG} button", has_text="Invoegen").click()
        expect(page.locator(DIALOG)).to_be_hidden()
        expect(page.locator(f"{EDITOR} .tiptap figure")).to_have_count(1)
        stored = _save_and_wait(
            page, page_id, lambda f: len(f) == 1 and f[0].get("alt") == "Een andere tekst"
        )
        assert len(stored) == 1
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


def test_the_picture_dialog_closed_without_a_choice_changes_nothing(setup):
    """Opened on a placed picture and closed with Annuleren: the form holds
    the same document, the picture is still the selection, and the insert
    menu's item with NO picture selected still opens an empty dialog."""
    browser, session = setup
    page, _page_id, _slug, _media_id = _page(browser, session, "Afbeelding ongewijzigd", 1440)
    try:
        before = page.locator("#cp-document-input").input_value()
        page.locator(f"{EDITOR} .tiptap figure").click()
        expect(page.locator(DIALOG)).to_be_visible()
        page.locator(f"{DIALOG} button", has_text="Annuleren").click()
        expect(page.locator(DIALOG)).to_be_hidden()
        page.evaluate("() => window.__settle()")
        assert page.locator("#cp-document-input").input_value() == before
        assert page.locator(f"{EDITOR} .tiptap figure.ProseMirror-selectednode").count() == 1

        page.locator(f"{EDITOR} .tiptap > p").first.click()
        page.locator(f"{INSERT} summary").click()
        page.locator(f"{INSERT} button", has_text="Afbeelding").click()
        expect(page.locator(DIALOG)).to_be_visible()
        held = _holds(page)
        assert (held["alt"], held["caption"], held["Invoegen may be pressed"]) == ("", "", False), (
            f"a new picture's dialog opens with another picture's words: {held}"
        )
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()
