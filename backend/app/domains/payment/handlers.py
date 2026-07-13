"""Job-handlers van het payment-component (fase 3, #401 — §19.2).

``payment.reconcile``: wees-record-check op ``payable_type/payable_id``. Een
PaymentRecord dat naar een verdwenen registratie/lidmaatschap wijst is een
data-integriteitsprobleem: het faalt luid (ERROR-log) én wordt een
werkbank-taak, zodat het niet stil blijft liggen. De handler her-enqueuet
zichzelf dagelijks (periodiek werk = zelf-herplanning, §5.8).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.domains.payment.models import PaymentRecord
from app.kernel.jobs import enqueue, job

logger = logging.getLogger(__name__)

RECONCILE_INTERVAL = timedelta(hours=24)


def find_orphan_records(db: Session) -> list[PaymentRecord]:
    """PaymentRecords waarvan de payable niet (meer) bestaat. Soft-deleted
    payables gelden als bestaand — het financiële feit blijft verklaarbaar."""
    from app.models.activity import Registration
    from app.models.member import Membership

    orphans: list[PaymentRecord] = []
    records = db.query(PaymentRecord).all()
    # Inclusief soft-deleted payables (execution_options, zie app/soft_delete.py).
    reg_ids = {r for (r,) in db.query(Registration.id)
               .execution_options(include_deleted=True).all()}
    ms_ids = {m for (m,) in db.query(Membership.id)
              .execution_options(include_deleted=True).all()}
    for record in records:
        if record.payable_type == "registration" and record.payable_id not in reg_ids:
            orphans.append(record)
        elif record.payable_type == "membership" and record.payable_id not in ms_ids:
            orphans.append(record)
    return orphans


@job("payment.reconcile")
def reconcile_orphans(db: Session, payload: dict) -> None:
    from app.domains.workflow.api import create_task, open_tasks

    open_titles = {t.title for t in open_tasks(db, ["FINANCE", "ADMIN"])}
    for record in find_orphan_records(db):
        # Het volledige record-id zit in de titel — dat is meteen de
        # idempotentie-sleutel over runs heen (geen tweede open taak).
        title = (f"Wees-betaling {record.id}: {record.payable_type} "
                 f"#{record.payable_id} bestaat niet")
        if title in open_titles:
            continue
        logger.error("payment.reconcile: %s (bedrag %s, status %s)",
                     title, record.amount, record.status)
        create_task(
            db, kind="payment.wees_record", title=title,
            subject_type="payment_record", subject_id=record.payable_id,
            required_role="FINANCE",
        )
    if not payload.get("once"):
        enqueue(db, "payment.reconcile", {},
                run_at=datetime.now(timezone.utc) + RECONCILE_INTERVAL)
