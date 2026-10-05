"""What a renewal buys and costs is one rule (#1590): `membership.service.renewal_terms`.

The renewal page announces the price and the last day before the click; the
renewal itself books them. Both read this function, so they cannot differ. What
the rule says was written inside `renew_membership` until #1590 and is pinned
here for the first time:

- with cover, a renewal buys the whole year after the furthest cover, at the full
  price — whatever a membership bought today would cost;
- without cover, it buys what a new membership buys today, at today's price.

Proven red: the full-year price replaced by today's price → the covered
household is quoted the mid-year price; the target year not advanced past the
cover → the same year is quoted twice.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domains.membership.api import Membership, renewal_terms
from app.kernel.tenant_config import tenant_membership_config
from tests.conftest import create_test_family

TODAY = date(2031, 3, 15)
MID_YEAR_PRICE = Decimal("11.00")


@pytest.fixture
def today_costs_eleven(monkeypatch):
    """Today's price for a NEW membership, set apart from the full price so the two
    cannot be mistaken for each other."""
    from app.domains.payment import api as payment_api

    monkeypatch.setattr(payment_api, "membership_price_for_date", lambda *a, **k: MID_YEAR_PRICE)


def test_with_cover_a_renewal_buys_the_whole_next_year_at_the_full_price(
    db_session, today_costs_eleven
):
    member, person = create_test_family(db_session)
    db_session.add(
        Membership(
            member_id=member.id,
            year=TODAY.year,
            valid_from=date(TODAY.year, 1, 1),
            valid_to=date(TODAY.year, 12, 31),
            is_active=True,
        )
    )
    db_session.flush()
    db_session.refresh(person)
    full = tenant_membership_config(db_session)["price_full"]
    assert full != MID_YEAR_PRICE, "the two prices are equal — this test would prove nothing"

    valid_from, valid_to, amount = renewal_terms(db_session, person, TODAY)

    assert (valid_from, valid_to) == (date(TODAY.year + 1, 1, 1), date(TODAY.year + 1, 12, 31))
    assert amount == full


def test_without_cover_a_renewal_buys_what_a_new_membership_buys_today(
    db_session, today_costs_eleven
):
    from app.domains.payment.api import membership_valid_period

    _member, person = create_test_family(db_session)

    valid_from, valid_to, amount = renewal_terms(db_session, person, TODAY)

    assert (valid_from, valid_to) == membership_valid_period(TODAY)
    assert valid_from == TODAY, "a mid-year start — otherwise the full price would be right too"
    assert amount == MID_YEAR_PRICE
