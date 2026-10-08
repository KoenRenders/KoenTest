"""Own words for a first membership (#1730; Koen, 8 October 2026).

The Lidmaatschap card told a first membership from no renewal: every open
membership payment was a "vernieuwing", also for a household that never was a
paid member. Now:

- **a household without a paid membership** reads "Aanmelding geregistreerd —
  betaal via overschrijving:" on its transfer block, and "Lidmaatschap betalen"
  on the way to a (new) payment — also when its first payment failed;
- **a household that has had a paid membership** keeps "Vernieuwing
  geregistreerd …" and "Lidmaatschap vernieuwen";
- the distinction is the service's (`membership.is_first_membership`), computed
  once; the landing page shows the same card with the same words.

Red (each restored after): `is_first_membership` returning False always → the
first household reads "Vernieuwing" and "vernieuwen"; returning True always →
the renewing household reads "Aanmelding" and "betalen"; the `first=` taken off
the call in `membership_card` → the transfer block says "Vernieuwing" for a
first membership while the button says "betalen".
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.membership.api import Membership, is_first_membership
from app.domains.payment.api import PaymentRecord
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

HOUSEHOLD = "/leden/gezin"
FIRST = "Aanmelding geregistreerd — betaal via overschrijving:"
RENEWAL = "Vernieuwing geregistreerd — betaal via overschrijving:"
PAY = "Lidmaatschap betalen"
RENEW = "Lidmaatschap vernieuwen"


def _card(html: str) -> str:
    start = html.index("data-membership-status")
    return html[start : html.index("</section>", start)]


def _sign_in(client, email: str) -> None:
    client.cookies.set(SESSION_COOKIE, make_session_value(email))


def _membership(db, member, *, year: int, paid: bool, method="transfer", status="pending"):
    """A membership of `year`: paid (active, no open booking), or waiting for
    its payment with a booking in `status`."""
    membership = Membership(
        member_id=member.id,
        year=year,
        is_active=paid,
        valid_from=date(year, 1, 1),
        valid_to=date(year, 12, 31),
    )
    db.add(membership)
    db.flush()
    if not paid:
        db.add(
            PaymentRecord(
                payable_type="membership",
                payable_id=membership.id,
                amount=Decimal("35.00"),
                method=method,
                status=status,
                structured_communication="+++173/0000/00173+++",
            )
        )
    db.commit()
    return membership


def test_the_service_tells_a_first_membership_from_a_renewal(db_session):
    never, _p = create_test_family(db_session, email="nooit-1730@example.org")
    assert is_first_membership(db_session, never)
    _membership(db_session, never, year=date.today().year, paid=False)
    assert is_first_membership(db_session, never), "a membership that waits is not a paid one"
    before, _q = create_test_family(db_session, email="vroeger-1730@example.org")
    _membership(db_session, before, year=date.today().year - 2, paid=True)
    assert not is_first_membership(db_session, before), "an expired paid membership counts"


def test_a_first_membership_by_transfer_says_aanmelding(client, db_session):
    member, _person = create_test_family(db_session, email="eerste-1730@example.org")
    _membership(db_session, member, year=date.today().year, paid=False)
    _sign_in(client, "eerste-1730@example.org")
    card = _card(client.get(HOUSEHOLD).text)
    assert FIRST in card and RENEWAL not in card
    assert "+++173/0000/00173+++" in card and "35,00" in card
    # The landing page shows the same card, with the same words.
    landing = _card(client.get("/mijn").text)
    assert FIRST in landing and RENEWAL not in landing


def test_a_first_membership_with_an_open_online_payment_has_no_renewal_button(client, db_session):
    member, _person = create_test_family(db_session, email="online-1730@example.org")
    _membership(db_session, member, year=date.today().year, paid=False, method="online")
    _sign_in(client, "online-1730@example.org")
    card = _card(client.get(HOUSEHOLD).text)
    assert "data-renewal-online" in card
    assert RENEW not in card and PAY not in card, "a second payment is offered while one runs"


def test_a_first_payment_that_failed_offers_lidmaatschap_betalen(client, db_session):
    member, _person = create_test_family(db_session, email="mislukt-1730@example.org")
    _membership(
        db_session, member, year=date.today().year, paid=False, method="online", status="failed"
    )
    _sign_in(client, "mislukt-1730@example.org")
    card = _card(client.get(HOUSEHOLD).text)
    assert f">{PAY}</a>" in card.replace("\n", "") or PAY in card
    assert RENEW not in card
    assert 'href="/leden/gezin/vernieuwen"' in card


def test_a_household_that_was_a_paid_member_keeps_vernieuwen(client, db_session):
    member, _person = create_test_family(db_session, email="lid-1730@example.org")
    _membership(db_session, member, year=date.today().year - 1, paid=True)
    _sign_in(client, "lid-1730@example.org")
    card = _card(client.get(HOUSEHOLD).text)
    assert RENEW in card and PAY not in card

    _membership(db_session, member, year=date.today().year, paid=False)
    running = _card(client.get(HOUSEHOLD).text)
    assert RENEWAL in running and FIRST not in running
