"""CR-11 pilot A, K2 (#1556) — Betalingen on the kit's table.

Block 4 (Koen, 2 October 2026): the head sorts, the row is the way in, a row shows
one action and `⋯`, a group per registration stays together under a sort, Bedrag
is never coloured and a Saldo that is not zero always is, the optional columns
follow the column chooser through the URL, and the empty state names its cause.

The geometry — row height, the columns that leave by list width, the stacked
rows on a phone — is measured in a browser (`tests_e2e/test_betalingen_table.py`).

Proven red against the branch below it (the booking page, `c94b6144`): the list
has no `data-row-link`, no sort link and no `data-p1` — every test here fails.
On this branch, each rule broken on its own: the direction of a sort ignored →
the sort test fails; the sort link carrying `page` → the sort-state test fails;
`may_mutate` always true → the read-only test fails; an unknown column mode
passed through → the chooser test fails; and the kit's own breaks (a coloured
negative amount, delete in its place in the menu, `aria-sort` on every sortable
column) fail their test here as well as in `tests/test_table_kit.py`.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domains.activities.api import Registration
from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.payment.api import PaymentRecord
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _login(client, db, *, mutate: bool = True) -> None:
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if mutate and not db.query(UserRole).filter_by(user_id=user.id, role_code="FINANCE").first():
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
    if not mutate:
        db.query(UserRole).filter(
            UserRole.user_id == user.id, UserRole.role_code.in_(("FINANCE", "OPERATOR"))
        ).delete(synchronize_session=False)
    db.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _registration(db, name: str):
    activity, comp, _product = seed_activity_with_product(db, price="30.00")
    reg = Registration(
        contact_email="deelnemer@example.org",
        phone="0470000000",
        activity_id=activity.id,
        component_id=comp.id,
        registration_type="INDIVIDUAL",
        contact_name=name,
    )
    db.add(reg)
    db.flush()
    return reg, activity


def _record(db, reg, amount, *, status="pending", paid=None, minutes=0, **extra):
    rec = PaymentRecord(
        payable_type="registration",
        payable_id=reg.id,
        amount=Decimal(amount),
        amount_paid=None if paid is None else Decimal(paid),
        method="transfer",
        status=status,
        created_at=T0 + timedelta(minutes=minutes),
        **extra,
    )
    db.add(rec)
    db.flush()
    return rec


@pytest.fixture
def world(db_session):
    """Three registrations: Bram (open, the oldest), An (paid, with a refund still
    to pay out — two bookings), Cas (paid, the most recent)."""
    bram, _a = _registration(db_session, "Bram Voorbeeld")
    an, activity = _registration(db_session, "An Voorbeeld")
    cas, _c = _registration(db_session, "Cas Voorbeeld")
    r_bram = _record(db_session, bram, "30.00", minutes=1)
    r_an = _record(db_session, an, "50.00", status="paid", paid="50.00", minutes=2)
    r_refund = _record(db_session, an, "-10.00", minutes=3, type="refund", refund_of_id=r_an.id)
    r_cas = _record(db_session, cas, "20.00", status="paid", paid="20.00", minutes=4)
    db_session.commit()
    return {
        "bram": r_bram,
        "an": r_an,
        "refund": r_refund,
        "cas": r_cas,
        "activity": activity,
        "an_reg": an,
    }


def _rows(html: str) -> list[str]:
    return re.findall(r"<tr data-row.*?</tr>", html, re.S)


def _names(html: str) -> list[str]:
    return re.findall(r"data-row-link[^>]*>([^<]+)</a>", html)


def _row_of(html: str, rec) -> str:
    return next(r for r in _rows(html) if f'href="/admin/betalingen/{rec.id}?' in r)


def test_the_head_has_seven_columns_and_five_of_them_sort(client, db_session, world):
    _login(client, db_session)
    html = client.get("/admin/betalingen/lijst").text
    heads = re.findall(r"<th scope=\"col\".*?</th>", html, re.S)
    labels = [re.sub(r"<[^>]+>|\s+", " ", h).strip() for h in heads]
    assert labels == ["Boeking", "Context", "Status", "Bedrag", "Ontvangen", "Saldo", "Acties"]
    assert re.findall(r'data-sort="(\w+)"', html) == [
        "naam",
        "context",
        "status",
        "bedrag",
        "saldo",
    ]
    # Without a choice: most recent first, and no column says it sorts.
    assert "aria-sort" not in html
    assert _names(html) == ["Cas Voorbeeld", "An Voorbeeld", "An Voorbeeld", "Bram Voorbeeld"]
    # The meta line above the table is gone: the toolbar counts.
    assert "recentste eerst" not in html and "alleen FINANCE" not in html


def test_a_sort_orders_the_groups_and_a_group_stays_together(client, db_session, world):
    _login(client, db_session)

    by_name = client.get("/admin/betalingen/lijst?sort=naam").text
    assert _names(by_name) == ["An Voorbeeld", "An Voorbeeld", "Bram Voorbeeld", "Cas Voorbeeld"]
    assert 'aria-sort="ascending"' in by_name
    descending = client.get("/admin/betalingen/lijst?sort=-naam").text
    assert _names(descending) == ["Cas Voorbeeld", "Bram Voorbeeld", "An Voorbeeld", "An Voorbeeld"]
    # By amount, a group sorts on its MAIN row (An's € 50, not her refund of
    # − € 10), and the refund stays under it.
    by_amount = client.get("/admin/betalingen/lijst?sort=bedrag").text
    assert _names(by_amount) == ["Cas Voorbeeld", "Bram Voorbeeld", "An Voorbeeld", "An Voorbeeld"]
    rows = _rows(by_amount)
    assert "↳" in rows[3] and "↳" not in rows[2]
    # An unknown sort is the list's own order.
    assert (
        _names(client.get("/admin/betalingen/lijst?sort=geboortedatum").text)[0] == "Cas Voorbeeld"
    )


def test_a_sort_keeps_the_rest_of_the_state_and_goes_to_page_one(client, db_session, world):
    _login(client, db_session)
    html = client.get(
        "/admin/betalingen/lijst?zicht=openstaand&q=voorbeeld&per_page=25&page=2&sort=naam"
    ).text
    link = re.search(r'<a href="([^"]+)" hx-get="([^"]+)"[^>]*data-sort="naam"', html)
    page_url, fragment_url = (u.replace("&amp;", "&") for u in link.groups())
    # The active column toggles its direction.
    assert "sort=-naam" in fragment_url
    for piece in ("zicht=openstaand", "q=voorbeeld", "per_page=25"):
        assert piece in fragment_url and piece in page_url, piece
    assert "page=" not in fragment_url.replace("per_page=", ""), "a sort goes to page 1"
    assert fragment_url.startswith("/admin/betalingen/lijst?")
    assert page_url.startswith("/admin/betalingen?")
    # The sort is a field of the toolbar's form too, refreshed with the fragment.
    assert re.search(
        r'id="bt-filter-sort" name="sort" value="naam" data-sort-field hx-swap-oob', html
    )


def test_the_row_is_the_way_in_with_one_action_and_the_rest_under_the_menu(
    client, db_session, world
):
    _login(client, db_session)
    html = client.get("/admin/betalingen/lijst?zicht=alle&q=voorbeeld").text
    rows = _rows(html)
    assert len(rows) == 4

    # Each row has one link of its own, to the booking's page, with the list as
    # its way back.
    for rec in (world["bram"], world["an"], world["refund"], world["cas"]):
        row = _row_of(html, rec)
        assert row.count("data-row-link") == 1
        assert (
            f'href="/admin/betalingen/{rec.id}?terug=/admin/betalingen%3Fzicht%3Dalle%26q%3Dvoorbeeld"'
            in row
        )
    # At most one visible action per row: Bevestig where the booking is open.
    assert [r.count("data-row-action") for r in rows] == [0, 0, 1, 1]
    assert "Bevestig" in _row_of(html, world["bram"]) and "Bevestig" in _row_of(
        html, world["refund"]
    )
    assert "Bevestig" not in _row_of(html, world["cas"])
    # No "Bewerken", no unfold.
    assert "Bewerken" not in html and "x-show" not in "".join(
        r.split("data-row-menu")[0] for r in rows
    )

    paid = _row_of(html, world["an"])
    menu = paid[
        paid.index("data-row-menu ") if "data-row-menu " in paid else paid.index('role="menu"') :
    ]
    assert menu.index("Terugbetaling") < menu.index("Inschrijving openen")
    assert f'href="/admin/betalingen/{world["an"].id}?terug=' in menu and "#terugbetaling" in menu
    open_row = _row_of(html, world["bram"])
    assert "Terugbetaling" not in open_row.split('role="menu"')[1], "a refund on an unpaid booking"
    # Delete last, red, after a divider — on the refund, which may be deleted.
    refund_menu = _row_of(html, world["refund"]).split('role="menu"')[1]
    assert refund_menu.index("data-menu-divider") < refund_menu.index("Verwijderen")
    assert "text-red-700" in refund_menu[refund_menu.index("data-menu-divider") :]


def test_amounts_are_not_coloured_and_a_balance_that_is_not_zero_is(client, db_session, world):
    _login(client, db_session)
    html = client.get("/admin/betalingen/lijst").text

    def cell(row: str, marker: str) -> str:
        start = row.index(marker)
        return row[start : row.index("</td>", start)]

    refund = _row_of(html, world["refund"])
    assert "↳" in refund and "Terugbetaling ·" in refund
    amount = cell(refund, "data-amount")
    assert "− € 10,00" in amount, "a refund is a negative amount, the sign before the euro sign"
    assert not re.search(r"text-(red|orange|teal|green|brand)", amount), "Bedrag is coloured"
    assert "text-brand-warning" in cell(refund, "data-balance"), "a negative balance has no warning"
    assert "text-brand-warning" in cell(_row_of(html, world["bram"]), "data-balance")
    settled = cell(_row_of(html, world["cas"]), "data-balance")
    assert "€ 0,00" in settled and "text-brand-warning" not in settled
    # The status is a badge; the row itself carries no colour.
    for row in _rows(html):
        assert not re.search(r'<tr data-row class="[^"]*(bg-|text-(red|orange|green))', row)

    # One sum row, under the registration with two bookings: 50 − 10 due, 50 in,
    # − 10 still to move.
    sums = re.findall(r"<tr data-sum.*?</tr>", html, re.S)
    assert len(sums) == 1 and "Totaal inschrijving" in sums[0]
    assert "€ 40,00" in sums[0] and "text-brand-warning" in cell(sums[0], "data-balance")
    assert "<tfoot" not in html


def test_the_context_is_a_jump_link_that_leads_back_to_the_booking(client, db_session, world):
    _login(client, db_session)
    html = client.get("/admin/betalingen/lijst?zicht=alle").text
    row = _row_of(html, world["an"])
    link = re.search(r'<a href="([^"]+)" data-reference', row)
    assert link, "the context is plain text"
    href = link.group(1).replace("&amp;", "&")
    assert href.startswith(f"/admin/activiteiten/{world['activity'].id}?terug=")
    assert f"boeking%3D{world['an'].id}" in href

    activity_page = client.get(href)
    assert activity_page.status_code == 200
    back = re.search(r'<a data-way-back href="([^"]+)"[^>]*>(.*?)</a>', activity_page.text, re.S)
    assert "Betaling van An Voorbeeld" in re.sub(r"<[^>]+>", "", back.group(2))
    assert (
        back.group(1).replace("&amp;", "&")
        == f"/admin/betalingen?zicht=alle&boeking={world['an'].id}"
    )


def test_the_column_chooser_makes_a_round_trip_through_the_url(client, db_session, world):
    _login(client, db_session)
    page = client.get("/admin/betalingen?kol_ontvangen=hide&kol_context=show&sort=naam").text
    assert 'data-p1="hide"' in page and 'data-p2="show"' in page
    chooser = page[page.index("data-columns-chooser") :]
    assert re.search(r'name="kol_ontvangen".*?<option value="hide" selected>', chooser, re.S)
    assert re.search(r'name="kol_context".*?<option value="show" selected>', chooser, re.S)
    # Whatever the list links to itself carries the choice: a sort, the pager.
    sort_link = re.search(r'hx-get="([^"]+)"[^>]*data-sort="bedrag"', page).group(1)
    assert "kol_ontvangen=hide" in sort_link and "kol_context=show" in sort_link

    plain = client.get("/admin/betalingen").text
    assert 'data-p1="auto"' in plain and 'data-p2="auto"' in plain
    odd = client.get("/admin/betalingen?kol_ontvangen=altijd").text
    assert 'data-p1="auto"' in odd, "an unknown mode reached the table"


def test_the_empty_state_names_its_cause(client, db_session, world):
    _login(client, db_session)
    searched = client.get("/admin/betalingen/lijst?q=zzz-geen-treffer").text
    assert "Geen betalingen gevonden voor “zzz-geen-treffer”." in searched
    assert re.search(r'id="bt-filter-count"[^>]*>\s*0–0 van 0\s*<', searched)
    assert "data-table-frame" not in searched

    for rec in (world["bram"], world["refund"]):
        db_session.delete(db_session.get(PaymentRecord, rec.id))
    db_session.commit()
    assert (
        "Geen openstaande betalingen."
        in client.get("/admin/betalingen/lijst?zicht=openstaand").text
    )


def test_who_may_not_change_payments_gets_no_action_and_no_delete(client, db_session, world):
    _login(client, db_session, mutate=False)
    html = client.get("/admin/betalingen/lijst").text
    assert len(_rows(html)) == 4
    assert "data-row-action" not in html and "Bevestig" not in html
    assert "Verwijderen" not in html and "#terugbetaling" not in html
    # What is left under ⋯ is the way to the registration; the row still opens.
    assert html.count("Inschrijving openen") == 4 and html.count("data-row-link") == 4
