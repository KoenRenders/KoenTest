"""The day of a moment is its Brussels day: the payment export and the member price (#2065).

Between 00:00 and 02:00 Brussels (01:00 in winter) the UTC day is still the day
before. Two places that decide money took the UTC day: the date a payment shows in
the export, and the day on which a registration's member price is measured.

Red before the change (16 October 2026, each case on the code of master):
- a payment settled at 00:30 Brussels on 1 August (22:30 UTC on 31 July) showed
  `2026-07-31` in the export, so a month file cut on that column put it in July;
- a registration made at 00:30 Brussels on the first day of a membership (22:30 UTC
  the day before) was priced as a non-member, and one made at 00:30 Brussels on the
  day after the membership ended was still priced as a member.
"""

from __future__ import annotations

import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import pytest

from app.domains.activities.totals import compute_registration_total
from app.domains.payment.api import PaymentRecord
from app.domains.payment.exports import build_payments_export_ods
from app.kernel.clock import BELGIUM, belgian_day

pytestmark = pytest.mark.ui_serverrendered


def _brussels(year, month, day, hour, minute) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=BELGIUM).astimezone(timezone.utc)


def test_the_day_of_a_moment_is_the_brussels_day():
    # Summer: UTC+2, so 00:30 is still the day before in UTC.
    assert belgian_day(_brussels(2026, 8, 1, 0, 30)) == date(2026, 8, 1)
    assert _brussels(2026, 8, 1, 0, 30).date() == date(2026, 7, 31)
    # Winter: UTC+1.
    assert belgian_day(_brussels(2026, 12, 1, 0, 30)) == date(2026, 12, 1)
    assert belgian_day(_brussels(2026, 12, 1, 23, 30)) == date(2026, 12, 1)
    with pytest.raises(ValueError):
        belgian_day(datetime(2026, 8, 1, 0, 30))


def test_a_payment_at_half_past_midnight_is_in_that_months_export(db_session):
    db_session.add(
        PaymentRecord(
            payable_type="registration",
            payable_id=9101,
            amount=Decimal("12.00"),
            amount_paid=Decimal("12.00"),
            method="online",
            status="paid",
            type="charge",
            paid_at=_brussels(2026, 8, 1, 0, 30),
        )
    )
    db_session.flush()
    ods = build_payments_export_ods(db_session)
    with zipfile.ZipFile(BytesIO(ods)) as zf:
        content = zf.read("content.xml").decode()
    assert "2026-08-01" in content
    assert "2026-07-31" not in content


def _person_with_membership(valid_from: date, valid_to: date):
    membership = SimpleNamespace(
        valid_to=valid_to, valid_on=lambda day: valid_from <= day <= valid_to
    )
    member = SimpleNamespace(memberships=[membership])
    return SimpleNamespace(member_persons=[SimpleNamespace(member=member)])


def _registration(registered_at: datetime, person):
    product = SimpleNamespace(
        name="Ticket",
        price=Decimal("10.00"),
        member_price=Decimal("6.00"),
        is_free=False,
        pay_on_site=False,
    )
    item = SimpleNamespace(product=product, quantity=1)
    return SimpleNamespace(registered_at=registered_at, person=person, items=[item])


def test_the_member_price_is_measured_on_the_brussels_day():
    first = date(2026, 8, 1)
    person = _person_with_membership(first, first + timedelta(days=30))
    # The first day of the membership, 00:30 Brussels: a member.
    total, _ = compute_registration_total(_registration(_brussels(2026, 8, 1, 0, 30), person))
    assert total == Decimal("6.00")
    # The day after it ended, 00:30 Brussels: no longer a member.
    last = first + timedelta(days=30)
    after = datetime(last.year, last.month, last.day, 0, 30, tzinfo=BELGIUM) + timedelta(days=1)
    total, _ = compute_registration_total(_registration(after.astimezone(timezone.utc), person))
    assert total == Decimal("10.00")
