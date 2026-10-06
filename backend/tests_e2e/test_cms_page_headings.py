"""E2E: the headings of a public CMS page, and the page editor's three buttons (#1656; CR-11 Q87).

In a browser, because both are what the eye gets: the size a heading is drawn
at (the cascade decides, not a template), and the buttons of the editor's bar.

Measured on master, the reason for this issue: a heading in the text was drawn
at 40 px (32 on a phone) — the page-title rule `body[data-shell="site"] #main
h1` (an id) won from `.cms-content h1` (1.5rem, a class) — and the page had
three h1's.

Broken on purpose (6 October 2026): the `.cms-page` rules taken out of the
stylesheet → 24 / 18 / 16 for h2 / h3 by the shell but h4 unsized and the
margins gone; `cms-page` taken off the page body → the same; `on_page` not
passed → the body's h1 back at 40 px and three h1's; the removal of the
editor's own heading button dropped → four heading buttons; a label put back
to "H2" → the labels differ.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

TEXT = "<div>Elke maand komt het bestuur samen. Iedereen die wil meedenken is welkom.</div>"
BODY = (
    f"<h1>Vergadering</h1>{TEXT}<h1>Activiteiten</h1>{TEXT}"
    f"<h2>Samen meer beleven</h2>{TEXT}<h3>Praktisch</h3>{TEXT}"
)


def _db():
    import app.main  # noqa: F401
    from app.database import SessionLocal

    return SessionLocal()


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from app.domains.cms.api import CmsPage
    from tests.conftest import SEEDED_ADMIN_EMAIL

    tag = secrets.token_hex(3)
    db = _db()
    page = CmsPage(title="Werking", slug=f"werking-{tag}", content=BODY, is_published=True)
    db.add(page)
    db.commit()
    page_id, slug = page.id, page.slug
    db.close()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, page_id, slug, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()
    db = _db()
    try:
        db.query(CmsPage).filter(CmsPage.id == page_id).delete()
        db.commit()
    finally:
        db.close()


def _stored(page_id: int) -> str:
    from app.domains.cms.api import CmsPage

    db = _db()
    try:
        return db.get(CmsPage, page_id).content
    finally:
        db.close()


_HEADS = """() => { const main = document.querySelector('#main');
  return {h1: main.querySelectorAll('h1').length,
          heads: [...main.querySelectorAll('h1,h2,h3,h4')].map(h => { const s = getComputedStyle(h);
            return {tag: h.tagName, text: h.innerText.trim(), px: parseFloat(s.fontSize), weight: s.fontWeight,
                    top: s.marginTop, bottom: s.marginBottom, colour: s.color}; }),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize(("width", "title"), [(1440, 40), (390, 32)])
def test_the_title_is_the_only_h1_and_the_three_levels_are_24_18_and_16_px(setup, width, title):
    """Red on master: "Vergadering" and "Activiteiten" h1's of 40 px (32 on a
    phone), three h1's on the page."""
    b, _id, slug, _session = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    try:
        page.goto(f"/{slug}")
        pagina_klaar(page)
        m = page.evaluate(_HEADS)
        print("MEASURE cms headings", width, m)
        assert m["h1"] == 1, "the page's title is not its only h1"
        shown = [(h["tag"], h["text"], h["px"], h["weight"]) for h in m["heads"]]
        assert shown == [
            ("H1", "Werking", title, "600"),
            ("H2", "Vergadering", 24, "600"),
            ("H2", "Activiteiten", 24, "600"),
            ("H3", "Samen meer beleven", 18, "600"),
            ("H4", "Praktisch", 16, "600"),
        ]
        body = m["heads"][1:]
        assert body[0]["top"] == "0px", "the first heading of the body adds air under the title"
        assert [(h["top"], h["bottom"]) for h in body[1:]] == [("24px", "8px")] * 3
        assert len({h["colour"] for h in body}) == 1, "one heading colour for the three levels"
        assert m["page"] == [width, width]
        # The title role (40 px, 32 on a phone) never reaches into a page body: an
        # h1 that stands there all the same — the renderer shifted it away, so it
        # is put there by hand — is a section head. Without the body's own size
        # rules the shell's page-title rule takes it.
        stray = page.evaluate(
            """() => { const h = document.createElement('h1'); h.textContent = 'Los';
                 document.querySelector('.cms-page').appendChild(h);
                 return parseFloat(getComputedStyle(h).fontSize); }"""
        )
        assert stray == 24, f"the page-title size reached into the page body: {stray}"
    finally:
        page.close()


_BAR = """() => { const bar = document.querySelector('[data-cp-balk]'), tool = document.querySelector('#cp-detail trix-toolbar');
  return {labels: [...bar.querySelectorAll('[data-cp-heading]')].map(b => b.innerText.trim()),
          levels: [...bar.querySelectorAll('[data-cp-heading]')].map(b => b.dataset.cpHeading),
          own_heading_button: tool.querySelectorAll('[data-trix-attribute="heading1"]').length,
          other_buttons: tool.querySelectorAll('[data-trix-attribute]').length,
          old_labels: [...bar.querySelectorAll('button')].filter(b => /^(H[123]|Titel)$/.test(b.innerText.trim())).length}; }"""


def test_the_page_editor_offers_kop_subkop_and_kleine_kop_and_saves_what_was_stored(setup):
    b, page_id, _slug, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        page.wait_for_selector("#cp-detail trix-toolbar")
        page.wait_for_function("document.getElementById('cp-trix').editor")
        m = page.evaluate(_BAR)
        print("MEASURE editor bar", m)
        assert m["labels"] == ["Kop", "Subkop", "Kleine kop"] and m["levels"] == ["1", "2", "3"]
        assert m["old_labels"] == 0, 'a button still reads "H2" or "Titel"'
        assert m["own_heading_button"] == 0, "the level Kop is offered twice"
        assert m["other_buttons"] >= 5, "the rest of the editor's toolbar is gone"

        # each button makes its own level in what is stored
        made = page.evaluate(
            """() => { const e = document.getElementById('cp-trix').editor, out = {};
                 for (const n of ['1', '2', '3']) { e.loadHTML('<div>Een regel</div>'); e.setSelectedRange([0, 3]);
                   document.querySelector(`[data-cp-heading="${n}"]`).click();
                   out[n] = document.getElementById('cp-content-input').value; }
                 return out; }"""
        )
        assert made["1"].startswith("<h1>") and made["2"].startswith("<h2>")
        assert made["3"].startswith("<h3>"), made

        # an existing page opens and saves without losing its levels
        page.reload()
        pagina_klaar(page)
        page.wait_for_function("document.getElementById('cp-trix').editor")
        page.locator("#cp-detail [data-form-save], #cp-detail button[type=submit]").first.click()
        expect(page.locator("#toasts")).to_contain_text("Opgeslagen")
        stored = _stored(page_id)
        assert (stored.count("<h1"), stored.count("<h2"), stored.count("<h3")) == (2, 1, 1), stored
        assert "<h4" not in stored, "the shift was written into the stored text"
        assert page.errors == []
    finally:
        page.close()


def test_another_editor_keeps_its_own_heading_button(setup):
    """Only the page editor: the kit's rich text field (the newsletter's and the
    meeting notes' editor) still has the editor's own heading button."""
    b, _id, _slug, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    try:
        login_met_sessie(page, session)
        page.goto("/admin/design-system")
        pagina_klaar(page)
        page.wait_for_selector("trix-toolbar", state="attached")
        assert page.locator('trix-toolbar [data-trix-attribute="heading1"]').count() >= 1
    finally:
        page.close()
