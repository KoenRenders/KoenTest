"""E2E: the list Activiteiten on the kit's table (#1930).

What only a browser shows: the heads on one line, where the last column ends,
the stacked rows on a phone, and what a click does.

- At 1 440 and 1 920 px the table has five columns (Activiteit, Datum, Locatie,
  Inschrijvingen, Status); every head stands on one line (36 px); the last
  column's cell reaches the frame's right edge, so the white space falls behind
  Status and never between the first two columns (the kit's rule since #1927).
- A click on a row's name opens the activity; its way back returns to the list
  with the state it had (`?sort=…` here).
- A click on the head Datum turns the sort and the URL carries it.
- At 390 px the rows are stacked — name, location, badge with the date — and the
  page is not wider than the screen.

Nothing here changes data.

Proven red (restored after): the `width: 136` of the column Inschrijvingen taken
out of the columns in `admin_ui.py` → the five-heads test fails at "Inschrijvingen
is not 136 px: [380, 152, 220, 104]", at 1 440 and at 1 920 px. Found by this
test, not planned: with `hx-include` on the list holder the row link carried the
toolbar's fields to the record (`?scope=…&per_page=…`); the holder no longer
includes the form, and the second test says so.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, login_met_sessie, pagina_klaar  # noqa: E402

_TABLE = """() => {
  const vis = e => e.checkVisibility();
  const frame = document.querySelector('#aa-lijst [data-table-frame]');
  const heads = [...frame.querySelectorAll('thead th')].filter(vis);
  const rows = [...frame.querySelectorAll('tbody tr[data-row]')];
  const box = e => { const r = e.getBoundingClientRect(); return {x: r.left, r: r.right, y: r.top, b: r.bottom, w: r.width, h: r.height}; };
  const first = rows[0];
  const cells = n => [...first.querySelectorAll(`[data-cell=${n}]`)].filter(vis);
  const lastHead = heads[heads.length - 1];
  const lastCell = [...first.children].filter(vis).pop();
  return {
    columns: heads.map(h => h.innerText.trim()),
    head_h: heads.map(h => Math.round(h.getBoundingClientRect().height)),
    head_x: heads.map(h => Math.round(h.getBoundingClientRect().left)),
    frame: box(frame),
    last_head_right: Math.round(lastHead.getBoundingClientRect().right),
    last_cell_right: Math.round(lastCell.getBoundingClientRect().right),
    rows: rows.length,
    badges_first_row: [...first.querySelectorAll('[data-badge]')].map(b => b.innerText.trim()),
    location_visible: cells('context').length,
    registrations_visible: cells('extra').length,
    name_x: Math.round(box(cells('name')[0]).x),
    scroll: document.documentElement.scrollWidth, width: innerWidth, height: innerHeight,
    frame_scroll: [frame.scrollWidth, frame.clientWidth],
  };
}"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _open(browser, size, url="/admin/activiteiten"):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(base_url=BASE, viewport={"width": size[0], "height": size[1]})
    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
    page.goto(url)
    pagina_klaar(page)
    return page


@pytest.mark.parametrize("width", [1440, 1920])
def test_five_heads_on_one_line_and_the_last_cell_reaches_the_frames_edge(browser, width):
    page = _open(browser, (width, 900))
    t = page.evaluate(_TABLE)
    print(f"MEASURE {width}", t)
    page.close()

    assert t["rows"] >= 1, "the seed holds a coming activity"
    assert t["columns"] == ["Activiteit", "Datum", "Locatie", "Inschrijvingen", "Status"]
    assert t["head_h"] == [36] * 5, f"a head wraps: {t['head_h']}"
    assert abs(t["last_cell_right"] - t["frame"]["r"]) <= 2, (
        f"the last column stops short of the frame: {t['last_cell_right']} v {t['frame']['r']}"
    )
    assert t["last_head_right"] == t["last_cell_right"]
    assert t["scroll"] == t["width"] and t["frame_scroll"][0] == t["frame_scroll"][1]
    # The columns stand packed to the left: the heads' x keep the kit's widths.
    gaps = [b - a for a, b in zip(t["head_x"], t["head_x"][1:])]
    assert gaps[0] == 380 or gaps[0] < 380, f"the name column is wider than its 380 px: {gaps}"
    assert gaps[1] == 152, f"Datum is not 152 px: {gaps}"
    assert gaps[2] == 220, f"Locatie is not 220 px: {gaps}"
    assert gaps[3] == 136, f"Inschrijvingen is not 136 px: {gaps}"
    assert t["badges_first_row"], "the Status cell is never empty"


def test_a_click_on_the_name_opens_the_activity_and_the_way_back_keeps_the_sort(browser):
    page = _open(browser, (1440, 900), "/admin/activiteiten?sort=naam")
    name = page.locator("#aa-lijst tbody tr[data-row] [data-row-link]").first
    title = name.inner_text()
    name.click()
    # A boosted navigation pushes the address and fires no `load`.
    page.wait_for_function("() => /^\\/admin\\/activiteiten\\/\\d+$/.test(location.pathname)")
    pagina_klaar(page)
    assert title in page.locator("h1").first.inner_text()
    # The row link asks for the record and nothing else: no field of the toolbar
    # rides along (`hx-include` on the list holder did that).
    assert "scope=" not in page.url and "per_page=" not in page.url, page.url
    page.locator("[data-way-back]").first.click()
    page.wait_for_function("() => location.pathname === '/admin/activiteiten'")
    pagina_klaar(page)
    assert "sort=naam" in page.url
    page.close()


def test_a_click_on_the_head_datum_turns_the_sort(browser):
    page = _open(browser, (1440, 900))
    with htmx_afgerond(page):
        page.locator('#aa-lijst a[data-sort="datum"]').click()
    assert "sort=-datum" in page.url
    assert page.locator('#aa-lijst th[aria-sort="descending"]').count() == 1
    with htmx_afgerond(page):
        page.locator('#aa-lijst a[data-sort="datum"]').click()
    assert "sort=datum" in page.url and "sort=-datum" not in page.url
    assert page.locator('#aa-lijst th[aria-sort="ascending"]').count() == 1
    page.close()


def test_at_390_the_rows_are_stacked_and_the_page_is_not_wider_than_the_screen(browser):
    page = _open(browser, (390, 844))
    t = page.evaluate(_TABLE)
    print("MEASURE 390", t)
    page.close()

    assert t["rows"] >= 1
    assert t["scroll"] == t["width"], "the page is wider than the screen"
    assert t["location_visible"] == 1, "the location stands as the context line of the row"
    assert t["registrations_visible"] == 0, "Inschrijvingen is not shown in a stacked row"
    assert t["badges_first_row"], "the badge stands in the row"
