"""E2E: the headings of a public CMS page, and the page editor's three buttons (#1656; CR-11 Q87).

In a browser, because both are what the eye gets: the size a heading is drawn
at (the cascade decides, not a template), and the buttons of the editor's bar.

Measured on master, the reason for this issue: a heading in the text was drawn
at 40 px (32 on a phone) — the page-title rule `body[data-shell="site"] #main
h1` (an id) won from `.prose-raak h1` (1.5rem, a class) — and the page had
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
from playwright.sync_api import sync_playwright

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


_BAR = """() => { const editor = document.querySelector('#cp-document');
  const bar = editor.querySelector('.de-bar');
  const knoppen = [...bar.querySelectorAll('.de-btn')].filter(b => b.closest('details') === null);
  const headings = knoppen.filter(b => /^(Kop|Subkop|Kleine kop)$/.test(b.innerText.trim()));
  return {labels: headings.map(b => b.innerText.trim()),
          levels: headings.map(b => b.innerText.trim() === 'Kop' ? 1 : b.innerText.trim() === 'Subkop' ? 2 : 3),
          own_heading_button: [...bar.querySelectorAll('.de-btn')].filter(b => b.innerText.trim() === 'Titel').length,
          other_buttons: [...bar.querySelectorAll('.de-btn')].length,
          old_labels: [...bar.querySelectorAll('.de-btn')].filter(b => /^(H[123]|Titel)$/.test(b.innerText.trim())).length}; }"""


def test_the_page_editor_offers_kop_subkop_and_kleine_kop_and_saves_what_was_stored(setup):
    b, page_id, _slug, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        page.wait_for_selector("#cp-document .tiptap")
        m = page.evaluate(_BAR)
        print("MEASURE editor bar", m)
        assert m["labels"] == ["Kop", "Subkop", "Kleine kop"] and m["levels"] == [1, 2, 3]
        assert m["old_labels"] == 0, 'a button still reads "H2" or "Titel"'
        assert m["own_heading_button"] == 0, "the level Kop is offered twice"
        assert m["other_buttons"] >= 5, "the rest of the editor's toolbar is gone"

        # Each button makes its own level in the document the server
        # receives: click at the document's end, type a word per level, and
        # read what the editor wrote to her hidden input.
        page.locator("#cp-document .tiptap").click()
        page.keyboard.press("Control+End")
        for label in ("Kop", "Subkop", "Kleine kop"):
            page.locator("#cp-document .de-bar .de-btn", has_text=label).first.click()
            page.keyboard.type(f"{label} van de test")
            page.keyboard.press("Enter")
        document = page.locator("#cp-document-input").input_value()
        compact = document.replace(" ", "")
        print("MEASURE document after the three headings", document[:200])
        # The page's own headings may satisfy a bare level check — the proof
        # is the TYPED words, each under her own level.
        for level, label in ((1, "Kop"), (2, "Subkop"), (3, "Kleine kop")):
            assert f"{label} van de test" in document, f"the typed {label} was not written"
            assert f'"level":{level}' in compact, f"level {level} was not written"

        # The typed levels must survive the SAVE and the reopen: save the
        # document, reload, and the draft the editor opens holds the page's
        # own headings plus the three typed ones — and no level the schema
        # refuses.
        page.locator("[data-action-bar] button[data-form-save]").first.click()
        pagina_klaar(page)
        page.reload()
        pagina_klaar(page)
        page.wait_for_selector("#cp-document .tiptap")
        document_na = page.locator("#cp-document-input").input_value()
        compact = document_na.replace(" ", "")
        # The page's own levels may satisfy a bare level check — the proof
        # is the TYPED words, each under her own level.
        for level, label in ((1, "Kop"), (2, "Subkop"), (3, "Kleine kop")):
            assert f"{label} van de test" in document_na, (
                f"the typed {label} did not survive the save and the reopen"
            )
            assert f'"level":{level}' in compact, f"level {level} left the document"
        assert '"level":4' not in compact, "the shift was written into the stored document"
        assert page.errors == [], f"the editor throws: {page.errors}"
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
