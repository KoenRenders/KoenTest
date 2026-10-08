"""The history of a payment record: the snapshot that writes a row of
`payment.payment_record_history` (`docs/architecture.md` §5.8 — a history table per
component, written by its owner).

Moved here unchanged from `audit/service.py` (CR-13 phase 4c, #1251). The helper
only adds the row and never commits: the history row is committed in the same
transaction as the change it records. Call it before the caller's commit, and
before a delete, while the source can still be read.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.domains.payment.models import PaymentRecordHistory
from app.kernel.codes import code_of


def snapshot_payment_record(
    db: Session, record, *, operation: str, action: str, source: str, actor: Optional[str] = None
) -> None:
    # CR-12 §F4: a history table is append-only and carries NO foreign key —
    # it must survive a withdrawn code. That is why its columns stay plain
    # strings and the snapshot writes the code, not the member. `code_of` does
    # that for all four at once, so that no fifth place appears where someone
    # can forget `.value`.
    db.add(
        PaymentRecordHistory(
            payment_record_id=record.id,
            payable_type=code_of(record.payable_type),
            payable_id=record.payable_id,
            amount=record.amount,
            amount_paid=record.amount_paid,
            method=code_of(record.method),
            status=code_of(record.status),
            type=code_of(record.type),
            refund_of_id=record.refund_of_id,
            gateway_payment_id=record.gateway_payment_id,
            note=record.note,
            paid_at=record.paid_at,
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
    )
