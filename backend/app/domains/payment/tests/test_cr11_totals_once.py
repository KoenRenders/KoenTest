"""CR-11 W1 (#1391): the payment totals stand once, in the tiles.

The table's "Netto totaal" row and the "Financieel overzicht" block under the
list are gone. What is still open is two tiles — "Nog te ontvangen" and "Nog
terug te betalen" (Koen at the validation, 1 October 2026; before that it was
one tile "Nog af te handelen" with both amounts) — each one amount the size of
the other tiles and its own number of bookings, never their net (CR-11 Q19):
€ 120 to receive and € 120 to refund is two things to do, and a net € 0 reads
as nothing to do. Nothing open: € 0,00.

Proven red: the tfoot put back → the "Netto" count is 2; `open_sides` summing
the signed balances (a net) → the 120/120 case says 0/0; the old single tile
put back → the four-tile test fails.
"""

import re
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


def _sides(receive, refund, receive_count, refund_count):
    return {
        "to_receive": Decimal(receive),
        "to_refund": Decimal(refund),
        "receive_count": receive_count,
        "refund_count": refund_count,
    }


def test_two_sides_that_would_net_to_zero_stay_two_amounts():
    assert open_sides([_record("120"), _record("-120")]) == _sides("120", "120", 1, 1)


def test_settled_records_leave_nothing_to_handle():
    assert open_sides([_record("30", "30"), _record("-10", "-10")]) == _sides("0", "0", 0, 0)


def test_an_overpaid_charge_is_money_to_go_back():
    assert open_sides([_record("18", "20")]) == _sides("0", "2", 0, 1)


def test_each_side_counts_its_own_bookings():
    records = [_record("10"), _record("5", "2"), _record("-4"), _record("7", "7")]
    assert open_sides(records) == _sides("13", "4", 2, 1)


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


def _tile(html: str, side: str) -> str:
    block = html[html.index(f'data-open-side="{side}"') :]
    return block[: block.index("</div>\n  </div>")]


def test_the_screen_has_four_tiles_and_the_totals_once(client, db_session):
    _add(db_session, "120", type_="charge", status="pending")
    _add(db_session, "-120", type_="refund", status="pending")
    _login_finance(client, db_session)
    html = client.get("/admin/betalingen").text

    # On the screen, not in a tile label's `title` that repeats it (#1432).
    visible = re.sub(r'title="[^"]*"', "", html)
    assert visible.count("Netto") == 1, "the net amount stands more than once"
    assert "Financieel overzicht" not in html and "<tfoot" not in html
    assert "Nog af te handelen" not in html, "the combined tile is back"
    for label in ("Netto te betalen", "Ontvangen", "Nog te ontvangen", "Nog terug te betalen"):
        assert label in html, label
    for side in ("receive", "refund"):
        tile = _tile(html, side)
        assert len(re.findall(r"€ [\d.,-]+", tile)) == 1, f"{side}: not one amount"
        assert "boekingen" in tile, f"{side}: no count of bookings"
        assert "text-orange-700" in tile, f"{side}: open but not orange"


def _render(**kpi) -> str:
    from app.ui import templates

    base = {"due": Decimal("0"), "paid": Decimal("0"), "boekingen": 0}
    return templates.env.get_template("_bt_boven.html").render(
        scope=None, zicht="alle", zichten=[], kpi={**base, **kpi}
    )


def test_nothing_open_shows_zero_on_both_tiles_in_ink():
    html = _render(**_sides("0", "0", 0, 0))
    for side in ("receive", "refund"):
        tile = _tile(html, side)
        assert "€ 0,00" in tile and "0 boekingen" in tile
        assert "text-orange-700" not in tile


def test_only_the_open_side_turns_orange():
    html = _render(**_sides("0", "9", 0, 2))
    assert "text-orange-700" not in _tile(html, "receive")
    refund = _tile(html, "refund")
    assert "text-orange-700" in refund and "€ 9,00" in refund and "2 boekingen" in refund
