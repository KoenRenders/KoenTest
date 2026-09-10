"""#822 — signpost or workplace, and the way to the subject.

Koen's rule, 10 September 2026: *"marking a payment 'handled' from its workbench record
is pointless"*, and *"handling a message is a workflow action that does belong in the
workbench, same for those mails and the kernel job."*

So: **if the entity has its own screen with its own actions, the workbench is a
SIGNPOST. If all you can do is judge it and note it down, the workbench IS the
WORKPLACE.**

On a webhook mismatch that is sharpest: the fix is to re-fetch the status from Mollie,
and that button lives on the payment screen. Being able to tick "Handled" here would
hide that the money is still not booked.

**The split hangs on the SUBJECT and not on the task kind**, so that a new payment task
automatically gets the right shape. It cuts straight across `SWEEP_SOORTEN`:
`mail.definitief_gefaald` and `kernel.job_gefaald` close themselves AND remain
workplaces. Those are two independent properties, and an earlier design of this issue
lumped them together.

**The way to the subject is the real reason this issue exists.** Of the four subject
types exactly one had a link (`payment_record`); for three of the five task kinds you
read the title and went looking.

`kernel_job` deliberately gets no link: there is no screen for it. Instead of a button
to a page where the job is not, the detail rows show its name, status, attempts and
last error. A dead reference is worse than none — see #811, where six of them broke at
once.

Broken on purpose to check that these tests can go red: removed `payment_record` from
`SUBJECTS_WITH_OWN_SCREEN` → the first two fall over; made `_subject_url` return `None`
→ the link tests fall over.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.payment.api import PaymentRecord
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _task(db, kind: str, subject_type: str, subject_id: str):
    from app.domains.workflow.api import create_task

    task = create_task(db, kind=kind, title=f"test {kind}",
                       subject_type=subject_type, subject_id=subject_id,
                       required_role="FINANCE")
    db.flush()
    return task


def _detail(client, task):
    return client.get(f"/admin/werkbank/taken/{task.id}",
                      headers={"HX-Request": "true"}).text


def _payment_record(db):
    record = PaymentRecord(payable_type="registration", payable_id=8221,
                           type="charge", amount=Decimal("10.00"), method="transfer",
                           status="pending", created_at=datetime.now(timezone.utc))
    db.add(record)
    db.flush()
    return record


@pytest.mark.parametrize("kind", ["payment.refund_bevestigen",
                                  "payment.webhook_mismatch"])
def test_a_payment_task_is_a_signpost(client, db_session, kind):
    _login(client, db_session)
    task = _task(db_session, kind, "payment_record", str(_payment_record(db_session).id))

    html = _detail(client, task)

    assert "Afgehandeld" not in html, (
        "marking a payment 'handled' from the workbench is pointless; on a mismatch it "
        "would also hide that the money is still not booked")
    assert "Besluit" not in html
    assert "Ga naar het onderwerp" in html, "the link is not the primary action"


def test_a_judgement_task_remains_the_workplace(client, db_session):
    """The counterproof, and without it "hiding everything" is indistinguishable from
    "hiding the right thing"."""
    _login(client, db_session)
    task = _task(db_session, "kernel.job_gefaald", "kernel_job", "1")

    html = _detail(client, task)

    assert "Afgehandeld" in html and "Besluit" in html, (
        "a task you can only judge has lost its workplace")


def test_a_failed_job_shows_its_data_in_place(client, db_session):
    """There is no screen for kernel jobs, so this IS the way to the subject."""
    from app.kernel.jobs import KernelJob

    _login(client, db_session)
    job = KernelJob(name="test.job", payload={}, status="failed",
                    run_at=datetime.now(timezone.utc), attempts=5, max_attempts=5,
                    last_error="ZeroDivisionError: division by zero")
    db_session.add(job)
    db_session.flush()
    task = _task(db_session, "kernel.job_gefaald", "kernel_job", str(job.id))

    html = _detail(client, task)

    assert "test.job" in html and "ZeroDivisionError" in html, (
        "you cannot see what you are judging")
    assert "Bekijk het onderwerp" not in html, (
        "there is no screen for a kernel job; a button to one is a dead link")


def test_a_mail_task_points_at_the_e_mail_log(client, db_session):
    from app.domains.mail.api import EmailLog

    _login(client, db_session)
    log = EmailLog(recipient="someone@example.com", subject="Test",
                   email_type="generic", status="failed")
    db_session.add(log)
    db_session.flush()
    task = _task(db_session, "mail.definitief_gefaald", "email_log", str(log.id))

    html = _detail(client, task)

    assert "/admin/e-maillog?recipient=someone%40example.com" in html, (
        "the mail task does not point at the log of that recipient")
    assert "Afgehandeld" in html, "a mail task remains a workplace"


def test_a_message_task_points_at_the_submissions(client, db_session):
    from app.domains.forms.models import Form, FormSubmission

    _login(client, db_session)
    form = Form(title="Test form", status="open", is_anonymous=True,
                share_token="w822")
    db_session.add(form)
    db_session.flush()
    submission = FormSubmission(form_id=form.id, submitter_name="Someone")
    db_session.add(submission)
    db_session.flush()
    task = _task(db_session, "bericht.behartigen", "form_submission",
                 str(submission.id))

    html = _detail(client, task)

    assert f"/admin/formulieren/{form.id}/inzendingen" in html, (
        "the message task does not point at the submissions of its own form")
    assert "Afgehandeld" in html, "a message task remains a workplace"
