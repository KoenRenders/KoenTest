"""#855 — a settled refund must leave the workbench without waiting for the clock.

Found by Koen during the v2.2.0 validation on HDEV, 10 September 2026. He opened a
refund from the workbench, marked it settled on the payment screen, and **the task
stayed**. Measured: settled around 21:40, the sweep had just run at 21:38 and the next
one was due at 22:38 — **fifty-eight minutes** of a task on screen for work already done.

**Why.** `vervroeg_sweep` was called from exactly one place, `create_refund`, and only
`if not settled`. That hook comes from #705 and solved the mirror-image complaint:
appearing was too slow. Resolving had no such hook, so disappearing still waited for the
hourly round.

**The fix is one call in `bevestig_betaling`**, which covers both cases Koen named:
`/bevestigen` (settling) and `/bijwerken` (writing off a charge, #617-2b) both pass
through that service.

**Not through the `PaymentSettled` kernel event**, however tidy that looks: it is
published from `apply_gateway_status`, the Mollie path. Manual confirmation never goes
there, so a listener would miss precisely the case reported — and a test written around
an online payment would stay green while it did. Correct on the diagram, wrong in
practice.

**Advance the sweep, do not close the task here.** The title is the idempotency key, and
a second place touching that key is how duplicate or prematurely closed tasks appear.

These tests assert on the SCHEDULED job, never on wall-clock waiting: the point is that
the round is brought forward, not that something eventually happens.

Broken on purpose to check that these tests can go red: removed the `vervroeg_sweep`
call from `bevestig_betaling` → three fall over (the two report cases plus the once=True
one, which then finds nothing scheduled at all); dropped `once=True` from `vervroeg_sweep`
→ only the fourth falls over, which is exactly the one guarding the hourly cadence.
"""
from decimal import Decimal

import pytest

from app.domains.payment.api import PaymentRecord
from app.domains.workflow.models import WorkflowTask

pytestmark = pytest.mark.ui_agnostisch

SWEEP_JOB = "workflow.sweep"


def _charge(db, *, amount="35.00", payable_id=4455):
    record = PaymentRecord(payable_type="registration", payable_id=payable_id,
                           type="charge", amount=Decimal(amount), method="transfer",
                           status="pending")
    db.add(record)
    db.flush()
    return record


def _scheduled_sweeps(db):
    from app.kernel.jobs import KernelJob

    return (db.query(KernelJob)
            .filter(KernelJob.name == SWEEP_JOB, KernelJob.status == "pending")
            .all())


def _run_scheduled_sweeps(db):
    """Run what is queued — that is what the hourly round would do, only sooner."""
    from app.domains.workflow.handlers import sweep

    jobs = _scheduled_sweeps(db)
    for job in jobs:
        sweep(db, job.payload or {})
        job.status = "done"
    db.commit()
    return jobs


def _open_refund_task(db, refund_id):
    return (db.query(WorkflowTask)
            .filter(WorkflowTask.kind == "payment.refund_bevestigen",
                    WorkflowTask.status == "open").all())


def test_settling_a_refund_brings_the_sweep_forward(db_session):
    """The reported case: settle it, and the task is gone in this round rather than the
    next hourly one."""
    from app.domains.payment.service import bevestig_betaling, registreer_terugbetaling

    charge = _charge(db_session)
    charge.status = "paid"
    charge.amount_paid = Decimal("35.00")
    db_session.flush()
    registreer_terugbetaling(db_session, charge.id, amount="10.00", actor="test")
    _run_scheduled_sweeps(db_session)
    refund = (db_session.query(PaymentRecord)
              .filter(PaymentRecord.type == "refund").one())
    assert _open_refund_task(db_session, refund.id), (
        "no refund task at all — then the rest of this test proves nothing (#678)")

    bevestig_betaling(db_session, refund.id, amount_paid="-10.00", actor="test")

    assert _scheduled_sweeps(db_session), (
        "settling scheduled no sweep, so the task waits for the hourly round — that is "
        "the fifty-eight minutes from this issue")
    _run_scheduled_sweeps(db_session)
    db_session.expire_all()
    assert not _open_refund_task(db_session, refund.id), (
        "the task is still open after the sweep it brought forward")


def test_writing_off_a_charge_brings_the_sweep_forward_too(db_session):
    """Koen's second case. It runs through the same service, and this test says so
    rather than assuming it."""
    from app.domains.payment.service import bevestig_betaling, registreer_terugbetaling

    charge = _charge(db_session, payable_id=4456)
    charge.status = "paid"
    charge.amount_paid = Decimal("35.00")
    db_session.flush()
    registreer_terugbetaling(db_session, charge.id, amount="5.00", actor="test")
    _run_scheduled_sweeps(db_session)
    refund = (db_session.query(PaymentRecord)
              .filter(PaymentRecord.type == "refund",
                      PaymentRecord.payable_id == 4456).one())

    # "Bewerken" writes off the amount through the same confirmation service.
    bevestig_betaling(db_session, refund.id, amount_paid="-5.00",
                      note="afgeboekt", actor="test")

    assert _scheduled_sweeps(db_session)


def test_advancing_twice_yields_no_second_task(db_session):
    """The title is the idempotency key. This is the test that rules out duplicate
    workbench tasks — the reason this hook advances the sweep instead of creating or
    closing anything itself."""
    from app.domains.workflow.api import vervroeg_sweep

    charge = _charge(db_session, payable_id=4457)
    charge.status = "paid"
    charge.amount_paid = Decimal("35.00")
    db_session.flush()
    from app.domains.payment.service import registreer_terugbetaling

    registreer_terugbetaling(db_session, charge.id, amount="7.00", actor="test")
    vervroeg_sweep(db_session)
    db_session.commit()

    _run_scheduled_sweeps(db_session)
    _run_scheduled_sweeps(db_session)

    db_session.expire_all()
    tasks = (db_session.query(WorkflowTask)
             .filter(WorkflowTask.kind == "payment.refund_bevestigen",
                     WorkflowTask.status == "open").all())
    assert len(tasks) == 1, f"{len(tasks)} tasks for one refund: {[t.title for t in tasks]}"


def test_the_advanced_sweep_schedules_no_successor(db_session):
    """What must not break: the hourly round stays exactly as it was.

    Every ordinary sweep schedules the next one. An advanced sweep does not (`once=True`),
    because there is already one waiting — without that flag the cadence would double
    permanently, and a doubling is the kind of thing nobody notices until the logs are
    full.
    """
    from app.domains.payment.service import bevestig_betaling, registreer_terugbetaling

    charge = _charge(db_session, payable_id=4458)
    charge.status = "paid"
    charge.amount_paid = Decimal("35.00")
    db_session.flush()
    registreer_terugbetaling(db_session, charge.id, amount="3.00", actor="test")
    _run_scheduled_sweeps(db_session)
    refund = (db_session.query(PaymentRecord)
              .filter(PaymentRecord.type == "refund",
                      PaymentRecord.payable_id == 4458).one())

    bevestig_betaling(db_session, refund.id, amount_paid="-3.00", actor="test")
    advanced = _scheduled_sweeps(db_session)
    assert advanced, "nothing was scheduled at all"
    assert all((job.payload or {}).get("once") for job in advanced), (
        "the advanced sweep is not marked once=True, so it schedules a successor and "
        "the hourly cadence doubles")

    _run_scheduled_sweeps(db_session)

    assert not _scheduled_sweeps(db_session), (
        "the advanced sweep left a successor behind")
