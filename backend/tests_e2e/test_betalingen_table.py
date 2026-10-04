"""E2E: the payments table in a browser (CR-11 pilot A, K2 — #1556).

What only a browser shows: the heights, which columns a narrower list keeps,
what a click anywhere on a row does, and the stacked rows on a phone.

- At 1 440 px the table has seven columns; in a narrower window (1 100 px, the
  list 988 px wide) Ontvangen has left, Context is still there. Kolommen →
  Tonen brings Ontvangen back and the URL carries the choice.
- The head is 36 px, a row of two lines 57 px; the `⋯` of every row stands at
  one x; a row shows at most one action.
- A click on a row's amount opens the booking's page; a click on the context
  opens the activity, not the booking; the way back returns to the list as it
  was left. "Bevestig" asks its question and does not navigate.
- A click on a column head sorts, and the URL carries the sort.
- At 390 × 844 the rows are stacked — name, context, badge and amount — with
  the action and `⋯` at the top right, the first row on the first screen, and
  the page is not wider than the screen; "Sorteren" stands under `⋯`.

The seed holds five registration groups. Nothing here changes data: "Bevestig"
is cancelled.

Proven red (on this branch, restored after): the row link's `::after` taken out
of the CSS → the click on the amount opens nothing; the container query for
priority 1 taken out → Ontvangen is still there at 1 100 px; the stacked-rows
rule taken out → the phone test fails (the page is wider than the screen);
`hx-include="unset"` taken off the sort link → the sort test fails. That last one
was found by this test, not planned: the list holder includes the toolbar's
form, whose own `sort` field then followed the link's and won, so the click
pushed `sort=naam` and the list did not move.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, login_met_sessie, pagina_klaar  # noqa: E402

_TABLE = """() => {
  const vis = e => e.checkVisibility();
  const rows = [...document.querySelectorAll('#betalingen-lijst tr[data-row]')];
  const heads = [...document.querySelectorAll('#betalingen-lijst thead th')];
  const menus = [...document.querySelectorAll('[data-row-menu-trigger]')].filter(vis);
  const first = rows[0];
  const box = e => { const r = e.getBoundingClientRect(); return {x: r.left, y: r.top, r: r.right, b: r.bottom, h: r.height}; };
  const cell = n => first.querySelector(`[data-cell=${n}]`);
  return {
    columns: heads.filter(vis).map(h => h.innerText.trim() || 'Acties'),
    head_box_h: document.querySelector('#betalingen-lijst thead').getBoundingClientRect().height,
    head_h: heads[0].getBoundingClientRect().height,
    row_heights: rows.filter(r => !r.querySelector('[data-cell=name] div')).map(r => r.getBoundingClientRect().height),
    first_row_y: first.getBoundingClientRect().top,
    menu_right: [...new Set(menus.map(m => Math.round(m.getBoundingClientRect().right)))],
    actions_per_row: rows.map(r => r.querySelectorAll('[data-row-action]').length),
    name: box(cell('name')), context: cell('context').checkVisibility() ? box(cell('context')) : null,
    status: box(cell('status')), amount: box(cell('amount')), actions: box(cell('actions')),
    extras_visible: [...first.querySelectorAll('[data-cell=extra]')].filter(vis).length,
    scroll: document.documentElement.scrollWidth, width: innerWidth, height: innerHeight,
    frame_scroll: [document.querySelector('[data-table-frame]').scrollWidth, document.querySelector('[data-table-frame]').clientWidth],
  };
}"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _open(browser, size, url="/admin/betalingen"):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(base_url=BASE, viewport={"width": size[0], "height": size[1]})
    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
    page.goto(url)
    pagina_klaar(page)
    return page


def test_at_1440_seven_columns_a_36_px_head_and_rows_of_57(browser):
    page = _open(browser, (1440, 900))
    t = page.evaluate(_TABLE)
    print("MEASURE 1440", t)
    page.close()

    assert t["columns"] == [
        "Boeking",
        "Context",
        "Status",
        "Bedrag",
        "Ontvangen",
        "Saldo",
        "Acties",
    ]
    assert t["head_h"] == 36
    assert t["row_heights"] and all(abs(h - 57) <= 1 for h in t["row_heights"]), t["row_heights"]
    assert len(t["menu_right"]) == 1, f"the ⋯ of the rows do not align: {t['menu_right']}"
    assert max(t["actions_per_row"]) <= 1, "a row shows more than one action"
    assert 1 in t["actions_per_row"] and 0 in t["actions_per_row"], (
        "the seed has open and settled rows"
    )
    assert t["scroll"] == t["width"] and t["frame_scroll"][0] == t["frame_scroll"][1]


