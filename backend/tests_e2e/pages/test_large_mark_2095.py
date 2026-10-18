"""E2E: the mark "Groot" of the page editor (#2095).

The author types the line, selects the amount and presses "Groot". The public page shows the amount larger than its
neighbours — measured as the computed font size of the span against the
paragraph's — and the line stays on one line at 390 px (a short line). The
stored document holds the mark on the amount only and the page keeps her one `h1` and the span stands in no heading.

Broken on purpose (18 October 2026), put back by the reverse edit: the
class's font size in `scripts/build-css.sh` set to the body's → both widths
red, the span as large as the paragraph.
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
    _new_page,
    _open,
    _paragraph,
)
from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

_MEASURE = """() => {
  const span = document.querySelector('.doc-page p span.prose-large');
  const p = span.closest('p');
  const lines = Math.round(p.getBoundingClientRect().height / parseFloat(getComputedStyle(span).lineHeight));
  return {span: parseFloat(getComputedStyle(span).fontSize),
          paragraph: parseFloat(getComputedStyle(p).fontSize),
          weight: getComputedStyle(span).fontWeight,
          h1s: document.querySelectorAll('h1').length,
          inHeading: !!span.closest('h1,h2,h3,h4'),
          lines: lines};
}"""


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _marked_words(page_id: int) -> list[str]:
    """The words of the draft that carry the mark `large`."""
    from app.database import SessionLocal
    from app.domains.cms.models import CmsPageTranslation

    db = SessionLocal()
    try:
        row = db.query(CmsPageTranslation).filter(CmsPageTranslation.page_id == page_id).first()
        found: list[str] = []

        def walk(node):
            if node.get("type") == "text" and any(
                m.get("type") == "large" for m in node.get("marks") or []
            ):
                found.append(node["text"])
            for child in node.get("content") or []:
                walk(child)

        walk(row.draft_json or {})
        return found
    finally:
        db.close()


@pytest.mark.parametrize("width", [390, 1440])
def test_a_large_amount_inside_an_ordinary_line(setup, width):
    browser, session = setup
    page_id, slug = _new_page(
        f"Groot {width}", {"type": "doc", "content": [_paragraph("Lidgeld ")]}
    )
    page = _open(browser, session, page_id, width)
    try:
        page.evaluate(_SETTLE)
        page.locator(f"{EDITOR} .tiptap > p").first.click()
        page.keyboard.press("End", delay=HELD)
        page.keyboard.type("€35 per gezin", delay=20)
        for _ in range(len(" per gezin")):
            page.keyboard.press("ArrowLeft", delay=HELD)
        for _ in range(len("€35")):
            page.keyboard.press("Shift+ArrowLeft", delay=HELD)
        page.locator(f"{EDITOR} .de-bar button", has_text="Groot").click()
        page.evaluate("() => window.__settle()")
        expect(page.locator(f"{EDITOR} .tiptap span.prose-large")).to_have_text("€35")

        with page.expect_navigation(timeout=15000):
            page.locator("[data-action-bar] button[data-form-save]").click()
        pagina_klaar(page)
        deadline = time.time() + 15
        marked: list[str] = []
        while time.time() < deadline:
            marked = _marked_words(page_id)
            if marked:
                break
            time.sleep(0.3)  # the store is read until it answers; nothing in the page to wait on
        assert marked == ["€35"], f"at {width}: the marked words are {marked}"
        assert page.errors == [], f"the screen throws: {page.errors}"

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
            measured = public.evaluate(_MEASURE)
            print("MEASURE groot", width, measured)
            assert measured["span"] > measured["paragraph"], measured
            assert measured["h1s"] == 1 and not measured["inHeading"], "the mark is no heading"
            assert measured["lines"] == 1, f"the short line wraps at {width}: {measured}"
            shot = os.environ.get("GROOT_SHOT")
            if shot and width == 390:
                public.screenshot(path=shot, clip={"x": 0, "y": 0, "width": 390, "height": 400})
        finally:
            public.close()
    finally:
        page.close()
