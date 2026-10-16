"""E2E: two gaps of a paste into the page editor (#2028).

1. A line break inside bold text: a pasted `<strong>Een<br>twee</strong>` gave
   the break the bold mark, and the save refused the whole document over
   `hardBreak.marks`. Now the break carries no mark, the words around it keep
   theirs, and the page saves.
2. A button, copied and pasted back: the editor drew `<a data-button>` with
   its label as text and nothing else, so a copy carried neither the label
   nor the destination, and `<a data-button href>` became a link. Now a
   button to an outside address, to a page and to a screen comes back the same
   button, and a pasted `<a data-button href>` is a button.

Measured before the repair (16 October 2026, a probe on master): the copy was
`<a data-button class="…">Buiten</a>`, and its paste a button with label "" and
no destination; the bold break was `{"type": "hardBreak", "marks": [bold]}`.

Broken on purpose (16 October 2026): `breakWithoutMarks` taken out of the
editor's extensions → the bold-break test is red on the save; the button's
`renderHTML` back to the bare element → the copy test is red on the label and
the destinations; the parse rule's `priority: 60` taken out → the pasted
`<a data-button href>` is a link and that case is red.
"""

import json
import os
import sys
import time

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.pages.test_cards_1770 import (  # noqa: E402
    _SETTLE,
    EDITOR,
    HELD,
    _new_page,
    _open,
    _paragraph,
)
from tests_e2e.pages.test_quotation_block_1985 import PASTE  # noqa: E402
from tests_e2e.schermen import pagina_klaar  # noqa: E402


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _draft(page_id: int) -> dict:
    from app.database import SessionLocal
    from app.domains.cms.models import CmsPageTranslation

    db = SessionLocal()
    try:
        row = db.query(CmsPageTranslation).filter(CmsPageTranslation.page_id == page_id).first()
        return row.draft_json or {}
    finally:
        db.close()


def _save_and_wait(page, page_id: int, done) -> dict:
    with page.expect_navigation(timeout=15000):
        page.locator("[data-action-bar] button[data-form-save]").click()
    pagina_klaar(page)
    deadline = time.time() + 15
    draft = {}
    while time.time() < deadline:
        draft = _draft(page_id)
        if done(draft):
            break
        time.sleep(0.3)  # the store is read until it answers; nothing in the page to wait on
    return draft


def _in_editor(page) -> dict:
    return json.loads(page.locator("#cp-document-input").input_value())


@pytest.mark.parametrize("width", [390, 1440])
def test_a_bold_line_break_is_pasted_and_saved(setup, width):
    browser, session = setup
    page_id, _slug = _new_page(
        f"Vette regel {width}", {"type": "doc", "content": [_paragraph("Boven.")]}
    )
    page = _open(browser, session, page_id, width)
    try:
        page.evaluate(_SETTLE)
        page.locator(f"{EDITOR} .tiptap > p").first.click()
        page.keyboard.press("End", delay=HELD)
        page.keyboard.press("Enter", delay=HELD)
        page.evaluate(PASTE, "<p><strong>Een<br>twee</strong></p>")
        page.evaluate("() => window.__settle()")

        def pasted(draft):
            return any(
                node.get("type") == "hardBreak"
                for block in draft.get("content") or []
                for node in block.get("content") or []
            )

        draft = _save_and_wait(page, page_id, pasted)
        assert pasted(draft), f"the save did not store the pasted text: {draft}"
        line = next(b for b in draft["content"] if pasted({"content": [b]}))["content"]
        assert [
            (n["type"], n.get("text"), [m["type"] for m in n.get("marks", [])]) for n in line
        ] == [
            ("text", "Een", ["bold"]),
            ("hardBreak", None, []),
            ("text", "twee", ["bold"]),
        ], line
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


def test_a_copied_button_comes_back_with_its_label_and_destination(setup):
    browser, session = setup
    target_id, _ = _new_page("Doelpagina 2028", {"type": "doc", "content": [_paragraph("Doel.")]})
    buttons = [
        {"label": "Buiten", "variant": "primary", "href": "https://voorbeeld.test/buiten"},
        {"label": "Pagina", "variant": "secondary", "page_id": target_id},
        {"label": "Word lid", "variant": "secondary", "screen": "lid-worden"},
    ]
    content = [_paragraph("Boven.")] + [{"type": "button", "attrs": b} for b in buttons]
    page_id, _slug = _new_page("Knoppen kopiëren 2028", {"type": "doc", "content": content})
    page = _open(browser, session, page_id, 1440)
    try:
        page.evaluate(_SETTLE)
        page.evaluate(
            """() => { window.__copied = null; document.addEventListener('copy', e => {
                 window.__copied = e.clipboardData.getData('text/html'); }); }"""
        )
        page.locator(f"{EDITOR} .tiptap > p").first.click()
        page.keyboard.press("Control+a", delay=HELD)
        page.keyboard.press("Control+c", delay=HELD)
        page.wait_for_function("() => window.__copied !== null")
        copied = page.evaluate("() => window.__copied")
        page.keyboard.press("Delete", delay=HELD)
        page.evaluate("() => window.__settle()")
        assert not [n for n in _in_editor(page)["content"] if n["type"] == "button"], "emptied"

        page.evaluate(PASTE, copied)
        page.evaluate(PASTE, '<a data-button href="https://voorbeeld.test/geplakt">Geplakt</a>')
        page.evaluate("() => window.__settle()")

        keys = ("label", "variant", "href", "page_id", "screen")
        came_back = [
            {k: v for k, v in n["attrs"].items() if k in keys and v is not None}
            for n in _in_editor(page)["content"]
            if n["type"] == "button"
        ]
        assert came_back == [
            *buttons,
            {"label": "Geplakt", "variant": "secondary", "href": "https://voorbeeld.test/geplakt"},
        ], f"copied {copied!r} came back as {came_back}"

        draft = _save_and_wait(
            page,
            page_id,
            lambda d: sum(1 for n in d.get("content") or [] if n.get("type") == "button") == 4,
        )
        assert sum(1 for n in draft["content"] if n["type"] == "button") == 4, draft
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()
