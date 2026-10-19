"""E2E: Organisaties on the kit — the list and the record (#1932).

What only a browser shows: the heads on one line, where the last column ends, the
rows of the record in read mode and their gap, and what a click does.

- At 1 440 and 1 920 px the list has three columns (Organisatie, Rechtsvorm,
  Status — Soort and Onder went with CR-20); every head stands on one line
  (36 px); the last column's cell reaches the frame's right edge (the kit's rule
  since #1927).
- A click on a row's name opens the record; its way back returns to the list with
  the state it had.
- The record in read mode at 1 440 px (end state §2.2; K2, #1928): Telefoon and
  Mobiel share a row, E-mail stands under them at full width, and the rows of a
  card are 4 px apart.
- The record in edit mode at 1 440 px: Straat half, Huisnummer and Bus a quarter,
  Postcode full — the shape of the member screen.
- At 390 px neither the list nor the record is wider than the screen.

Nothing here changes data.

Proven red (restored after): the Mobiel fact of the read mode given `data-span="full"`
→ "Telefoon and Mobiel do not share a row"; `data-mode="read"` set to `edit` on the
flow → the 4 px gap is gone.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import PLATFORM, login_met_sessie, pagina_klaar  # noqa: E402

ORGANISATION_ID = 1  # the legal entity of the seed

_LIST = """() => {
  const vis = e => e.checkVisibility();
  const frame = document.querySelector('#org-lijst [data-table-frame]');
  const heads = [...frame.querySelectorAll('thead th')].filter(vis);
  const first = frame.querySelector('tbody tr[data-row]');
  const lastCell = [...first.children].filter(vis).pop();
  return {
    columns: heads.map(h => h.innerText.trim()),
    head_h: heads.map(h => Math.round(h.getBoundingClientRect().height)),
    head_x: heads.map(h => Math.round(h.getBoundingClientRect().left)),
    frame_right: Math.round(frame.getBoundingClientRect().right),
    last_right: Math.round(lastCell.getBoundingClientRect().right),
    rows: frame.querySelectorAll('tbody tr[data-row]').length,
    scroll: document.documentElement.scrollWidth, width: innerWidth,
  };
}"""

_RECORD = """() => {
  const box = e => { const r = e.getBoundingClientRect(); return {x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), b: Math.round(r.bottom)}; };
  const card = document.querySelector('#org-section-organisation');
  const cells = [...card.querySelectorAll('[data-form-grid] > [data-span], [data-form-grid] > p')];
  const spans = cells.map(c => c.getAttribute('data-span'));
  const rows = {};
  cells.forEach(c => { const b = box(c); (rows[b.y] = rows[b.y] || []).push(b); });
  const ys = Object.keys(rows).map(Number).sort((a, b) => a - b);
  const gaps = ys.slice(1).map((y, i) => y - Math.max(...rows[ys[i]].map(b => b.b)));
  return {
    spans, row_sizes: ys.map(y => rows[y].length), gaps,
    first_x: rows[ys[0]][0].x, mail_w: rows[ys[2]] ? rows[ys[2]][0].w : null,
    grid_w: box(card.querySelector('[data-form-grid]')).w,
    scroll: document.documentElement.scrollWidth, width: innerWidth,
    sections: [...document.querySelectorAll('[data-form-section] h2')].map(h => h.innerText.trim()),
    mode: document.querySelector('[data-form-flow]').getAttribute('data-mode'),
  };
}"""


@pytest.fixture(scope="module")
def operator():
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.auth.models import User, UserRole

    email = f"e2e-1932-{secrets.token_hex(3)}@example.org"
    db = SessionLocal()
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
    db.commit()
    db.close()
    return make_session_value(email)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _open(browser, operator, size, url):
    page = browser.new_page(base_url=PLATFORM, viewport={"width": size[0], "height": size[1]})
    login_met_sessie(page, operator, PLATFORM)
    page.goto(url)
    pagina_klaar(page)
    return page


@pytest.mark.parametrize("width", [1440, 1920])
def test_the_list_has_its_heads_on_one_line_and_its_last_cell_reaches_the_edge(
    browser, operator, width
):
    page = _open(browser, operator, (width, 900), "/admin/organisaties")
    t = page.evaluate(_LIST)
    print(f"MEASURE list {width}", t)
    page.close()

    assert t["rows"] >= 1
    # CR-20 phase 2: Gebruikt door, how many tenants use the party (F5).
    assert t["columns"] == ["Organisatie", "Gebruikt door", "Rechtsvorm", "Status"]
    assert t["head_h"] == [36] * 4, f"a head wraps: {t['head_h']}"
    assert abs(t["last_right"] - t["frame_right"]) <= 2, (
        f"the last column stops short of the frame: {t['last_right']} v {t['frame_right']}"
    )
    gaps = [b - a for a, b in zip(t["head_x"], t["head_x"][1:])]
    assert gaps == [380, 140, 200], f"the columns are not at the kit's widths: {gaps}"
    assert t["scroll"] == t["width"]


def test_a_click_on_the_name_opens_the_record_and_the_way_back_keeps_the_state(browser, operator):
    page = _open(browser, operator, (1440, 900), "/admin/organisaties?sort=-naam")
    page.locator("#org-lijst tbody tr[data-row] [data-row-link]").first.click()
    page.wait_for_function("() => /^\\/admin\\/organisaties\\/\\d+$/.test(location.pathname)")
    pagina_klaar(page)
    assert "scope=" not in page.url and "per_page=" not in page.url, page.url
    page.locator("[data-way-back]").first.click()
    page.wait_for_function("() => location.pathname === '/admin/organisaties'")
    pagina_klaar(page)
    assert "sort=-naam" in page.url
    page.close()


def test_the_record_in_read_mode_shares_a_row_for_phone_and_mobile_and_sets_rows_4_px_apart(
    browser, operator
):
    page = _open(browser, operator, (1440, 900), f"/admin/organisaties/{ORGANISATION_ID}")
    t = page.evaluate(_RECORD)
    print("MEASURE record read 1440", t)
    page.close()

    assert t["mode"] == "read"
    assert t["sections"] == ["Organisatie", "Adres", "Rekening", "Nummers", "Personen"]
    # Naam and Rechtsvorm; Telefoon and Mobiel; E-mail; Website; Facebook; Instagram; TikTok.
    assert t["spans"][:4] == ["half"] * 4
    assert t["row_sizes"][:2] == [2, 2], f"Telefoon and Mobiel do not share a row: {t['row_sizes']}"
    assert t["row_sizes"][2] == 1 and t["spans"][4] == "full"
    assert t["mail_w"] >= t["grid_w"] - 2, "E-mail does not stand at full width under them"
    assert set(t["gaps"]) == {4}, f"the rows of a card are not 4 px apart: {t['gaps']}"
    assert t["scroll"] == t["width"]


def test_the_record_in_edit_mode_has_the_shape_of_the_member_address(browser, operator):
    page = _open(
        browser, operator, (1440, 900), f"/admin/organisaties/{ORGANISATION_ID}?bewerken=1"
    )
    sizes = page.evaluate(
        """() => Object.fromEntries(['street', 'house_number', 'bus_number', 'postal_code'].map(n => {
          const r = document.querySelector(`[data-field=${n}]`).getBoundingClientRect();
          return [n, [Math.round(r.left), Math.round(r.top), Math.round(r.width)]];
        }))"""
    )
    print("MEASURE record edit 1440", sizes)
    page.close()

    street, number, bus, postal = (
        sizes[k] for k in ("street", "house_number", "bus_number", "postal_code")
    )
    assert street[1] == number[1] == bus[1], "Straat, Huisnummer and Bus do not share a row"
    assert postal[1] > street[1], "Postcode stands under them"
    assert abs(number[2] - bus[2]) <= 1 and abs(street[2] - 2 * number[2]) <= 14
    assert postal[2] >= street[2] + number[2] + bus[2], "Postcode is not the full width"


def test_neither_the_list_nor_the_record_is_wider_than_a_phone(browser, operator):
    for url in ("/admin/organisaties", f"/admin/organisaties/{ORGANISATION_ID}"):
        page = _open(browser, operator, (390, 844), url)
        assert page.evaluate("document.documentElement.scrollWidth") <= 390, url
        page.close()
