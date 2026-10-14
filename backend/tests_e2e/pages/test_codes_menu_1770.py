"""E2E: a code chosen from the insert menu (CR-17; Koen, 12 October 2026).

The insert menu has one item "Code". It opens the list the card "Codes" beside
the editor shows, without the form codes. A choice puts the code at the cursor
as plain text — what an author types — and the public page shows its value
there.

Walked at 390 px, in a paragraph, in a table cell and in a callout: the three
places a code is typed today.

Broken on purpose (13 October 2026), each put back by the reverse edit: the
`insertContent` of the script's answer taken out → red, the paragraph keeps
its own words only; the filter of `insertable_codes` turned off → red, a form
code stands in the menu's list.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

EDITOR = "#cp-document"
INSERT = f"{EDITOR} details.de-menu-insert"
DIALOG = "div[x-show='codes'][role='dialog']"
CODE = "{{membership_price_full}}"


def _paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


@pytest.fixture(scope="module")
def setup():
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.cms.api import create_page, publish, save_document
    from app.schemas.cms import CmsPageCreate
    from tests.conftest import SEEDED_ADMIN_EMAIL

    document = {
        "type": "doc",
        "content": [
            _paragraph("Het lidgeld is "),
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "attrs": {"section": "body"},
                        "content": [
                            {"type": "tableCell", "content": [_paragraph("In een cel: ")]},
                            {"type": "tableCell", "content": [_paragraph("Ernaast.")]},
                        ],
                    }
                ],
            },
            {"type": "callout", "content": [{"type": "text", "text": "In een kader: "}]},
        ],
    }
    db = SessionLocal()
    page = create_page(
        db,
        CmsPageCreate(
            title="Codes kiezen", slug=f"codes-{secrets.token_hex(3)}", show_in_nav=False
        ),
    )
    save_document(db, page.id, document)
    publish(db, page.id)
    page_id, slug = page.id, page.slug
    db.close()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, page_id, slug, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _choose_code_at_the_end_of(page, block) -> None:
    block.click()
    expect(page.locator(f"{EDITOR} .tiptap")).to_be_focused()
    page.keyboard.press("End", delay=80)  # held as a person holds a key
    page.locator(f"{INSERT} summary").click()
    page.locator(f"{INSERT} [data-insert-code]").click()
    expect(page.locator(DIALOG)).to_be_visible()
    page.locator(f"{DIALOG} [data-code='{CODE}']").click()
    expect(page.locator(DIALOG)).to_be_hidden()


def test_a_code_from_the_menu_stands_as_text_and_renders_as_its_value(setup):
    from app.domains.cms.render import _values

    browser, page_id, slug, session = setup
    page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")

        # One item "Code", last in the insert menu.
        page.locator(f"{INSERT} summary").click()
        items = [t.strip() for t in page.locator(f"{INSERT} button").all_inner_texts()]
        assert items.count("Code") == 1 and items[-1] == "Code", items
        page.locator(f"{INSERT} [data-insert-code]").click()
        expect(page.locator(DIALOG)).to_be_visible()

        # The list is the card's, without the form codes.
        offered = [
            e.get_attribute("data-code") for e in page.locator(f"{DIALOG} [data-code]").all()
        ]
        card = [t.strip() for t in page.locator("[data-placeholders] dt").all_inner_texts()]
        assert offered and offered == [c for c in card if not c.startswith("{{form:")], (
            offered,
            card,
        )
        assert [c for c in card if c.startswith("{{form:")], "the card lost its form codes"
        assert "{{tenants:raak}}" in offered
        # Every choice can be pressed on a phone: inside the window, 44 px high.
        for box in (e.bounding_box() for e in page.locator(f"{DIALOG} [data-code]").all()):
            assert box["x"] >= 0 and box["x"] + box["width"] <= 390 and box["height"] >= 44, box
        page.locator(f"{DIALOG} button", has_text="Annuleren").click()
        expect(page.locator(DIALOG)).to_be_hidden()

        tiptap = f"{EDITOR} .tiptap"
        _choose_code_at_the_end_of(page, page.locator(f"{tiptap} > p").first)
        assert page.locator(f"{tiptap} > p").first.inner_text() == f"Het lidgeld is {CODE}"
        _choose_code_at_the_end_of(page, page.locator(f"{tiptap} td").first)
        assert page.locator(f"{tiptap} td").first.inner_text().strip() == f"In een cel: {CODE}"
        _choose_code_at_the_end_of(page, page.locator(f"{tiptap} .prose-callout"))
        assert page.locator(f"{tiptap} .prose-callout").inner_text() == f"In een kader: {CODE}"

        # What the form holds is text, no node of its own.
        stored = page.locator("#cp-document-input").input_value()
        assert stored.count(CODE) == 3 and '"value"' not in stored

        with page.expect_navigation(timeout=15000):
            page.locator("[data-action-bar] button[data-form-save]").click()
        pagina_klaar(page)
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()

    # Published, the public page shows the value in all three places.
    from app.database import SessionLocal
    from app.domains.cms.api import publish

    db = SessionLocal()
    try:
        publish(db, page_id)
    finally:
        db.close()
    value = _values()["membership_price_full"]
    public = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    try:
        public.goto(f"/{slug}")
        pagina_klaar(public)
        prose = public.locator(".prose-raak").first
        assert prose.locator("p").first.inner_text() == f"Het lidgeld is {value}"
        assert prose.locator("td").first.inner_text().strip() == f"In een cel: {value}"
        assert prose.locator(".prose-callout").inner_text() == f"In een kader: {value}"
        assert "{{" not in prose.inner_text()
    finally:
        public.close()
