"""Tests voor de centrale e-maillog (#328)."""

from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.domains.mail.api import EmailType, MailStatus, purge_old_email_logs, send_form_confirmation
from app.domains.mail.models import EmailLog
from app.kernel.jobs import JobStatus


def _logs_for(recipient: str):
    s = SessionLocal()
    try:
        return s.query(EmailLog).filter(EmailLog.recipient == recipient).all()
    finally:
        s.close()


def test_send_without_credentials_logs_skipped():
    # In de testomgeving zijn er geen Gmail-credentials → status 'skipped',
    # maar de mail wordt wél gelogd met het juiste type.
    recipient = "skip-test@example.com"
    send_form_confirmation(to_email=recipient, form_title="Contacteer ons", name="Test")
    rows = _logs_for(recipient)
    assert len(rows) == 1
    assert rows[0].email_type is EmailType.FORM_CONFIRMATION
    assert rows[0].status is MailStatus.SKIPPED
    assert rows[0].body  # volledige inhoud bewaard


def test_send_logs_sent(monkeypatch):
    from app.domains.mail import service as email_mod

    monkeypatch.setattr(email_mod.settings, "gmail_user", "x@raak.be")
    monkeypatch.setattr(email_mod.settings, "gmail_app_password", "pw")

    class _FakeSMTP:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, *a):
            pass

        def sendmail(self, *a):
            pass

    monkeypatch.setattr(email_mod.smtplib, "SMTP_SSL", lambda *a, **k: _FakeSMTP())

    recipient = "sent-test@example.com"
    send_form_confirmation(to_email=recipient, form_title="Contacteer ons", name="Test")
    rows = _logs_for(recipient)
    assert len(rows) == 1
    assert rows[0].status is MailStatus.SENT
    assert rows[0].error_message is None


def test_send_logs_failed(monkeypatch):
    from app.domains.mail import service as email_mod

    monkeypatch.setattr(email_mod.settings, "gmail_user", "x@raak.be")
    monkeypatch.setattr(email_mod.settings, "gmail_app_password", "pw")

    def _boom(*a, **k):
        raise OSError("SMTP down")

    monkeypatch.setattr(email_mod.smtplib, "SMTP_SSL", _boom)

    recipient = "failed-test@example.com"
    send_form_confirmation(to_email=recipient, form_title="Contacteer ons", name="Test")
    rows = _logs_for(recipient)
    assert len(rows) == 1
    assert rows[0].status is MailStatus.FAILED
    assert "SMTP down" in (rows[0].error_message or "")


def test_failed_send_enqueues_retry_job(monkeypatch):
    from app.domains.mail import service as email_mod
    from app.kernel.jobs import KernelJob

    monkeypatch.setattr(email_mod.settings, "gmail_user", "x@raak.be")
    monkeypatch.setattr(email_mod.settings, "gmail_app_password", "pw")
    monkeypatch.setattr(
        email_mod.smtplib, "SMTP_SSL", lambda *a, **k: (_ for _ in ()).throw(OSError("SMTP down"))
    )

    recipient = "retry-enqueue@example.com"
    send_form_confirmation(to_email=recipient, form_title="Contacteer ons", name="T")
    log_id = _logs_for(recipient)[0].id

    s = SessionLocal()
    try:
        jobs = s.query(KernelJob).filter(KernelJob.name == "mail.retry").all()
        assert any(
            j.payload.get("email_log_id") == log_id and j.status is JobStatus.PENDING for j in jobs
        )
    finally:
        s.close()


