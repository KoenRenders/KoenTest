"""CR-13 phase 3 (#1250): a membership's period, at its addresses.

- `Membership.check()`: a membership cannot end before it begins — on every flush,
  through the listener, without a call site;
- `ck_memberships_valid_period` (migration 172): the same, at rest;
- `Membership.valid_on(day)`: active, and the day within the period — the one
  answer to the member-price question that `valid_membership_until` now asks.

Broken on purpose to check these tests can go red (run, then restored), each
additively, with what failed: `return` as the first line of `Membership.check()` →
the flush test alone (the database test stays green: the two are independent);
`return True` as the first line of `valid_on` → four: after the period, before it,
inactive, and without dates.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domains.mdm.api import Member
from app.domains.membership.api import Membership
from app.domains.membership.models import MembershipError

pytestmark = pytest.mark.ui_agnostisch


def _membership(db, **values) -> Membership:
    household = Member()
    db.add(household)
    db.flush()
    membership = Membership(member_id=household.id, year=2026, is_active=True, **values)
    db.add(membership)
    return membership


def test_a_membership_that_ends_before_it_begins_is_refused_on_flush(db_session):
    _membership(db_session, valid_from=date(2026, 6, 1), valid_to=date(2026, 5, 31))
    with pytest.raises(MembershipError):
        db_session.flush()


def test_a_membership_without_dates_is_fine(db_session):
    """The import writes one; the rule speaks only when both ends are there."""
    _membership(db_session, valid_from=None, valid_to=None)
    db_session.flush()


def test_a_membership_of_one_day_is_fine(db_session):
    _membership(db_session, valid_from=date(2026, 6, 1), valid_to=date(2026, 6, 1))
    db_session.flush()


def test_the_database_refuses_it_too(db_session):
    membership = _membership(db_session, valid_from=date(2026, 1, 1), valid_to=date(2026, 12, 31))
    db_session.flush()
    with pytest.raises(IntegrityError, match="ck_memberships_valid_period"):
        with db_session.begin_nested():
            db_session.execute(
                text("UPDATE membership.memberships SET valid_to = '2025-12-31' WHERE id = :id"),
                {"id": membership.id},
            )


@pytest.mark.parametrize(
    "active, day, expected",
    [
        (True, date(2026, 1, 1), True),
        (True, date(2026, 12, 31), True),
        (True, date(2027, 1, 1), False),
        (True, date(2025, 12, 31), False),
        (False, date(2026, 6, 1), False),
    ],
)
def test_valid_on_is_active_and_within_the_period(active, day, expected):
    """Built in memory, no database round trip: `valid_on` reads its own fields."""
    membership = Membership(
        year=2026, is_active=active, valid_from=date(2026, 1, 1), valid_to=date(2026, 12, 31)
    )
    assert membership.valid_on(day) is expected


def test_valid_on_without_dates_is_never_valid():
    assert Membership(year=2026, is_active=True).valid_on(date(2026, 6, 1)) is False
