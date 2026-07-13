"""Fase 3 (#401): payment-component — PaymentSettled-event, idempotente
webhook-afhandeling en de wees-record-reconciliatie (§19.2)."""
from decimal import Decimal

from app.domains.payment.api import GatewayPayment, PaymentRecord, handle_gateway_update
from app.domains.payment.handlers import find_orphan_records, reconcile_orphans
from app.domains.workflow.models import WorkflowTask
from app.kernel.contracts.payment import PaymentSettled
from app.kernel.events import subscribe, _subscribers


def _gateway_payment(db, amount="10.00"):
    gp = GatewayPayment(provider="mollie", provider_payment_id="tr_x", amount=Decimal(amount))
    db.add(gp)
    db.flush()
    return gp


def _record(db, gp=None, payable_type="registration", payable_id=999_999, amount="10.00"):
    rec = PaymentRecord(payable_type=payable_type, payable_id=payable_id,
                        amount=Decimal(amount), method="online",
                        gateway_payment_id=gp.id if gp else None)
    db.add(rec)
    db.flush()
    return rec


def test_payment_settled_published_once_for_repeated_webhook(db_session):
    seen = []

    def _handler(event, db):
        seen.append(event)

    subscribe(PaymentSettled)(_handler)
    try:
        gp = _gateway_payment(db_session)
        rec = _record(db_session, gp)
        handle_gateway_update(db_session, gateway_payment_id=gp.id, new_status="paid")
        # Herhaalde webhook: no-op — geen tweede event, paid_at blijft staan.
        eerste_paid_at = rec.paid_at
        handle_gateway_update(db_session, gateway_payment_id=gp.id, new_status="paid")
        assert len(seen) == 1
        assert seen[0].payment_record_id == rec.id and seen[0].amount == "10.00"
        assert rec.paid_at == eerste_paid_at and rec.amount_paid == Decimal("10.00")
    finally:
        _subscribers[PaymentSettled].remove(_handler)


def test_orphan_detection_and_workbench_task(db_session):
    wees = _record(db_session, payable_type="registration", payable_id=987_654_321)
    orphans = find_orphan_records(db_session)
    assert wees in orphans

    before = db_session.query(WorkflowTask).count()
    reconcile_orphans(db_session, {"once": True})
    tasks = (db_session.query(WorkflowTask)
             .filter(WorkflowTask.kind == "payment.wees_record").all())
    assert any(wees.id in t.title for t in tasks)
    assert all(t.required_role == "FINANCE" for t in tasks)

    # Idempotent: nogmaals draaien maakt geen tweede taak voor hetzelfde record.
    reconcile_orphans(db_session, {"once": True})
    assert db_session.query(WorkflowTask).count() == before + len(tasks)


def test_reconcile_reschedules_itself(db_session):
    from app.kernel.jobs import KernelJob

    reconcile_orphans(db_session, {})
    job = (db_session.query(KernelJob)
           .filter(KernelJob.name == "payment.reconcile")
           .order_by(KernelJob.id.desc()).first())
    assert job is not None and job.status == "pending"