def test_retry_job_resends_and_marks_sent(monkeypatch):
    from app.domains.mail import handlers as mail_handlers
    from app.domains.mail import service as email_mod
    from app.kernel.jobs import KernelJob, run_due_jobs

    # 1. Verzending faalt → log 'failed' + retry-job gepland.
    monkeypatch.setattr(email_mod.settings, "gmail_user", "x@raak.be")
    monkeypatch.setattr(email_mod.settings, "gmail_app_password", "pw")
    monkeypatch.setattr(
        email_mod.smtplib, "SMTP_SSL", lambda *a, **k: (_ for _ in ()).throw(OSError("SMTP down"))
    )
    recipient = "retry-resend@example.com"
    send_form_confirmation(to_email=recipient, form_title="Contacteer ons", name="T")
    log_id = _logs_for(recipient)[0].id

    # 2. Bij de retry doet SMTP het weer → job draait, log wordt 'sent'.
    class _FakeSMTP:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, *a):
            pass

        def sendmail(self, *a):
            pass

    monkeypatch.setattr(mail_handlers.smtplib, "SMTP_SSL", lambda *a, **k: _FakeSMTP())

    s = SessionLocal()
    try:
        run_due_jobs(s)
        row = s.get(EmailLog, log_id)
        assert row.status is MailStatus.SENT and row.error_message is None
        job_row = (
            s.query(KernelJob)
            .filter(KernelJob.name == "mail.retry")
            .order_by(KernelJob.id.desc())
            .first()
        )
        assert job_row.status is JobStatus.DONE
    finally:
        s.close()


def test_the_log_lists_and_filters(db_session):
    """The log as the e-mail log screen reads it (`mail.service.list_email_log`);
    the JSON route that kept a second copy of this query went with #1251."""
    from app.domains.mail.service import list_email_log

    for kind in (EmailType.FORM_CONFIRMATION, EmailType.OTHER):
        db_session.add(
            EmailLog(recipient="listed@example.com", subject="x", email_type=kind, status="sent")
        )
    db_session.flush()
    rows, total = list_email_log(db_session)
    assert total >= 2 and len(rows) >= 2
    # Filter op type levert enkel form_confirmation op.
    filtered, count = list_email_log(db_session, email_type="form_confirmation")
    assert count >= 1 and count < total
    assert all(row.email_type == EmailType.FORM_CONFIRMATION for row in filtered)


def test_purge_respects_retention(db_session):
    old = EmailLog(
        recipient="old@example.com",
        subject="oud",
        email_type="other",
        status="sent",
        created_at=datetime.now(timezone.utc) - timedelta(days=400),
    )
    recent = EmailLog(
        recipient="recent@example.com",
        subject="nieuw",
        email_type="other",
        status="sent",
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db_session.add_all([old, recent])
    db_session.flush()

    deleted = purge_old_email_logs(db_session, retention_days=365)
    assert deleted == 1
    remaining = {e.recipient for e in db_session.query(EmailLog).all()}
    assert "recent@example.com" in remaining
    assert "old@example.com" not in remaining


def test_purge_zero_retention_keeps_all(db_session):
    db_session.add(
        EmailLog(
            recipient="keep@example.com",
            subject="x",
            email_type="other",
            status="sent",
            created_at=datetime.now(timezone.utc) - timedelta(days=1000),
        )
    )
    db_session.flush()
    assert purge_old_email_logs(db_session, retention_days=0) == 0


def test_a_logged_mail_can_be_deleted(db_session):
    """`mail.service.delete_email_log`, the function behind the screen's delete."""
    from app.domains.mail.service import delete_email_log

    row = EmailLog(
        recipient="to-delete@example.com", subject="x", email_type="other", status="sent"
    )
    db_session.add(row)
    db_session.flush()
    log_id = row.id
    assert delete_email_log(db_session, log_id) is True
    assert db_session.query(EmailLog).filter(EmailLog.id == log_id).first() is None
    # Onbekende id → niets verwijderd.
    assert delete_email_log(db_session, 99999999) is False


def test_mail_requested_event_sends_and_logs(db_session):
    """MailRequested (kernel-contract, #399): publiceren volstaat — het
    mail-component verstuurt en logt via het _send-chokepoint (hier zonder
    credentials → status 'skipped', maar wél gelogd met het juiste type)."""
    from app.kernel.contracts.mail import MailRequested
    from app.kernel.events import publish

    recipient = "event-mail@example.com"
    publish(
        MailRequested(
            to_email=recipient, subject="Event-test", body_html="<p>hallo</p>", email_type="other"
        ),
        db_session,
    )
    # CR-13 phase 4: the handler queues a job; the job sends and logs.
    from tests.conftest import send_queued_mail

    send_queued_mail(db_session)
    rows = _logs_for(recipient)
    assert len(rows) == 1
    assert rows[0].subject == "Event-test" and rows[0].status is MailStatus.SKIPPED
