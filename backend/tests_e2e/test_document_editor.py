"""E2E: the document editor on the kit page (CR-17 #1671, slice 2; C6 3).

In a browser, because the editor is what the eye gets: the toolbar her
configuration builds, the blocks she inserts, and the document she keeps in
step with her hidden input. The kit page (`/admin/design-system`) is the one
screen that carries her in this slice — the page screen follows in slice 3.

Measured, not asserted from templates: the buttons' labels and aria-labels,
the demo's blocks, the inserted table, the typed word in the editor AND in
the input's JSON, and the page's width at 390 px (AC6's first half —
saving arrives with the page screen).
"""

import json
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

EDITOR = "#ds-document"
TOOLBAR = f"{EDITOR} .document-editor > div:first-child"


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


_TOOLBAR = """() => { const editor = document.querySelector('#ds-document');
  const bar = editor.querySelector('.document-editor > div');
  return {labels: [...bar.querySelectorAll('button')].filter(b => b.closest('details') === null)
             .map(b => ({text: b.innerText.trim(), aria: b.getAttribute('aria-label')})),
          menu: bar.querySelector('summary') ? bar.querySelector('summary').innerText.trim() : null,
          items: bar.querySelectorAll('details button').length,
          pressed: [...bar.querySelectorAll('button')].map(b => b.getAttribute('aria-pressed') || '')}; }"""