def test_a_narrower_list_drops_ontvangen_first_and_the_chooser_brings_it_back(browser):
    page = _open(browser, (1100, 900))
    t = page.evaluate(_TABLE)
    print("MEASURE 1100", t)
    assert t["columns"] == ["Boeking", "Context", "Status", "Bedrag", "Saldo", "Acties"]
    assert t["scroll"] == t["width"], "the table scrolls sideways"

    page.locator("[data-more-button]").click()
    page.locator("[data-columns-chooser] summary").click()
    with htmx_afgerond(page):
        page.locator("select[name=kol_ontvangen]").select_option("show")
    assert "kol_ontvangen=show" in page.url
    again = page.evaluate(_TABLE)
    assert "Ontvangen" in again["columns"]
    assert again["scroll"] == again["width"], "showing the column made the page wider"

    # The choice is in the URL: a reload keeps it.
    page.reload()
    pagina_klaar(page)
    assert "Ontvangen" in page.evaluate(_TABLE)["columns"]
    page.close()


def test_a_click_anywhere_on_the_row_opens_the_booking_and_back_returns(browser):
    page = _open(browser, (1440, 900), "/admin/betalingen?zicht=openstaand")
    left_at = page.url
    name = page.locator("#betalingen-lijst [data-row-link]").first.inner_text()

    # The amount is not a link; the row's link covers it. A click at the cell's
    # centre, as a hand does it — Playwright's own `click()` on the cell refuses,
    # because it sees the link's click area on top of it, which is the point.
    cell = page.locator("#betalingen-lijst tr[data-row]").first.locator("[data-cell=amount]")
    box = cell.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    pagina_klaar(page)
    assert "/admin/betalingen/" in page.url and "terug=" in page.url
    assert name in page.locator("[data-record-head] h1").inner_text()

    page.locator("[data-way-back]").click()
    pagina_klaar(page)
    assert page.url == left_at
    assert page.locator("[data-status-filter] input[value=openstaand]").is_checked()
    page.close()


def test_the_context_opens_its_own_record_and_bevestig_does_not_navigate(browser):
    page = _open(browser, (1440, 900), "/admin/betalingen?zicht=openstaand")
    row = page.locator("#betalingen-lijst tr[data-row]").first

    row.locator("[data-row-action]").click()
    page.get_by_text("Als volledig betaald bevestigen?").wait_for(state="visible")
    assert "/admin/betalingen?" in page.url, "Bevestig navigated instead of asking"
    page.keyboard.press("Escape")

    row.locator("[data-cell=context] a[data-reference]").click()
    pagina_klaar(page)
    assert "/admin/betalingen/" not in page.url, "the context link opened the booking"
    assert "/admin/activiteiten/" in page.url or "/admin/leden/gezin/" in page.url
    assert "Betaling van" in page.locator("[data-way-back]").inner_text()
    page.close()


def test_a_column_head_sorts_and_the_url_carries_it(browser):
    page = _open(browser, (1440, 900))
    with htmx_afgerond(page):
        page.locator("#betalingen-lijst a[data-sort=naam]").click()
    assert "sort=naam" in page.url
    names = page.locator(
        "#betalingen-lijst tbody tr[data-row]:first-child [data-row-link]"
    ).all_inner_texts()
    assert names == sorted(names, key=str.casefold), names
    assert page.locator("#betalingen-lijst th[aria-sort=ascending]").count() == 1

    with htmx_afgerond(page):
        page.locator("#betalingen-lijst a[data-sort=naam]").click()
    assert "sort=-naam" in page.url
    assert page.locator("#betalingen-lijst th[aria-sort=descending]").count() == 1
    # A search keeps the sort: it is a field of the toolbar's form.
    with htmx_afgerond(page):
        page.locator("input[name=q]").fill("e")
    assert "sort=-naam" in page.url
    page.close()


def test_on_a_phone_the_rows_are_stacked_and_nothing_overflows(browser):
    page = _open(browser, (390, 844))
    t = page.evaluate(_TABLE)
    print("MEASURE 390", t)

    assert t["scroll"] == t["width"], "the page is wider than the screen"
    assert t["frame_scroll"][0] == t["frame_scroll"][1], "the table scrolls sideways"
    assert 0 < t["first_row_y"] < t["height"], "the first row is not on the first screen"
    assert t["head_box_h"] <= 1, "the head takes room on a phone"
    # Stacked: name, then the context under it, then the badge and the amount on
    # one line; the action and ⋯ at the top right; Ontvangen and Saldo not shown.
    assert t["name"]["y"] < t["context"]["y"] < t["status"]["y"]
    assert (
        abs((t["status"]["y"] + t["status"]["h"] / 2) - (t["amount"]["y"] + t["amount"]["h"] / 2))
        <= 3
    )
    assert t["amount"]["x"] > t["status"]["x"]
    assert abs(t["actions"]["y"] - t["name"]["y"]) <= 2 and t["actions"]["x"] > t["name"]["x"]
    assert t["extras_visible"] == 0
    assert max(t["actions_per_row"]) <= 1

    # "Sorteren" stands under ⋯ on a phone, and sorts.
    page.locator("[data-more-button]").click()
    mirror = page.locator("[data-sort-mirror]")
    mirror.wait_for(state="visible")
    with htmx_afgerond(page):
        mirror.select_option("naam")
    assert "sort=naam" in page.url and page.url.count("sort=") == 1
    page.close()


