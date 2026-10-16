"""The history of a payment record: the snapshot that writes a row of
`payment.payment_record_history` (`docs/architecture.md` §5.8 — a history table per
component, written by its owner).

Moved here unchanged from `audit/service.py` (CR-13 phase 4c, #1251). The helper
only adds the row and never commits: the history row is committed in the same
transaction as the change it records. Call it before the caller's commit, and
before a delete, while the source can still be read.

#1885: declared here, written by the one snapshot (`kernel.logged.snapshot`),
which stores a code as its code (CR-12 §F4: a history table carries no foreign
key, it must survive a withdrawn code) for every column at once.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.domains.payment.models import PaymentRecord, PaymentRecordHistory
from app.kernel.logged import declare, snapshot

declare(PaymentRecord, PaymentRecordHistory, key="payment_record_id")


def snapshot_payment_record(
    db: Session, record, *, operation: str, action: str, source: str, actor: Optional[str] = None
) -> None:
    snapshot(
        db,
        record,
        operation=operation,
        action=action,
        source=source,
        actor=actor,
        model=PaymentRecord,
    )