_EDITOR = """() => { const editor = document.querySelector('#ds-document');
  const tip = editor.querySelector('.tiptap');
  const input = document.getElementById(editor.dataset.input);
  return {headings: [...tip.querySelectorAll('h1,h2,h3')].map(h => h.tagName),
          lists: tip.querySelectorAll('ul,ol').length,
          tables: tip.querySelectorAll('table').length,
          figures: tip.querySelectorAll('figure[data-document-figure]').length,
          text: tip.innerText.trim(),
          json: input ? input.value : null,
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize("width", [1440, 390])
def test_the_editor_opens_with_the_page_sets_toolbar(setup, width):
    """The toolbar her configuration builds: the three headings by name, the
    three marks by letter with their aria-labels, the link by her word, the
    two lists, and the insert menu with her two blocks. Nothing scrolls
    sideways — the page stays exactly as wide as the screen (AC6)."""
    b, session = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto("/admin/design-system")
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")
        m = page.evaluate(_TOOLBAR)
        print("MEASURE document editor toolbar", width, m)
        assert m["labels"] == [
            {"text": "Kop", "aria": None},
            {"text": "Subkop", "aria": None},
            {"text": "Kleine kop", "aria": None},
            {"text": "B", "aria": "Vet"},
            {"text": "I", "aria": "Cursief"},
            {"text": "S", "aria": "Doorgehaald"},
            {"text": "Link", "aria": None},
            {"text": "•", "aria": "Lijst"},
            {"text": "1.", "aria": "Genummerde lijst"},
        ], m["labels"]
        assert m["menu"] == "Blok invoegen ▾"
        assert m["items"] == 2, "the insert menu offers Tabel and Afbeelding"
        e = page.evaluate(_EDITOR)
        print("MEASURE document editor blocks", width, e)
        assert e["headings"] == ["H1"], "the demo's Kop stands as a heading"
        assert e["lists"] == 1 and e["tables"] == 1 and e["figures"] == 1
        assert "Een pagina als document" in e["text"]
        assert e["page"] == [width, width], "the page scrolls sideways"
        assert page.errors == [], f"the editor throws: {page.errors}"
    finally:
        page.close()


def test_inserting_a_block_and_typing_keeps_the_input_in_step(setup):
    """AC1's editor half: the insert menu adds a table with her header row,
    a typed word stands in the editor AND in the hidden input's JSON — the
    document is what the server will receive (slice 3 wires the save)."""
    b, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto("/admin/design-system")
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")
        before = page.evaluate(_EDITOR)["tables"]

        page.locator(f"{EDITOR} summary").click()
        page.locator(f"{EDITOR} details button", has_text="Tabel").click()
        page.wait_for_function(
            f"document.querySelectorAll('{EDITOR} .tiptap table').length === {before + 1}"
        )
        # The caret at the last paragraph — the demo's own text — so the typed
        # word lands in the document, not in the middle of the inserted table.
        page.locator(f"{EDITOR} .tiptap p").last.click()
        page.keyboard.type(" Meettekst")

        e = page.evaluate(_EDITOR)
        print("MEASURE document editor after insert and typing", e)
        assert e["tables"] == before + 1
        assert "Meettekst" in e["json"], "the typed word is not in the input's JSON"
        assert "Meettekst" in e["text"]
        assert page.errors == [], f"the editor throws: {page.errors}"
    finally:
        page.close()


def test_everything_the_editor_writes_validates(setup):
    """B1 of the review (#1699): every node and mark the CONFIGURED editor
    can produce is one `validate_document` accepts — measured by really
    writing them in the browser and feeding the emitted JSON to the
    server's own gate.

    The table is excluded until slice 3's save adapter maps her attributes
    (colspan, align — named in the PR); the quote, code, code block, rule
    and underline are switched OFF, so their shortcuts write plain text
    instead of a block the server refuses."""
    b, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("dialog", lambda d: d.accept("https://voorbeeld.test"))
    try:
        login_met_sessie(page, session)
        page.goto("/admin/design-system")
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")

        # The caret at the document's end, so what is typed lands after the
        # demo's blocks — and every node STAYS in the document (a toggle
        # that is switched off again would leave the emission and prove
        # nothing about what the editor can write).
        page.locator(f"{EDITOR} .tiptap").click()
        page.keyboard.press("Control+End")
        page.locator(f"{EDITOR} .de-btn", has_text="Kop").first.click()
        page.keyboard.type("Kopregel")
        page.keyboard.press("Enter")
        page.keyboard.type("Een ")
        for aria, word in (("Vet", "vet"), ("Cursief", "cursief"), ("Doorgehaald", "doorgehaald")):
            page.locator(f"{EDITOR} button[aria-label='{aria}']").click()
            page.keyboard.type(word)
            page.locator(f"{EDITOR} button[aria-label='{aria}']").click()
        page.keyboard.type(" en ")
        page.locator(f"{EDITOR} .de-btn", has_text="Link").first.click()
        page.keyboard.type("een link")
        page.keyboard.press("Shift+Enter")
        page.keyboard.type("na de harde return")
        page.keyboard.press("Enter")
        for aria, word in (("Lijst", "punt"), ("Genummerde lijst", "eerst")):
            page.locator(f"{EDITOR} button[aria-label='{aria}']").click()
            page.keyboard.type(word)
            page.keyboard.press("Enter")
            page.keyboard.type(word)
            # An empty item leaves the list, so she stays behind whole.
            page.keyboard.press("Enter")
        # The switched-off five: their shortcut writes plain text now.
        page.keyboard.type("> blokcitaat")

        emitted = page.evaluate(
            "() => document.getElementById("
            "document.querySelector('[data-document-editor]').dataset.input).value"
        )
        print("MEASURE document editor emitted", emitted[:400])
        from app.domains.cms.schema import UnknownAttribute, validate_document

        document = json.loads(emitted)
        assert "blockquote" not in emitted, "a quote block was written after all"

        # The one declared gap: the demo's table, round-tripped through
        # TipTap, carries her own cell attributes (colspan, align — the
        # slice-3 adapter, named in the PR). Everything ELSE the editor
        # wrote must validate: the refusal, if any, names exactly a table
        # attribute, and the same document without her tables passes.
        refusal = None
        try:
            validate_document(document)
        except UnknownAttribute as error:
            refusal = str(error)
        assert refusal is None or "table" in refusal, f"an unexpected refusal: {refusal}"

        stripped = json.loads(emitted)
        stripped["content"] = [b for b in stripped["content"] if b.get("type") != "table"]
        validate_document(stripped)
        assert page.errors == [], f"the editor throws: {page.errors}"
    finally:
        page.close()
