"""#1884 — a received amount equal to the full amount settles the payment.

Koen, on HDEV (10 October 2026): on a payment of € 47 by transfer he
registered a received amount of € 47 through "Bewerken" and saw "Deels
betaald"; only the button that confirms the payment made it "Vereffend".
`edit_payment_record` wrote the amount and left the status pending, and a
pending record with an amount reads "partial". More than a label: nothing
that belongs to "paid" happened — no event, so a membership stayed
inactive.

One rule: fully received is settled. An edit that brings the received
amount to the full amount takes the path of the confirmation
(`confirm_manual_payment` → `PaymentRecord.mark_paid`). A smaller amount
stays "partial" and publishes nothing. The same for a refund, with its sign.

Broken on purpose (14 October 2026), put back by the reverse edit: the new
branch in `edit_payment_record` taken out → the full-amount tests red
("partial" where "paid" is expected; no event; the membership inactive),
the smaller-amount test still green.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.auth.models import User, UserRole
from app.domains.mdm.api import Member
from app.domains.membership.api import Membership
from app.domains.payment.api import (
    PayableType,
    PaymentRecord,
    PaymentRecordHistory,
    PaymentType,
    edit_payment_record,
)
from app.kernel import events
from app.kernel.contracts.payment import PaymentReceived
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_agnostisch


@pytest.fixture
def received():
    seen: list[PaymentReceived] = []
    events.subscribe(PaymentReceived)(lambda event, db: seen.append(event))
    yield seen
    events._subscribers[PaymentReceived].pop()


def _record(db, amount: str, *, kind=PaymentType.CHARGE, **extra) -> PaymentRecord:
    record = PaymentRecord(
        payable_type=extra.pop("payable_type", PayableType.REGISTRATION),
        payable_id=extra.pop("payable_id", 18841),
        amount=Decimal(amount),
        method="transfer",
        status="pending",
        type=kind,
        **extra,
    )
    db.add(record)
    db.flush()
    return record


def _actions(db, record) -> list[str]:
    db.flush()  # the app's session does not flush on a read (#1771)
    return [
        h.action
        for h in db.query(PaymentRecordHistory)
        .filter(PaymentRecordHistory.payment_record_id == record.id)
        .order_by(PaymentRecordHistory.id)
    ]


def test_an_edit_to_the_full_amount_settles_the_payment(db_session, received):
    record = _record(db_session, "47.00")
    edit_payment_record(
        db_session, record.id, status="pending", amount_paid=Decimal("47.00"), actor="fin@test"
    )
    assert record.state() == "paid"
    assert [(e.payment_record_id, e.amount_booked, e.fully_paid) for e in received] == [
        (record.id, "47.00", True)
    ], "the event of a payment that came in, published once"
    assert _actions(db_session, record)[-1] == "payment_manually_confirmed"


def test_an_edit_to_the_full_amount_activates_a_membership(db_session):
    member = Member()
    db_session.add(member)
    db_session.flush()
    membership = Membership(member_id=member.id, year=2026, is_active=False)
    db_session.add(membership)
    db_session.flush()
    record = _record(
        db_session, "47.00", payable_type=PayableType.MEMBERSHIP, payable_id=membership.id
    )
    edit_payment_record(db_session, record.id, status="pending", amount_paid=Decimal("47.00"))
    assert membership.is_active, "a membership paid in full stays inactive"


def test_an_edit_to_a_smaller_amount_stays_partial_and_publishes_nothing(db_session, received):
    record = _record(db_session, "47.00")
    edit_payment_record(
        db_session, record.id, status="pending", amount_paid=Decimal("20.00"), actor="fin@test"
    )
    assert record.state() == "partial"
    assert received == []
    assert _actions(db_session, record)[-1] == "payment_updated"


def test_a_refund_paid_out_in_full_is_settled(db_session):
    charge = _record(db_session, "30.00", payable_id=18842)
    charge.amount_paid = Decimal("30.00")
    charge.status = "paid"
    refund = _record(
        db_session, "-10.00", kind=PaymentType.REFUND, payable_id=18842, refund_of_id=charge.id
    )
    assert refund.state() == "refund_due"
    edit_payment_record(db_session, refund.id, status="pending", amount_paid=Decimal("-10.00"))
    assert refund.state() == "paid"


def test_the_screen_s_edit_settles_a_full_amount(client, db_session):
    """As the form posts it: the status unchanged ("pending"), the amount typed."""
    user = db_session.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code.value == "FINANCE" for r in user.roles):
        db_session.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db_session.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    record = _record(db_session, "47.00", payable_id=18843)
    db_session.commit()

    answer = client.post(
        f"/admin/betalingen/{record.id}/bewerken",
        data={"status": "pending", "amount_paid": "47", "note": ""},
        headers={"X-CSRF-Token": csrf_token_for(value), "HX-Request": "true"},
    )
    assert answer.status_code == 200, answer.text[:300]
    db_session.expire_all()
    assert db_session.get(PaymentRecord, record.id).state() == "paid"
