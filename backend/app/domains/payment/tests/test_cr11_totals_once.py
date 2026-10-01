"""CR-11 W1 (#1391): the payment totals stand once, in the tiles.

The table's "Netto totaal" row and the "Financieel overzicht" block under the
list are gone; the third tile is "Nog af te handelen" and shows two sides —
to receive, to refund — side by side, never their net (CR-11 Q19): € 120 to
receive and € 120 to refund is two things to do, and a net € 0 reads as
nothing to do. Both zero: "€ 0,00" once.

Proven red: the tfoot put back → the "Netto" count is 2; `open_sides` summing
the signed balances (a net) → the 120/120 case says 0/0.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.payment.api import PaymentRecord, open_sides
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _record(amount, paid=None):
    """A bare record: no database round trip, so `open_sides` is all that runs."""
    return SimpleNamespace(
        amount=Decimal(amount), amount_paid=None if paid is None else Decimal(paid)
    )


def test_two_sides_that_would_net_to_zero_stay_two_amounts():
    sides = open_sides([_record("120"), _record("-120")])
    assert sides == {"to_receive": Decimal("120"), "to_refund": Decimal("120")}


def test_settled_records_leave_nothing_to_handle():
    sides = open_sides([_record("30", "30"), _record("-10", "-10")])
    assert sides == {"to_receive": Decimal("0"), "to_refund": Decimal("0")}


def test_an_overpaid_charge_is_money_to_go_back():
    assert open_sides([_record("18", "20")]) == {
        "to_receive": Decimal("0"),
        "to_refund": Decimal("2"),
    }


def _login_finance(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _add(db, amount, *, type_, status, paid=None):
    db.add(
        PaymentRecord(
            payable_type="membership",
            payable_id=1,
            type=type_,
            amount=Decimal(amount),
            amount_paid=None if paid is None else Decimal(paid),
            method="transfer",
            status=status,
        )
    )
    db.flush()


def test_the_screen_states_the_totals_once(client, db_session):
    _add(db_session, "120", type_="charge", status="pending")
    _add(db_session, "-120", type_="refund", status="pending")
    _login_finance(client, db_session)
    html = client.get("/admin/betalingen").text

    assert html.count("Netto") == 1, "the net amount stands more than once"
    assert "Financieel overzicht" not in html and "<tfoot" not in html
    tile = html[html.index("data-open-sides") :]
    tile = tile[: tile.index("</div>")]
    assert "te ontvangen" in tile and "terug te betalen" in tile
    assert (
        "text-orange-700"
        in html[html.index("Nog af te handelen") : html.index("data-open-sides") + 80]
    )


def _tile(to_receive, to_refund) -> str:
    from app.ui import templates

    kpi = {
        "due": Decimal("0"),
        "paid": Decimal("0"),
        "to_receive": Decimal(to_receive),
        "to_refund": Decimal(to_refund),
        "boekingen": 0,
        "open": 0,
    }
    html = templates.env.get_template("_bt_boven.html").render(
        scope=None, zicht="alle", zichten=[], kpi=kpi
    )
    block = html[html.index("Nog af te handelen") :]
    return block[: block.index("</div>", block.index("data-open-sides"))]


def test_nothing_open_shows_zero_once_and_stays_ink():
    tile = _tile("0", "0")
    assert tile.count("€ 0,00") == 1 and "te ontvangen" not in tile
    assert "text-orange-700" not in tile


def test_one_open_side_colours_the_tile():
    tile = _tile("0", "9")
    assert "text-orange-700" in tile and "€ 9,00" in tile and "€ 0,00" in tile
