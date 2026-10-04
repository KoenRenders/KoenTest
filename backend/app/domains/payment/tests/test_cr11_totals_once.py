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

CR-11 pilot A, K1 (#1555; block 2, Koen, 2 October 2026): on /admin/betalingen
the tiles became three **key figures** in the title row, plain text — Netto te
betalen · Nog te ontvangen · Nog terug te betalen. The tile "Ontvangen" and the
counts of bookings under each amount are gone (the toolbar's count shows n). A
figure takes the `warning` tint only while its amount is open. The embedded
Betalingen tab of a record keeps its band until K6 (#1560).

Proven red on the figures: `warning` always set in the view → the two "in ink"
tests fail.
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


def _figures(html: str) -> dict[str, tuple[str, bool]]:
    """The key figures of the title row: label → (value, has the warning tint)."""
    head = html[html.index("data-list-head") : html.index("data-toolbar")]
    found = re.findall(
        r'<dd data-figure class="([^"]*)">([^<]*)</dd>\s*<dt data-figure-label[^>]*>([^<]*)</dt>',
        head,
    )
    return {label: (value, "text-brand-warning" in cls) for cls, value, label in found}


def test_the_screen_has_three_figures_and_the_totals_once(client, db_session):
    _add(db_session, "120", type_="charge", status="pending")
    _add(db_session, "-120", type_="refund", status="pending")
    _login_finance(client, db_session)
    html = client.get("/admin/betalingen").text

    # On the screen, not in a figure's `title` that repeats it (#1432).
    visible = re.sub(r'title="[^"]*"', "", html)
    assert visible.count("Netto") == 1, "the net amount stands more than once"
    assert "Financieel overzicht" not in html and "<tfoot" not in html
    assert "Nog af te handelen" not in html, "the combined tile is back"
    assert "kpi-strip" not in html, "the band of tiles is back beside the figures"
    figures = _figures(html)
    assert list(figures) == ["Netto te betalen", "Nog te ontvangen", "Nog terug te betalen"]
    # Two sides, never their net: € 120 to receive and € 120 to refund.
    assert figures["Nog te ontvangen"] == ("€ 120,00", True)
    assert figures["Nog terug te betalen"] == ("€ 120,00", True)
    assert figures["Netto te betalen"][1] is False, "the net is never tinted"


def test_nothing_open_shows_zero_on_both_figures_in_ink(client, db_session):
    _add(db_session, "20", type_="charge", status="paid", paid="20")
    _login_finance(client, db_session)
    figures = _figures(client.get("/admin/betalingen").text)
    assert figures["Nog te ontvangen"] == ("€ 0,00", False)
    assert figures["Nog terug te betalen"] == ("€ 0,00", False)


def test_only_the_open_side_takes_the_warning_tint(client, db_session):
    _add(db_session, "-9", type_="refund", status="pending")
    _login_finance(client, db_session)
    figures = _figures(client.get("/admin/betalingen").text)
    assert figures["Nog te ontvangen"] == ("€ 0,00", False)
    assert figures["Nog terug te betalen"] == ("€ 9,00", True)
