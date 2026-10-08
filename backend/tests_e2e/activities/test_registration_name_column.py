"""E2E: the Naam column of the registrations table has room for a name (#1741).

Found by Koen on HDEV (8 October 2026), on a household's tab Inschrijvingen in
a window of about 1 090 px: "die linkerkolom is wel niet breed genoeg". A name
broke in the middle of a word and a row was five lines high.

Measured before the change: five of the table's eight columns have the width
their content needs — 568 px together — so in a table of 900–1 100 px the name
was left with 47–76 px. And the household's record page is capped, so its table
is 1 024 px wide at EVERY desktop width: there the column was 76 px always.

What holds now (Koen, 8 October 2026: "1a" — Producten leaves first, Saldo
after it), on the household's tab and on the activity's tab, which share the
one table (`activities.api.registration_table`):

- the name column is at least 200 px wherever the table is a table; an
  ordinary name stands on one line, and so does the component under it;
- Producten leaves below 1 099 px of table width and Saldo below 979 px — the
  kit's own priorities, as on Betalingen;
- **the columns add up to the table**: a group row spans a fixed number of
  columns, and over a column that is gone the browser adds one — 127 px of
  nothing at 1 024 px, taken from the name. The group row follows the columns
  that leave;
- nothing is wider than its column, and the page is as wide as the window;
- on a phone the stacked row is as it was, products line included.

One registration with an ordinary name and one with the heaviest case (a long
double family name, a long component, a long e-mail address) are made for the
seeded member and removed again.

Red (each restored after): the two priorities taken off the columns → the
name is 76 px on the household's tab; the group row spanning its fixed seven
columns again → the columns no longer add up to the table; the stacked
products line left to the priority → it is gone on a phone.
"""

import os
import sys
from decimal import Decimal

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

ORDINARY = "Annemieke Vandenbroucke"
HEAVY = "Marie-Antoinette Vandenbroucke-Deschuymere"
COMPONENT = "Huisbezoek met nieuwjaarsreceptie"


@pytest.fixture(scope="module")
def world():
    """Two registrations of the seeded member for the seeded activity, in a
    component with a long name, each with a transfer still to make."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivitySubRegistration, Registration
    from app.domains.auth.api import login_person_for_email
    from app.domains.payment.api import PaymentRecord
    from seed_e2e import MARKER_EMAIL

    db = SessionLocal()
    try:
        person = login_person_for_email(db, MARKER_EMAIL)
        activity = db.query(Activity).filter(Activity.name == "E2E-activiteit").one()
        component = ActivitySubRegistration(
            activity_id=activity.id, name=COMPONENT, price=Decimal("0"), is_free=True
        )
        db.add(component)
        db.flush()
        made = {"component": component.id, "regs": [], "bookings": []}
        for number, (name, email) in enumerate(
            (
                (ORDINARY, "annemieke.vandenbroucke@example.com"),
                (HEAVY, "marie-antoinette.vandenbroucke-deschuymere@example.com"),
            )
        ):
            registration = Registration(
                activity_id=activity.id,
                component_id=component.id,
                person_id=person.id,
                registration_type="INDIVIDUAL",
                contact_name=name,
                contact_email=email,
                phone="0470 00 00 01",
            )
            db.add(registration)
            db.flush()
            booking = PaymentRecord(
                payable_type="registration",
                payable_id=registration.id,
                amount=Decimal("1250.00"),
                method="transfer",
                status="pending",
                structured_communication=f"+++174/100{number}/00096+++",
            )
            db.add(booking)
            db.flush()
            made["regs"].append(registration.id)
            made["bookings"].append(booking.id)
        db.commit()
        made["household"] = person.member_persons[0].member_id
        made["activity"] = activity.id
    finally:
        db.close()

    yield made

    db = SessionLocal()
    try:
        for model, ids in (
            (PaymentRecord, made["bookings"]),
            (Registration, made["regs"]),
            (ActivitySubRegistration, [made["component"]]),
        ):
            db.query(model).filter(model.id.in_(ids)).execution_options(
                include_all_tenants=True, include_deleted=True
            ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


TABLE = """(names) => { const r = e => e.getBoundingClientRect(), n = v => Math.round(v);
  const frame = document.querySelector('[data-table-frame]'), table = frame.querySelector('table');
  const lines = e => e ? Math.round(r(e).height / parseFloat(getComputedStyle(e).lineHeight)) : 0;
  const rows = [...table.querySelectorAll('tr[data-row]')];
  const one = name => { const row = rows.find(t => t.querySelector('[data-row-link]').textContent.trim() === name);
    const cell = row.querySelector('[data-cell="name"]');
    return {name: lines(cell.querySelector('[data-row-link]')), sub: lines(cell.querySelector('div')),
            height: n(r(row).height), products: row.querySelector('[data-cell="more"]').checkVisibility(),
            balance: row.querySelector('[data-cell="extra"]').checkVisibility()}; };
  const head = [...table.querySelectorAll('thead th')].filter(t => t.checkVisibility());
  const cells = [...table.querySelectorAll('td[data-cell="name"]')];
  return {frame: n(r(frame).width), table: n(r(table).width), stacked: getComputedStyle(table).display === 'block',
          columns: head.map(t => t.dataset.cell), widths: head.map(t => n(r(t).width)),
          total: n(head.reduce((sum, t) => sum + r(t).width, 0)),
          name_column: head.length ? n(r(head[0]).width) : 0,
          overflowing: cells.filter(c => c.scrollWidth > c.clientWidth + 1).length,
          ordinary: one(names[0]), heavy: one(names[1]),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""

TABS = ("household", "activity")


def _measure(browser, world, tab: str, width: int) -> dict:
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    url = {
        "household": f"/admin/leden/gezin/{world['household']}/inschrijvingen",
        "activity": f"/admin/activiteiten/{world['activity']}/inschrijvingen",
    }[tab]
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 1000})
    try:
        admin = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
        login_met_sessie(page, make_session_value(admin), BASE)
        page.goto(url)
        pagina_klaar(page)
        measured = page.evaluate(TABLE, [ORDINARY, HEAVY])
        print("MEASURE registration table", tab, width, measured)
        return measured
    finally:
        page.close()


