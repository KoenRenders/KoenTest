"""E2E: the activity's summary and its list tabs in a browser (#1560, CR-11
pilot A, K6).

What a server test cannot see:

- **the frame does not move** (B7 test 12): the head and the tab bar stand at
  the same place on Gegevens, Inschrijvingen and Betalingen;
- **the summary card** is 300 px wide at the right of the form on a desktop and
  a strip under the tabs on a phone; a list tab has neither, its toolbar stands
  directly under the tabs and its table takes the full width;
- **one open row per list**: a second row closes the first; a collapsed group
  hides its rows and shows them again as they were;
- **the way back lands on the row**: from the registration's page the tab opens
  with that row unfolded and the focus on it;
- **the copy button** copies the public link in place — a check mark at the
  button, no screen, no toast — and when the browser refuses, shows no check
  mark and selects the address;
- on the embedded Betalingen tab a click on a row unfolds it and leaves the
  page where it is, and the row's own action stays a button of its own.

The activity is made for this file (#1880): one component, one product and two
registrations by transfer, so two open bookings. It used to be "the activity the
payments list names first", and that is whichever activity got the newest
booking: after `shell/test_view_transition_rule.py`, which registers once on an
activity of its own, the tabs tests met an activity with one registration. The
activity stays — one with registrations is not deleted (#1561), and its bookings
are a financial fact — as the seed's own does.

Proven red (each on this branch, restored after):
- the list's one `openRow` state made a state per row → the one-open-row test
  fails (two rows open);
- the group's collapse rule taken out of the CSS → the group test fails;
- the landing on the open row taken out of the shell's handler after a
  navigation → the way-back test fails (the focus is on the title);
- the card's container query removed → the desktop geometry test fails (the
  card is a strip of the full width);
- the toggle's click area removed → the click-on-the-date test fails.
"""

import os
import sys
from datetime import date, timedelta
from decimal import Decimal

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_met_sessie, pagina_klaar  # noqa: E402

_BOXES = """() => {
  const box = s => { const e = document.querySelector(s); if (!e || !e.checkVisibility()) return null;
    const r = e.getBoundingClientRect(); return {x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)}; };
  const rows = [...document.querySelectorAll('tr[data-row]')].filter(e => e.checkVisibility());
  const r0 = rows.length ? rows[0].getBoundingClientRect() : null;
  return {
    head: box('[data-record-head]'), tabs: box('[data-related-tabs]'),
    card: box('[data-summary-card]'), form: box('[data-form-column]'),
    toolbar: box('[data-toolbar]'), frame: box('[data-table-frame]'),
    first_row: r0 ? {y: Math.round(r0.top), bottom: Math.round(r0.bottom)} : null,
    scroll: document.documentElement.scrollWidth, width: innerWidth, height: innerHeight,
  };
}"""

#: What an unfolding row left in the page (#1636: none of it may be there).
_DISCLOSURES = """() => document.querySelectorAll(
  '[data-row-toggle], tr[data-row-detail], [data-row-part], [data-table-frame] details').length"""
