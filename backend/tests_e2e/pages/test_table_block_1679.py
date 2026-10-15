"""E2E: the table block full out (CR-17 phase 2, #1679, slice 1; C4.13).

In a browser, because all halves of this commit are what the eye gets:

* the EDITOR half — the Tabel menu that appears on a table: the header row
  the organiser's own choice, rows and columns added and removed. The test
  presses the real buttons on a SHORT page — one line of words, one small
  table — without any scroll helper: on that page the menu opens where
  there is room (the review of `3110b37e`, A2: opening downward put her
  last items under the record bar, pressable by nobody), then saves,
  publishes and reads the PUBLIC page back (the phase's own rule: a
  browser test per thing that persists, reading the result there);
* the LOOK half — C4.13's measures as computed styles on the public page:
  the header row on `surface-2` semibold, one 1 px line between rows, no
  vertical lines, cells 12/16 px, text 14 px; and the container of C4.13
  ("Where the width lives"): 1 024 px, centred, the table filling her and
  her text at 768 on the left line — the row's edge measured against the
  container's, never the table's box (the design review's A1);
* the HOME INTRO half (A3) — a five-column table in the intro's band: the
  intro's holder scrolls her at every width, the band's buttons stay
  inside the window, the page never scrolls sideways.

Decided with the look and taken in (Koen, 11 October 2026): NO line under a
wide table — no script on the public site — and NO right-aligned numbers.
A table stays a table at every width; what holds her scrolls (the design
review's choice, the master CLI's comment of 11 October 2026).

Proven red while building, each additive and restored (the gate
convention, named where each test proves her): the full grid brought back
to `.prose-raak :is(th,td)` made the look tests fail on `border-left`;
`addRowAfter` taken out of `TABLE_MENU` made the menu test time out on her
button; the centring taken out of `.doc-page` made the container pins fall
over on the left edge; the scroll moved back onto the table herself
(`display:block`) left the holder's `scrollWidth` equal to her
`clientWidth`; and with the menu's room-measure (`openInRoom`) disabled,
the short-page test could not press her lowest item.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

EDITOR = "#cp-document"

#: Every header one long word, like the design review measured her: the
#: table's MIN-content decides whether she overflows her holder, and a
#: header that wraps keeps her under the intro's 681 px band. One long
#: word per column holds her above it at every width the test measures.
_TABLE_CONTENT = """
<table><thead><tr><th>Onderdelenoverzicht</th><th>Kostenberekening</th>
<th>Weekplanning</th><th>Locatiebeschrijving</th>
<th>Inschrijvingsprocedure</th></tr></thead>
<tbody>
<tr><td>Wandeling</td><td>€ 3,00</td><td>zondagochtend</td>
<td>ontmoetingsplaats aan de kerk</td><td>aan de balie</td></tr>
<tr><td>Soep na afloop</td><td>€ 5,00</td><td>rond de middag</td>
<td>in de zaal</td><td>met de wandeling</td></tr>
</tbody></table>
"""

#: A SHORT page: one line of words and one small table — the review's A2
#: case. On this page the record bar stands right under the toolbar, and a
#: menu that only opens downward puts her lowest items under her.
_SHORT_CONTENT = "<p>Eén regel woorden.</p><table><thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table>"

#: The table menu appears the moment the cursor stands in a table.
_MENU = f"{EDITOR} details.de-menu-table"
_ROWS = "() => document.querySelectorAll('#cp-document .tiptap tr').length"
_COLS = "() => document.querySelectorAll('#cp-document .tiptap tr:first-child > *').length"
_HEADS = "() => document.querySelectorAll('#cp-document .tiptap th').length"


def _tabel_document() -> dict:
    """A five-column table as a document, through the parser — the same
    door the migration walked, so the intro's block is what the site
    serves from a document, not from stored HTML."""
    from app.domains.cms.parse import parse_html

    return parse_html(
        "<p>De intro van de startpagina met een brede tabel erin.</p>" + _TABLE_CONTENT
    )


@pytest.fixture(scope="module")
def setup():
    """One short page for the menu (A2's case), one wide page for the look
    and the holder's scroll, one browser for the module — and the home
    intro's site block carrying a five-column table in her document, so
    the intro is measured as the visitor meets her (A3)."""
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.cms.api import CmsPage
    from tests.conftest import SEEDED_ADMIN_EMAIL

    tag = secrets.token_hex(3)
    db = SessionLocal()
    short = CmsPage(
        title="Tabeltest",
        slug=f"tabel-{tag}",
        content=_SHORT_CONTENT,
        is_published=True,
    )
    wide = CmsPage(
        title="Brede tabeltest",
        slug=f"breed-{tag}",
        content=f"<p>Een brede tabel zoals de vereniging ze vandaag al heeft.</p>{_TABLE_CONTENT}",
        is_published=True,
    )
    db.add_all([short, wide])
    db.commit()
    page_id, slug, wide_slug = short.id, short.slug, wide.slug
    # The home page of THIS page's tenant (CR-32 R17: the home is a flagged page of
    # the CMS; the intro is the first part of her document): every tenant has her
    # own, and the first row a bare query finds is another tenant's.
    intro = (
        db.query(CmsPage)
        .filter(CmsPage.is_home.is_(True), CmsPage.tenant_id == short.tenant_id)
        .first()
    )
    intro_id = intro.id if intro else None
    db.close()

    if intro_id:
        from app.domains.cms.api import publish, save_document

        s = SessionLocal()
        # The table and the contact button in a band of the home page, as the board
        # makes one: a section holding the blocks.
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "section",
                    "attrs": {"tone": "accent"},
                    "content": _tabel_document()["content"],
                }
            ],
        }
        # The home page is the tenant's real one: the band goes IN FRONT of her
        # document and the document goes back when the test is over, or every later
        # test would find a home without her activities.
        from app.domains.cms.api import published_document as _published_document

        _before = _published_document(s, s.get(CmsPage, intro_id)) or {"type": "doc", "content": []}
        doc["content"] = doc["content"] + _before["content"]
        save_document(s, intro_id, doc)
        publish(s, intro_id)
        s.close()

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, page_id, slug, wide_slug, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()
    if intro_id:
        s = SessionLocal()
        save_document(s, intro_id, _before)
        publish(s, intro_id)
        s.close()


def _menu_klik(page, label):
    """Press one command of the table menu — no scroll helper: on this
    short page the menu must open where there is room herself (`openInRoom`
    in the editor), or her lowest items sit under the record bar where no
    press reaches them (the review's A2)."""
    page.locator(f"{_MENU} summary").click()
    page.locator(f"{_MENU} button", has_text=label).click()


def test_the_table_menu_edits_the_table_through_the_screen(setup):
    """C4.13's editor half, pressed on the short page at both widths: all
    eight commands — a row above and below, a column left and right, a row
    away, the header row off and on, the table away — then the real save,
    the publish (over a stored-HTML page: the confirmation), and the public
    page read back."""
    b, page_id, slug, _wide_slug, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")
        assert page.locator(_MENU).is_hidden(), "the table menu shows outside a table"

        # The cursor into the table — the menu appears (C4.13: her own menu).
        page.click(f"{EDITOR} .tiptap td")
        page.wait_for_selector(_MENU, state="visible")
        rows = page.evaluate(_ROWS)
        cols = page.evaluate(_COLS)
        assert (rows, cols) == (2, 2), f"the short page's table changed: {rows}, {cols}"

        _menu_klik(page, "Rij boven toevoegen")
        page.wait_for_function(f"{_ROWS} === {rows + 1}")
        _menu_klik(page, "Rij onder toevoegen")
        page.wait_for_function(f"{_ROWS} === {rows + 2}")
        _menu_klik(page, "Kolom links toevoegen")
        page.wait_for_function(f"{_COLS} === {cols + 1}")
        _menu_klik(page, "Kolom rechts toevoegen")
        page.wait_for_function(f"{_COLS} === {cols + 2}")
        heads = page.evaluate(_HEADS)
        assert heads == cols + 2, "the new columns brought no header cells"

        # The header row is the organiser's own choice: off, then on again.
        _menu_klik(page, "Koprij aan of uit")
        page.wait_for_function(f"{_HEADS} === 0")
        _menu_klik(page, "Koprij aan of uit")
        page.wait_for_function(f"{_HEADS} === {heads}")

        # Rij en kolom verwijderen, en de tabel zelf weg.
        _menu_klik(page, "Rij verwijderen")
        page.wait_for_function(f"{_ROWS} === {rows + 1}")
        _menu_klik(page, "Kolom verwijderen")
        page.wait_for_function(f"{_COLS} === {cols + 1}")
        _menu_klik(page, "Tabel verwijderen")
        page.wait_for_function(f"{_ROWS} === 0")
        assert page.locator(_MENU).is_hidden(), "the menu stays after her table went"

        # The table back for the save: what the author built must persist.
        page.locator(f"{EDITOR} details.de-menu-insert summary").click()
        page.locator(f"{EDITOR} details.de-menu-insert button", has_text="Tabel").click()
        page.wait_for_function(f"{_ROWS} === 3")
        page.locator("[data-action-bar] button[data-form-save]").click()
        page.wait_for_url(f"**/admin/paginas/{page_id}*opgeslagen=1*", timeout=15000)
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")
        assert "Concept gewijzigd" in page.locator("[data-record-head]").inner_text()

        # Publish — over a stored-HTML page she asks first (A4's notice).
        page.locator("button", has_text="Publiceren").click()
        page.locator("[data-dialog-ok]").click()
        page.wait_for_function(
            "() => document.querySelector('[data-record-head]') && "
            "!document.querySelector('[data-record-head]').textContent.includes('Concept gewijzigd')",
            timeout=15000,
        )

        # The public page carries what the author did (B3: read it there).
        page.goto(f"/{slug}")
        pagina_klaar(page)
        tabel = page.evaluate(
            "() => { const t = document.querySelector('.doc-page .prose-raak table');"
            "return t ? {rows: t.querySelectorAll('tr').length,"
            "heads: t.querySelectorAll('th').length} : null; }"
        )
        assert tabel == {"rows": 3, "heads": 3}, (
            f"the published table is not the saved one: {tabel}"
        )
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


@pytest.mark.parametrize("width", [1440, 1024, 390])
def test_the_table_look_is_beslissing_14(setup, width):
    """C4.13's look half, measured on the public page a visitor opens: the
    header row on `surface-2` semibold, one 1 px line between rows and no
    vertical lines, cells 12/16 px, text 14 px — and the container: 1 024
    px centred at 1 440, the table filling her with the ROW's edge at the
    container's (never the box: the design review's A1), the page exactly
    as wide as her screen at every width, at 1 024 the width nobody
    measured, and on the phone the holder scrolling."""
    b, _page_id, _slug, wide_slug, _session = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        page.goto(f"/{wide_slug}")
        pagina_klaar(page)
        look = page.evaluate(
            """() => {
              const container = document.querySelector('.doc-page').getBoundingClientRect();
              const table = document.querySelector('.doc-page .prose-raak table');
              const holder = document.querySelector('.doc-page .prose-raak');
              const tr = table.querySelector('tr');
              const row = tr.getBoundingClientRect();
              const th = table.querySelector('th');
              const td = table.querySelector('tbody td');
              const cs = el => getComputedStyle(el);
              const norm = s => s.replace(/[\\s,]/g, '');
              const token = norm(cs(document.body).getPropertyValue('--surface-2'));
              return {
                container: [Math.round(container.x), Math.round(container.width)],
                row: [Math.round(row.x), Math.round(row.width), Math.round(row.right),
                      Math.round(container.right)],
                header: [norm(cs(th).backgroundColor), cs(th).fontWeight, token],
                cell: [cs(td).borderBottomWidth, cs(td).borderLeftWidth,
                       cs(td).borderRightWidth, cs(td).paddingTop, cs(td).paddingLeft],
                text: [cs(table).fontSize],
                holder: [holder.scrollWidth, holder.clientWidth],
                page: [document.documentElement.scrollWidth, innerWidth],
              };
            }"""
        )
        print("MEASURE table look", width, look)
        if width == 1440:
            assert look["container"][1] == 1024, f"the container is not 1 024: {look['container']}"
            assert look["row"][0] == look["container"][0], (
                f"the row does not start on the container's left line: {look['row']}"
            )
            assert look["row"][2] == look["row"][3], (
                f"the row does not run to the container's edge: {look['row']}"
            )
        if width == 1024:
            assert look["row"][2] <= look["row"][3] + 1, (
                f"the row runs past her container: {look['row']}"
            )
        assert look["header"][0] == look["header"][2], (
            f"the header row is not surface-2: {look['header']}"
        )
        assert look["header"][1] == "600", f"the header row is not semibold: {look['header']}"
        assert look["cell"] == ["1px", "0px", "0px", "12px", "16px"], (
            f"the cell is not beslissing 14 (one line between rows, 12/16 px): {look['cell']}"
        )
        assert look["text"] == ["14px"], f"the table's text is not 14 px: {look['text']}"
        if width == 390:
            assert look["holder"][0] > look["holder"][1], "the wide table's holder does not scroll"
        assert look["page"] == [width, width], f"the page scrolls sideways: {look['page']}"
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_a_wide_table_in_the_home_band_stays_in_her_band(setup, width):
    """A3 of the review, since CR-32 R17 on the home page's band (a section): a
    five-column table in it scrolls by itself at every width (a page with a section
    is no scroll holder, so each table is her own), the band's buttons stay
    inside the window, and the page never scrolls sideways."""
    b, *_rest, _session = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        page.goto("/")
        pagina_klaar(page)
        intro = page.evaluate(
            """() => { const h = document.querySelector('.prose-section table');
              const knop = [...document.querySelectorAll('button, a')].find(el => /contact/i.test(el.textContent));
              const b = knop ? knop.getBoundingClientRect() : null;
              return {holder: [h.scrollWidth, h.clientWidth],
                      overflow: getComputedStyle(h).overflowX,
                      tabellen: document.querySelectorAll('.prose-section table').length,
                      knop: b ? [Math.round(b.x), Math.round(b.right)] : null,
                      page: [document.documentElement.scrollWidth, innerWidth]}; }"""
        )
        print("MEASURE home intro", width, intro)
        assert intro["tabellen"] == 1, f"the intro carries no table: {intro}"
        assert intro["overflow"] == "auto", f"the band's table is no holder of her own: {intro}"
        assert intro["holder"][0] >= intro["holder"][1], (
            f"the table is narrower than herself: {intro}"
        )
        assert intro["knop"] is not None and intro["knop"][1] <= intro["page"][1], (
            f"the band's contact button runs off the window: {intro}"
        )
        assert intro["page"] == [width, width], f"the home scrolls sideways: {intro}"
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()