def test_an_open_row_menu_lies_over_the_rows_under_it(browser):
    """Every row's controls are a stacking level of their own, above the row's
    link. An open menu lifts its row above the others — or the `⋯` of the next
    row shows through it (seen on the first 1 440 px screenshot of K2)."""
    page = _open(browser, (1440, 900))
    page.locator("#betalingen-lijst [data-row-menu-trigger]").first.click()
    page.locator("#betalingen-lijst [data-row-menu]").first.wait_for(state="visible")
    covered = page.evaluate(
        """() => {
      const menu = [...document.querySelectorAll('[data-row-menu]')].find(m => m.checkVisibility());
      const box = menu.getBoundingClientRect();
      const under = [...document.querySelectorAll('[data-row-menu-trigger]')].slice(1)
        .map(t => t.getBoundingClientRect())
        .filter(r => r.left + r.width / 2 > box.left && r.left + r.width / 2 < box.right
                  && r.top + r.height / 2 > box.top && r.top + r.height / 2 < box.bottom);
      return under.map(r => !!document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)
                              .closest('[data-row-menu]'));
    }"""
    )
    page.close()
    assert covered, "no ⋯ lies under the open menu in this seed, so this proves nothing"
    assert all(covered), "a ⋯ of another row shows through the open menu"


_BALANCE = """() => {
  const extra = [...document.querySelectorAll('#betalingen-lijst [data-stacked-balance]')];
  return {
    total: extra.length,
    shown: extra.filter(e => e.checkVisibility()).map(e => {
      const r = e.getBoundingClientRect();
      const amount = e.previousElementSibling.getBoundingClientRect();
      const row = e.closest('tr').getBoundingClientRect();
      return {text: e.innerText.trim(), under: r.top >= amount.bottom - 1, right: Math.round(r.right), amount_right: Math.round(amount.right),
              inside: r.bottom <= row.bottom + 1 && r.right <= row.right + 1, colour: getComputedStyle(e).color,
              amount_colour: getComputedStyle(e.previousElementSibling).color, row_h: Math.round(row.height)};
    }),
    scroll: document.documentElement.scrollWidth, width: innerWidth,
  };
}"""


@pytest.fixture
def partly_paid():
    """One seeded booking made partly paid for the measurement, and put back:
    what the list holds by the time this test runs depends on the tests before
    it (a full run confirms the open bookings), so the test brings its own."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.payment.models import PaymentRecord, PaymentStatus

    db = SessionLocal()
    record = db.query(PaymentRecord).filter(PaymentRecord.amount > 0).first()
    assert record is not None, "the seed has no booking"
    was = (record.amount_paid, record.status)
    record.amount_paid = record.amount / 4
    record.status = PaymentStatus.PENDING
    db.commit()
    try:
        yield
    finally:
        record.amount_paid, record.status = was
        db.commit()
        db.close()


def test_on_a_phone_a_balance_that_differs_stands_under_the_amount(browser, partly_paid):
    """#1582: the stacked row has no Saldo column. Where the balance differs
    from the amount and is not zero — a partly paid booking, and the sum row of
    its registration — it stands under the amount, right-aligned with it, in
    the warning tone, inside its row; a wide list does not show it (it has the
    column).

    Proven red (on this branch, restored after): the stacked rule
    `[data-stacked-only]{display:block}` removed → nothing is shown at 390."""
    page = _open(browser, (390, 844))
    phone = page.evaluate(_BALANCE)
    print("MEASURE balance 390", phone)
    page.close()
    assert phone["total"] >= 1, "the partly paid booking shows no balance"
    assert len(phone["shown"]) == phone["total"], phone
    for extra in phone["shown"]:
        assert extra["text"].startswith(("nog € ", "terug € ")), extra
        assert extra["under"] and extra["inside"], extra
        assert abs(extra["right"] - extra["amount_right"]) <= 1, extra
        # The warning tone on the balance, never on the amount (Q36).
        assert extra["colour"] != extra["amount_colour"], extra
    assert phone["scroll"] == phone["width"], phone

    page = _open(browser, (1440, 900))
    wide = page.evaluate(_BALANCE)
    page.close()
    assert wide["total"] == phone["total"] and wide["shown"] == [], wide
