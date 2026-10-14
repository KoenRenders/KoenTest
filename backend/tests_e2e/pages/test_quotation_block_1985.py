"""E2E: the quotation block of the page editor (#1985).

Three ways in, each at 390 and 1 440 px: the toolbar's "Citaat", "> " typed
at the start of a paragraph, and a pasted `<blockquote>`. Each gives ONE
quotation in the stored document and one `<blockquote>` on the public page,
and Enter on the empty line inside the quotation leaves it: the words typed
next stand in a paragraph after it. Keys are held (`HELD`).

Broken on purpose (14 October 2026), each put back by the reverse edit: the
quotation off in the editor (`blockquote:` false) → no button, "> " stays
text, the paste a paragraph — all six red; the toolbar's quotation not built
→ the button way red at both widths.
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

PASTE = """(html) => {
  const data = new DataTransfer();
  data.setData('text/html', html);
  data.setData('text/plain', 'Een citaat.');
  document.querySelector('#cp-document .tiptap').dispatchEvent(
    new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));
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


def _stored(page_id: int) -> list:
    """The top blocks of the page's draft, as (type, words) pairs."""
    from app.database import SessionLocal
    from app.domains.cms.models import CmsPageTranslation

    def words(node):
        if node.get("type") == "text":
            return node.get("text", "")
        return "".join(words(child) for child in node.get("content") or [])

    db = SessionLocal()
    try:
        row = db.query(CmsPageTranslation).filter(CmsPageTranslation.page_id == page_id).first()
        blocks = [
            (block["type"], words(block)) for block in (row.draft_json or {}).get("content") or []
        ]
        # The editor keeps an empty paragraph at the end of the page to type in.
        while blocks and blocks[-1] == ("paragraph", ""):
            blocks.pop()
        return blocks
    finally:
        db.close()


EXPECTED = [("paragraph", "Boven."), ("blockquote", "Een citaat."), ("paragraph", "Na het citaat.")]


@pytest.mark.parametrize("width", [390, 1440])
@pytest.mark.parametrize("way", ["button", "typed", "pasted"])
def test_a_quotation_by_each_way_is_one_quotation_on_the_page(setup, way, width):
    browser, session = setup
    page_id, slug = _new_page(
        f"Citaat {way} {width}", {"type": "doc", "content": [_paragraph("Boven.")]}
    )
    page = _open(browser, session, page_id, width)
    try:
        page.evaluate(_SETTLE)
        page.locator(f"{EDITOR} .tiptap > p").first.click()
        page.keyboard.press("End", delay=HELD)
        page.keyboard.press("Enter", delay=HELD)
        if way == "button":
            page.locator(f"{EDITOR} .de-bar button", has_text="Citaat").click()
            page.keyboard.type("Een citaat.", delay=20)
        elif way == "typed":
            page.keyboard.type("> Een citaat.", delay=20)
        else:
            page.evaluate(PASTE, "<blockquote><p>Een citaat.</p></blockquote>")
        page.evaluate("() => window.__settle()")
        quotes = page.locator(f"{EDITOR} .tiptap blockquote")
        expect(quotes).to_have_count(1)
        # Enter at the end of the quotation's words, Enter on the empty line: out.
        page.keyboard.press("Enter", delay=HELD)
        page.keyboard.press("Enter", delay=HELD)
        page.keyboard.type("Na het citaat.", delay=20)
        page.evaluate("() => window.__settle()")
        expect(quotes).to_have_count(1)

        with page.expect_navigation(timeout=15000):
            page.locator("[data-action-bar] button[data-form-save]").click()
        pagina_klaar(page)
        deadline = time.time() + 15
        stored = []
        while time.time() < deadline:
            stored = _stored(page_id)
            if stored == EXPECTED:
                break
            time.sleep(0.3)  # the store is read until it answers; nothing in the page to wait on
        assert stored == EXPECTED, f"{way} at {width}: the stored document is {stored}"
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
            shown = public.locator(".doc-page blockquote")
            expect(shown).to_have_count(1)
            assert shown.inner_text().strip() == "Een citaat."
        finally:
            public.close()
    finally:
        page.close()