@pytest.mark.parametrize("tab", TABS)
@pytest.mark.parametrize("width", [1090, 1100, 1440])
def test_a_name_has_room_wherever_the_table_is_a_table(browser, world, tab, width):
    m = _measure(browser, world, tab, width)
    assert not m["stacked"], m
    assert m["name_column"] >= 200, f"the name column is {m['name_column']} px"
    assert m["ordinary"]["name"] == 1, "an ordinary name breaks over two lines"
    if tab == "household":
        # The component of this file is a long one (33 letters): it may take a
        # second line between two words, never more.
        assert m["ordinary"]["sub"] <= 2, "the component breaks inside a word"
    assert m["heavy"]["name"] <= 3, m["heavy"]
    # The columns add up to the table: no column that no head names.
    assert abs(m["total"] - m["table"]) <= 2, (m["total"], m["table"], m["widths"])
    assert m["overflowing"] == 0 and m["page"][0] == m["page"][1], m
    # Producten leaves below 1 099 px of table width, Saldo below 979 px.
    assert m["ordinary"]["products"] is (m["frame"] >= 1100), (m["frame"], m["columns"])
    assert m["ordinary"]["balance"] is (m["frame"] >= 980), (m["frame"], m["columns"])
    assert ("more" in m["columns"]) is m["ordinary"]["products"]
    assert ("extra" in m["columns"]) is m["ordinary"]["balance"]


@pytest.mark.parametrize("tab", TABS)
def test_on_a_phone_the_stacked_row_keeps_its_products_line(browser, world, tab):
    m = _measure(browser, world, tab, 390)
    assert m["stacked"] and m["page"][0] == m["page"][1], m
    # Producten is an optional COLUMN; stacked, it is a line of the row and stays.
    assert m["ordinary"]["products"] and m["heavy"]["products"], m
    assert not m["ordinary"]["balance"], "the balance was never a line of the stacked row"
    # As it was before this change (measured on master: 249 and 217 px for the
    # heavy row of the household's and the activity's tab).
    assert m["heavy"]["height"] == (249 if tab == "household" else 217), m["heavy"]