_ROW = """(row) => { const r = e => { const b = e.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top + scrollY), Math.round(b.width), Math.round(b.height)]; };
  const cell = n => row.querySelector(`[data-cell="${n}"]`);
  const shown = n => { const c = n === 'balance' ? row.querySelector('[data-balance]') : cell(n); return !!c && c.checkVisibility(); };
  return {row: r(row), name: r(row.querySelector('[data-row-link]')),
          shown: Object.fromEntries(['name', 'context', 'date', 'more', 'amount', 'balance', 'status', 'actions'].map(n => [n, shown(n)])),
          stacked: row.querySelector('[data-stacked-balance]') ? row.querySelector('[data-stacked-balance]').checkVisibility() : null,
          balance_colour: getComputedStyle(row.querySelector('[data-balance] span')).color,
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _page(browser, size, **context):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(
        base_url=BASE, viewport={"width": size[0], "height": size[1]}, **context
    )
    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
    return page


#: The registrations of this file's activity. Each has an address of its own
#: that holds no name: the list's search reads the address too.
REGISTRATIONS = (
    ("Lowie Tabbladen", "e2e-1880-a@example.org"),
    ("Fien Lijstrij", "e2e-1880-b@example.org"),
)


@pytest.fixture(scope="module")
def activity() -> str:
    """The address of an activity made for this file, with the registrations
    and the bookings the tests count. Through the real way in, as the seed
    does it: a hand-built registration would carry no booking."""
    from fastapi import BackgroundTasks

    import app.main  # noqa: F401  the whole app: the handlers a registration publishes to
    from app.database import SessionLocal
    from app.domains.activities.api import (
        Activity,
        ActivityDate,
        ActivityProduct,
        ActivitySubRegistration,
        Registration,
        register_for_activity,
    )
    from app.domains.payment.api import PaymentRecord
    from app.schemas.activity import RegistrationCreate, RegistrationItemCreate

    db = SessionLocal()
    try:
        made = Activity(name="Tabbladentest")  # short: the head keeps one line on a phone
        db.add(made)
        db.flush()
        db.add(ActivityDate(activity_id=made.id, start_date=date.today() + timedelta(days=45)))
        component = ActivitySubRegistration(
            activity_id=made.id,
            name="Etentje",
            registration_type_code="INDIVIDUAL",
            price=Decimal("0"),
            is_free=True,
        )
        db.add(component)
        db.flush()
        product = ActivityProduct(
            component_id=component.id, name="Soep", price=Decimal("10.00"), is_free=False
        )
        db.add(product)
        db.commit()
        for name, email in REGISTRATIONS:
            register_for_activity(
                db,
                made.id,
                RegistrationCreate(
                    contact_name=name,
                    contact_email=email,
                    phone="0470000000",
                    component_id=component.id,
                    payment_method="transfer",
                    items=[RegistrationItemCreate(product_id=product.id, quantity=2)],
                ),
                BackgroundTasks(),
            )
        # One registration is partly settled, as in the seed: beside its open
        # booking a paid one. Its balance then differs from its amount, which
        # is what a stacked row shows under the amount.
        first = (
            db.query(Registration)
            .filter(Registration.activity_id == made.id)
            .order_by(Registration.id)
            .first()
        )
        db.add(
            PaymentRecord(
                payable_type="registration",
                payable_id=first.id,
                type="charge",
                amount=Decimal("20.00"),
                amount_paid=Decimal("20.00"),
                method="transfer",
                status="paid",
                structured_communication="+++000/0000/01880+++",
            )
        )
        db.commit()
        return f"/admin/activiteiten/{made.id}"
    finally:
        db.close()


def _boxes(page, url) -> dict:
    page.goto(url)
    pagina_klaar(page)
    return page.evaluate(_BOXES)


def test_the_frame_does_not_move_and_only_gegevens_has_the_card(browser, activity):
    page = _page(browser, (1440, 1080))
    gegevens = _boxes(page, activity)
    registrations = _boxes(page, activity + "/inschrijvingen")
    payments = _boxes(page, activity + "/betalingen")
    page.close()

    for tab in (registrations, payments):
        assert tab["head"] == gegevens["head"] and tab["tabs"] == gegevens["tabs"], (gegevens, tab)
        assert tab["scroll"] == tab["width"], tab
    # Gegevens: the card, 300 px, at the right of the form and level with it.
    card, form = gegevens["card"], gegevens["form"]
    assert card and card["w"] == 300, gegevens
    assert card["x"] >= form["x"] + form["w"] and card["y"] == form["y"], gegevens
    assert 190 <= card["h"] <= 240, card
    # A list tab: no card, the toolbar directly under the tabs, the table as
    # wide as the tab bar, and the first row well inside the first screen.
    under_tabs = gegevens["tabs"]["y"] + gegevens["tabs"]["h"]
    for tab in (registrations, payments):
        assert tab["card"] is None, tab
        assert 0 <= tab["toolbar"]["y"] - under_tabs <= 16, tab
        assert tab["frame"]["w"] == tab["tabs"]["w"], tab
        assert tab["first_row"]["y"] - under_tabs <= 150, tab


def test_on_a_phone_the_summary_is_a_strip_under_the_tabs(browser, activity):
    page = _page(browser, (390, 844))
    gegevens = _boxes(page, activity)
    registrations = _boxes(page, activity + "/inschrijvingen")
    payments = _boxes(page, activity + "/betalingen")
    page.close()

    card, form, tabs = gegevens["card"], gegevens["form"], gegevens["tabs"]
    assert card["w"] == 358 and 110 <= card["h"] <= 150, card
    # Under the tabs, above the form.
    assert tabs["y"] + tabs["h"] <= card["y"] and card["y"] + card["h"] <= form["y"], gegevens
    for name, tab in (("inschrijvingen", registrations), ("betalingen", payments)):
        assert tab["card"] is None and tab["scroll"] == 390, (name, tab)
        # The first row is on the first screen, whole.
        assert tab["first_row"]["bottom"] <= tab["height"], (name, tab)


def test_a_row_is_the_way_in_and_a_group_still_collapses(browser, activity):
    """#1636. Red against master: the click on a row unfolded it and the page
    stayed; four traces of a disclosure per row."""
    page = _page(browser, (1440, 1080))
    tab = activity + "/inschrijvingen"
    page.goto(tab)
    pagina_klaar(page)
    rows = page.locator("tr[data-row]")
    assert rows.count() == len(REGISTRATIONS), "the tab does not show this file's registrations"
    assert page.evaluate(_DISCLOSURES) == 0
    first = rows.nth(0)
    key = first.get_attribute("data-row-key")
    m = first.evaluate(_ROW)
    y_first = m["row"][1]
    print("MEASURE registrations row 1440", m)
    # Seven columns of data and the actions, all on one line at 1 440 — and the
    # name keeps room to read (with the six-column widths it was left 13 px).
    assert all(m["shown"].values()), m["shown"]
    assert m["page"][0] == m["page"][1]
    assert m["name"][2] >= 80 and m["row"][3] <= 90, f"the row is squeezed: {m['name']}, {m['row']}"
    assert y_first < 500, f"the first row starts at y {y_first}"

    # The row's `⋯`: the jumps. It opens without leaving the page.
    first.locator("[data-row-menu-trigger]").click()
    menu = first.locator("[data-row-menu]")
    menu.wait_for(state="visible")
    items = [t.strip() for t in menu.locator('[role="menuitem"]').all_inner_texts()]
    assert items[:2] == ["Inschrijving openen", "Betaling openen"], items
    assert page.url.endswith("/inschrijvingen")
    page.keyboard.press("Escape")
    menu.wait_for(state="hidden")

    # The group collapses and shows its rows again.
    group = page.locator("[data-group-toggle]").first
    group.click()
    assert group.get_attribute("aria-expanded") == "false"
    assert first.is_hidden()
    group.click()
    first.wait_for(state="visible")

    # A click anywhere on the row — its date — opens the registration's page.
    # (`force`: the link's click area lies over the cell, which is the point.)
    first.locator('[data-cell="date"]').click(force=True)
    page.wait_for_url(lambda url: f"/admin/inschrijvingen/{key}" in url)
    pagina_klaar(page)
    assert "rij%3D" + key in page.url or f"rij={key}" in page.url
    page.close()


def test_the_way_back_from_a_registration_lands_on_its_row(browser, activity):
    page = _page(browser, (1440, 1080))
    page.goto(activity + "/inschrijvingen?sort=-naam")
    pagina_klaar(page)
    row = page.locator("tr[data-row]").nth(1)
    key = row.get_attribute("data-row-key")
    row.locator("[data-row-link]").click()
    page.wait_for_url(lambda url: f"/admin/inschrijvingen/{key}" in url)
    pagina_klaar(page)

    # The way back gives the tab as it was left — the sort — and names the row.
    page.locator(f"a[href*='/inschrijvingen?'][href*='rij={key}']").first.click()
    pagina_klaar(page)
    assert page.url.endswith(f"/inschrijvingen?sort=-naam&rij={key}"), page.url
    assert page.evaluate(_DISCLOSURES) == 0
    # The row it left: in view, its link focused.
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.hasAttribute('data-row-link')"
    )
    focused = page.evaluate("() => document.activeElement.closest('tr[data-row]').dataset.rowKey")
    assert focused == key, f"the focus is on row {focused}, the visitor left row {key}"
    box = page.locator(f'tr[data-row-key="{key}"]').bounding_box()
    assert 0 <= box["y"] and box["y"] + box["height"] <= 1080, f"the row is out of view: {box}"
    page.close()


def test_on_a_phone_the_row_is_stacked_with_the_balance_under_the_amount(browser, activity):
    """#1636: below 900 px a row is stacked as on Betalingen (K2) — the Saldo
    column goes, and an open balance stands under the amount."""
    page = _page(browser, (390, 844))
    page.goto(activity + "/inschrijvingen")
    pagina_klaar(page)
    assert page.evaluate(_DISCLOSURES) == 0
    rows = page.locator("tr[data-row]")
    measured = [rows.nth(i).evaluate(_ROW) for i in range(rows.count())]
    print("MEASURE registrations row 390", measured[0])
    for m in measured:
        assert m["page"][0] == 390, m["page"]
        assert m["shown"]["name"] and m["shown"]["amount"] and m["shown"]["status"], m["shown"]
        assert not m["shown"]["balance"], "the Saldo column is a column of a wide screen"
    # Where a registration has an open balance, it reads under its amount.
    assert any(m["stacked"] for m in measured), "no row shows its balance under the amount"
    page.close()


def test_the_toolbar_keeps_its_state_in_the_tabs_address(browser, activity):
    page = _page(browser, (1440, 1080))
    page.goto(activity + "/inschrijvingen")
    pagina_klaar(page)
    names = [n.strip() for n in page.locator("[data-row-link]").all_inner_texts()]
    assert sorted(names) == sorted(name for name, _ in REGISTRATIONS), names
    needle = names[1].split()[0]
    page.locator('#reg-filter input[type="search"]').fill(needle)
    page.wait_for_function("() => location.search.includes('q=')")
    htmx_stil(page)
    assert "/inschrijvingen?" in page.url and "/lijst" not in page.url
    shown = [n.strip() for n in page.locator("[data-row-link]").all_inner_texts()]
    assert shown == [names[1]], shown
    assert page.locator("[data-toolbar-count]").inner_text().strip() == "1–1 van 1"
    # One shell and one record head: the fragment landed in the list holder.
    assert page.locator("[data-record-head]").count() == 1
    page.close()


def test_the_copy_button_copies_in_place(browser, activity):
    page = _page(browser, (1440, 1080), permissions=["clipboard-read", "clipboard-write"])
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    page.goto(activity)
    pagina_klaar(page)
    card = page.locator("[data-summary-card]")
    link = card.locator("[data-summary-link]").get_attribute("href")
    button = card.locator("button[data-copy]")
    icons = button.locator("span")
    assert icons.nth(0).is_visible() and icons.nth(1).is_hidden()
    before = page.url

    button.click()
    icons.nth(1).wait_for(state="visible")
    # The check mark stands where the copy icon stood; nothing else happened.
    assert icons.nth(0).is_hidden()
    assert page.evaluate("() => navigator.clipboard.readText()") == link
    assert page.url == before and not dialogs
    assert page.locator("#toasts > *").count() == 0
    assert page.locator("[role=dialog]:visible").count() == 0
    page.close()


def test_a_refused_copy_shows_no_check_mark_and_selects_the_address(browser, activity):
    page = _page(browser, (1440, 1080))
    page.goto(activity)
    pagina_klaar(page)
    # The browser refuses both ways of copying.
    page.evaluate(
        """() => { Object.defineProperty(navigator, 'clipboard', {value: {writeText: () => Promise.reject(new Error('refused'))}, configurable: true});
                   document.execCommand = () => false; }"""
    )
    card = page.locator("[data-summary-card]")
    button = card.locator("button[data-copy]")
    button.click()
    page.wait_for_function("() => String(getSelection()).length > 0")
    assert button.locator("span").nth(1).is_hidden(), "a check mark after a copy that failed"
    selected = page.evaluate("() => String(getSelection())")
    assert selected == card.locator("[data-summary-link]").inner_text()
    page.close()


def test_an_embedded_booking_opens_its_page_and_the_way_back_returns_to_the_tab(browser, activity):
    """#1636 (Koen's addition): on a record's tab a booking's row opens the
    booking's page, as on the main list; the way back returns to the tab with
    its state, to the row it left. Red against master: the click unfolded the
    row and the page stayed."""
    page = _page(browser, (1440, 1080))
    tab = activity + "/betalingen"
    page.goto(tab + "?zicht=alle")
    pagina_klaar(page)
    assert page.evaluate(_DISCLOSURES) == 0
    row = page.locator("tr[data-row]").first
    key = row.get_attribute("data-row-key")
    # The row's ⋯ opens its menu and the page stays.
    row.locator("[data-row-menu-trigger]").click()
    row.locator("[data-row-menu]").wait_for(state="visible")
    assert "/betalingen" in page.url and f"/betalingen/{key}" not in page.url
    page.keyboard.press("Escape")

    # A click on the amount opens the booking's page.
    row.locator("[data-amount]").click(force=True)
    page.wait_for_url(lambda url: f"/admin/betalingen/{key}" in url)
    pagina_klaar(page)
    page.locator("[data-way-back]").click()
    pagina_klaar(page)
    assert "/activiteiten/" in page.url and page.url.endswith(f"boeking={key}"), page.url
    assert "zicht=alle" in page.url, "the tab's state is gone"
    assert page.evaluate(_DISCLOSURES) == 0
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.hasAttribute('data-row-link')"
    )
    assert (
        page.evaluate("() => document.activeElement.closest('tr[data-row]').dataset.rowKey") == key
    )
    page.close()
