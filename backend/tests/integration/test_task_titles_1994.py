"""#1994 — the Werkbank's other three task titles in words, and the sweep's key.

Since #1991 a refund task names its payment in words. The other three kinds
the sweep makes showed codes, ids, an address and English words:
"E-mail #<id> aan <recipient> definitief gefaald", "Webhook-mismatch:
gateway <id>… is paid, record <id>… is pending", "Job <code> (#<id>)
definitief gefaald: <error>". Koen, 14 October 2026, to "Mag ik voor v2.19
een issue schrijven om de drie andere taaktitels … in woorden te zetten?":
"2xja op v2.19" (brought onto v2.17 the same day, as the master CLI
reported).

Now each says what happened, its words from the code list where the fact
lives — the mail's kind from mail's list, the provider and our status from
payment's. A job has no Dutch word of its own; its title says what
happened and the list's second line names the job. No id, no address, no
error text.

A title in words need not be unique, so it can no longer be the sweep's
key: two pending refunds on one payable read alike since #1991, and the
second got no task. The key is the task's kind and subject.

Broken on purpose (14 October 2026), each put back by the reverse edit: the
old mail title back → the mail test red; the key back to the title → "the
second refund on one payable got no task"; the retitling taken out → the
three old open tasks keep their old titles.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domains.workflow.handlers import sweep
from app.domains.workflow.models import TaskStatus, WorkflowTask

pytestmark = pytest.mark.ui_agnostisch

MAIL = "E-mail (Lidmaatschap) niet afgeleverd"
MISMATCH = "Betaald volgens Mollie, hier in afwachting: nakijken"
JOB = "Achtergrondtaak definitief mislukt"


def _failed_mail(db):
    from app.domains.mail.api import EmailLog
    from app.kernel.jobs import KernelJob

    log = EmailLog(
        recipient="lid@voorbeeld.test",
        subject="Welkom",
        email_type="membership_confirmation",
        status="failed",
    )
    db.add(log)
    db.flush()
    db.add(
        KernelJob(
            name="mail.retry",
            payload={"email_log_id": log.id},
            status="failed",
            run_at=datetime.now(timezone.utc),
            last_error="SMTP refused",
        )
    )
    db.flush()
    return "email_log", str(log.id)


def _mismatch(db):
    from app.domains.payment.api import GatewayPayment, PaymentRecord

    gp = GatewayPayment(provider="mollie", amount=Decimal("10.00"), status="paid")
    db.add(gp)
    db.flush()
    record = PaymentRecord(
        payable_type="registration",
        payable_id=19941,
        amount=Decimal("10.00"),
        method="online",
        status="pending",
        gateway_payment_id=gp.id,
    )
    db.add(record)
    db.flush()
    return "payment_record", str(record.id)


def _failed_job(db):
    from app.kernel.jobs import KernelJob

    job = KernelJob(
        name="iets.anders",
        payload={},
        status="failed",
        run_at=datetime.now(timezone.utc),
        last_error="Boem: something broke",
    )
    db.add(job)
    db.flush()
    return "kernel_job", str(job.id)


KINDS = [
    ("mail.definitief_gefaald", _failed_mail, MAIL),
    ("payment.webhook_mismatch", _mismatch, MISMATCH),
    ("kernel.job_gefaald", _failed_job, JOB),
]


def _open(db, kind, subject_id):
    db.expire_all()
    return (
        db.query(WorkflowTask)
        .filter(
            WorkflowTask.kind == kind,
            WorkflowTask.subject_id == subject_id,
            WorkflowTask.status == TaskStatus.OPEN,
        )
        .all()
    )


@pytest.mark.parametrize(("kind", "make", "title"), KINDS)
def test_a_task_title_says_what_happened_in_words(db_session, kind, make, title):
    _subject_type, subject_id = make(db_session)
    sweep(db_session, {"once": True})
    db_session.flush()
    [task] = _open(db_session, kind, subject_id)
    assert task.title == title
    for old in ("#", "@", "Job ", "Webhook", "gateway", "paid", "Boem", "definitief gefaald"):
        assert old not in task.title, f"{old!r} in {task.title!r}"


@pytest.mark.parametrize(("kind", "make", "title"), KINDS)
def test_an_open_task_with_an_old_title_gets_the_new_one(db_session, kind, make, title):
    subject_type, subject_id = make(db_session)
    old = WorkflowTask(
        kind=kind,
        title=f"Een oude titel #{subject_id}",
        status="open",
        subject_type=subject_type,
        subject_id=subject_id,
        required_role="ADMIN" if kind != "payment.webhook_mismatch" else "FINANCE",
    )
    db_session.add(old)
    db_session.flush()
    old_id = old.id

    sweep(db_session, {"once": True})
    db_session.flush()
    assert [(t.id, t.title) for t in _open(db_session, kind, subject_id)] == [(old_id, title)]


def test_two_pending_refunds_on_one_payable_each_get_a_task(db_session):
    from app.domains.payment.api import PaymentRecord

    # The second refund comes after the first already has its task: under the
    # old key its title was "already there", and it got none.
    refunds = []
    for amount in ("-5.00", "-7.00"):
        record = PaymentRecord(
            payable_type="membership",
            payable_id=19942,
            amount=Decimal(amount),
            method="transfer",
            status="pending",
            type="refund",
        )
        db_session.add(record)
        db_session.flush()
        refunds.append(str(record.id))
        sweep(db_session, {"once": True})
        db_session.flush()
    tasks = [t for r in refunds for t in _open(db_session, "payment.refund_bevestigen", r)]
    assert len(tasks) == 2, "the second refund on one payable got no task"
    assert {t.title for t in tasks} == {"Terugbetaling lidmaatschap #19942 bevestigen"}

    # And a second round makes none more.
    sweep(db_session, {"once": True})
    db_session.flush()
    assert len([t for r in refunds for t in _open(db_session, "payment.refund_bevestigen", r)]) == 2
