"""The history rows of a payment, recorded (CR-13 phase 4c, cut C5, #1251).

`snapshot_payment_record` moved from `audit/service.py` to payment, the owner of
`payment.payment_record_history` (`docs/architecture.md` §5.8: a history table
per component). The move changes no row: this test walks one payment through its
life and compares every history row, column by column, with what the code wrote
before the move. `EXPECTED` was recorded on the old code (9 October 2026, the
function still in `audit/service.py`) and has not been touched since.

Proven red (9 October 2026): `note=record.note` taken out of the snapshot → the
rows that carry a note differ, and the test shows the first row that does.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domains.payment.api import PayableType, PaymentRecordHistory
from app.domains.payment.service import (
    confirm_manual_payment,
    create_payment_record,
    create_refund,
    edit_payment_record,
    set_payment_status,
    void_payment_record,
)

pytestmark = pytest.mark.ui_agnostisch

ACTOR = "treasurer@example.org"

EXPECTED: list[tuple] = [
    (
        "charge",
        "insert",
        "payment_created",
        "admin_manual",
        "treasurer@example.org",
        "registration",
        770001,
        "30.00",
        "None",
        "transfer",
        "pending",
        "charge",
        None,
        None,
        None,
        False,
    ),
    (
        "charge",
        "update",
        "payment_manually_confirmed",
        "admin_manual",
        "treasurer@example.org",
        "registration",
        770001,
        "30.00",
        "30.00",
        "transfer",
        "paid",
        "charge",
        None,
        None,
        "seen on the statement",
        True,
    ),
    (
        "refund",
        "insert",
        "payment_refunded",
        "admin_manual",
        "treasurer@example.org",
        "registration",
        770001,
        "-10.00",
        "-10.00",
        "transfer",
        "paid",
        "refund",
        "charge",
        None,
        "one seat less",
        True,
    ),
    (
        "charge",
        "update",
        "payment_updated",
        "admin_update",
        "treasurer@example.org",
        "registration",
        770001,
        "30.00",
        "30.00",
        "transfer",
        "paid",
        "charge",
        None,
        None,
        "corrected note",
        True,
    ),
    (
        "other",
        "insert",
        "payment_created",
        "system",
        None,
        "registration",
        770002,
        "12.50",
        "None",
        "cash",
        "pending",
        "charge",
        None,
        None,
        None,
        False,
    ),
    (
        "other",
        "update",
        "payment_status_edited",
        "admin_manual",
        "treasurer@example.org",
        "registration",
        770002,
        "12.50",
        "12.50",
        "cash",
        "paid",
        "charge",
        None,
        None,
        "at the door",
        True,
    ),
    (
        "other",
        "delete",
        "payment_voided",
        "admin_manual",
        "treasurer@example.org",
        "registration",
        770002,
        "12.50",
        "12.50",
        "cash",
        "paid",
        "charge",
        None,
        None,
        "entered twice",
        True,
    ),
]


def _rows(db, labels: dict[str, str]) -> list[tuple]:
    """Every history row, oldest first, with the generated ids replaced by the
    label of the record they name and the moment reduced to "set or not"."""
    history = db.query(PaymentRecordHistory).order_by(PaymentRecordHistory.id).all()
    return [
        (
            labels[h.payment_record_id],
            h.operation,
            h.action,
            h.source,
            h.actor,
            h.payable_type,
            h.payable_id,
            str(h.amount),
            str(h.amount_paid),
            h.method,
            h.status,
            h.type,
            labels.get(h.refund_of_id, h.refund_of_id),
            h.gateway_payment_id,
            h.note,
            h.paid_at is not None,
        )
        for h in history
    ]


def test_the_history_rows_of_a_payments_life_are_what_they_were(db_session):
    db = db_session
    charge = create_payment_record(
        db,
        PayableType.REGISTRATION,
        770_001,
        Decimal("30.00"),
        "transfer",
        audit_source="admin_manual",
        audit_actor=ACTOR,
    )
    db.flush()
    confirm_manual_payment(
        db, charge.id, note="seen on the statement", actor=ACTOR, amount_paid=Decimal("30.00")
    )
    refund = create_refund(db, charge.id, Decimal("10.00"), note="one seat less", actor=ACTOR)
    edit_payment_record(db, charge.id, note="corrected note", actor=ACTOR)

    other = create_payment_record(db, PayableType.REGISTRATION, 770_002, Decimal("12.50"), "cash")
    db.flush()
    set_payment_status(db, other.id, "paid", actor=ACTOR, note="at the door")
    void_payment_record(db, other.id, actor=ACTOR, note="entered twice")
    db.flush()

    labels = {charge.id: "charge", refund.id: "refund", other.id: "other"}
    assert _rows(db, labels) == EXPECTED
