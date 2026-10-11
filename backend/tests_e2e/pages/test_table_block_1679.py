"""E2E: the table block full out (CR-17 phase 2, #1679, slice 1; C4.13).

In a browser, because both halves of this commit are what the eye gets:

* the EDITOR half — the Tabel menu that appears on a table: the header row
  the organiser's own choice, rows and columns added and removed. The test
  presses the real buttons and reads the document back after the real
  save (the rule of this phase: a browser test per thing that persists);
* the LOOK half — C4.13's measures as computed styles on the public page:
  the header row on `surface-2` semibold, one 1 px line between rows, no
  vertical lines, cells 12/16 px, text 14 px; on a phone the table's block
  scrolls inside itself while the page does not (C6 11).

Decided with the look and taken in (Koen, 11 October 2026): NO line under a
wide table — no script on the public site — and NO right-aligned numbers.
The rendered table's HTML does not change in this commit, so the round-trip
tests that pin her bare `<table>` stay as they are.

Proven red while building, both additive and restored afterwards (the gate
convention): giving `.prose-raak :is(th,td)` a left border back made the
look test fail on `border-left` ("the full grid came back"); removing
`addRowAfter` from `TABLE_MENU` made the editor test time out on her
button ("the menu no longer offers what the author must reach").
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

EDITOR = "#cp-document"

_TABLE_CONTENT = """
<table><thead><tr><th>Onderdeel</th><th>Wat het kost</th><th>Wanneer</th>
<th>Waar</th><th>Inschrijven</th></tr></thead>
<tbody>
<tr><td>Wandeling</td><td>€ 3,00</td><td>zondagochtend</td>
<td>ontmoetingsplaats aan de kerk</td><td>aan de balie</td></tr>
<tr><td>Soep na afloop</td><td>€ 5,00</td><td>rond de middag</td>
<td>in de zaal</td><td>met de wandeling</td></tr>
</tbody></table>
"""

#: Words under the table, so the page is a real one: a page this short puts
#: the record bar in her natural place — right under the toolbar's dropdown —
#: and no scroll of a real window clears her. With the words the form runs
#: past the window, the bar sticks to the bottom and the menu opens free.
_ONDER_DE_TABEL = "\n".join(
    f"<p>Regel {n} onder de tabel — woorden die een echte pagina ook heeft, "
    f"zodat het scherm lang genoeg is om te scrollen.</p>"
    for n in range(1, 9)
)

#: The table menu appears the moment the cursor stands in a table.
_MENU = f"{EDITOR} details.de-menu-table"
_ROWS = "() => document.querySelectorAll('#cp-document .tiptap tr').length"
_COLS = "() => document.querySelectorAll('#cp-document .tiptap tr:first-child > *').length"
_HEADS = "() => document.querySelectorAll('#cp-document .tiptap th').length"


@pytest.fixture(scope="module")
def setup():
    """One page with a table in her words, one browser for the module.

    The page is seeded through the model with her content (the same way the
    screen test of #1671 seeds hers): the public route serves her words, so
    the look is measured on the real page a visitor opens.
    """
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.cms.api import CmsPage
    from tests.conftest import SEEDED_ADMIN_EMAIL

    tag = secrets.token_hex(3)
    db = SessionLocal()
    page = CmsPage(
        title="Tabeltest",
        slug=f"tabel-{tag}",
        content=(
            f"<p>Een tabel zoals de vereniging ze vandaag al heeft.</p>"
            f"{_TABLE_CONTENT}{_ONDER_DE_TABEL}"
        ),
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


def _menu_klik(page, label):
    """Open the table menu and press one of her commands, the way an author
    reaches her: the toolbar scrolled to the top of the window first, so
    the eight-item dropdown opens in the upper half — clear of the record
    bar, which sticks to the window's bottom while the form runs past her
    (on a page long enough to scroll, which the seed gives)."""
    page.evaluate(
        """() => { document.querySelector('.de-menu-table summary')
              .scrollIntoView({block:'start'});
              window.scrollBy(0, 100); }"""
    )
    page.locator(f"{_MENU} summary").click()
    page.locator(f"{_MENU} button", has_text=label).click()


def test_the_table_menu_edits_the_table_through_the_screen(setup):
    """C4.13's editor half, pressed: the menu appears on a table, adds a
    row and a column, turns the header row off and on, removes a column —
    and the saved document carries what the buttons did (the real save)."""
    b, page_id, _slug, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
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

        _menu_klik(page, "Rij onder toevoegen")
        page.wait_for_function(f"{_ROWS} === {rows + 1}")
        _menu_klik(page, "Kolom rechts toevoegen")
        page.wait_for_function(f"{_COLS} === {cols + 1}")
        # The header row grows with her column: re-read before toggling.
        heads = page.evaluate(_HEADS)
        assert heads == cols + 1, "the new column brought no header cell"

        # The header row is the organiser's own choice: off, then on again.
        _menu_klik(page, "Koprij aan of uit")
        page.wait_for_function(f"{_HEADS} === 0")
        _menu_klik(page, "Koprij aan of uit")
        page.wait_for_function(f"{_HEADS} === {heads}")
        _menu_klik(page, "Kolom verwijderen")
        page.wait_for_function(f"{_COLS} === {cols}")

        # Opslaan through the record form's bar — the one save of the screen.
        page.locator("[data-action-bar] button[data-form-save]").click()
        page.wait_for_url(f"**/admin/paginas/{page_id}*opgeslagen=1*", timeout=15000)
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")

        # The saved document carries the edits: one row more than the seed.
        page.click(f"{EDITOR} .tiptap td")
        page.wait_for_selector(_MENU, state="visible")
        assert page.evaluate(_ROWS) == rows + 1, "the added row did not survive the save"
        assert page.evaluate(_COLS) == cols, "the column count moved without a command"
        assert "Concept gewijzigd" in page.locator("[data-record-head]").inner_text()
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_the_table_look_is_beslissing_14(setup, width):
    """C4.13's look half, measured on the public page a visitor opens: the
    header row on `surface-2` semibold, one 1 px line between rows and no
    vertical lines, cells 12/16 px, text 14 px — and on a phone the table's
    block scrolls inside itself while the page does not (C6 11)."""
    b, _page_id, slug, _session = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        page.goto(f"/{slug}")
        pagina_klaar(page)
        look = page.evaluate(
            """() => {
              const table = document.querySelector('.doc-page .prose-raak table');
              const th = table.querySelector('th');
              const td = table.querySelector('tbody td');
              const cs = el => getComputedStyle(el);
              /* surface-2 is the shell's own token (the site and the back
                 office carry different values): the header must carry the
                 TOKEN, not a hard-coded colour. Computed style and custom
                 property write the same colour differently ("rgb(240, 243,
                 246)" against "rgb(240 243 246)"): both stripped of commas
                 and spaces before they are compared. */
              const norm = s => s.replace(/[\\s,]/g, '');
              const token = norm(cs(document.body).getPropertyValue('--surface-2'));
              return {
                header: [norm(cs(th).backgroundColor), cs(th).fontWeight, token],
                cell: [cs(td).borderBottomWidth, cs(td).borderLeftWidth,
                       cs(td).borderRightWidth, cs(td).paddingTop, cs(td).paddingLeft],
                text: [cs(table).fontSize],
                scroll: [table.scrollWidth > table.clientWidth,
                         document.documentElement.scrollWidth, innerWidth],
              };
            }"""
        )
        print("MEASURE table look", width, look)
        assert look["header"][0] == look["header"][2], (
            f"the header row is not surface-2: {look['header']}"
        )
        assert look["header"][1] == "600", f"the header row is not semibold: {look['header']}"
        assert look["cell"] == ["1px", "0px", "0px", "12px", "16px"], (
            f"the cell is not beslissing 14 (one line between rows, 12/16 px): {look['cell']}"
        )
        assert look["text"] == ["14px"], f"the table's text is not 14 px: {look['text']}"
        if width == 390:
            assert look["scroll"][0], "the wide table's block does not scroll herself"
        assert look["scroll"][1] == look["scroll"][2] == width, "the page scrolls sideways"
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()
