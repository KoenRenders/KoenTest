"""Tests voor de centrale e-maillog (#328)."""
from datetime import datetime, timezone, timedelta

import pytest

from app.database import SessionLocal
from app.domains.mail.models import EmailLog
from app.domains.mail.api import send_form_confirmation, purge_old_email_logs


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
    assert rows[0].email_type == "form_confirmation"
    assert rows[0].status == "skipped"
    assert rows[0].body  # volledige inhoud bewaard


def test_send_logs_sent(monkeypatch):
    from app.domains.mail import service as email_mod

    monkeypatch.setattr(email_mod.settings, "gmail_user", "x@raak.be")
    monkeypatch.setattr(email_mod.settings, "gmail_app_password", "pw")

    class _FakeSMTP:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, *a): pass
        def sendmail(self, *a): pass

    monkeypatch.setattr(email_mod.smtplib, "SMTP_SSL", lambda *a, **k: _FakeSMTP())

    recipient = "sent-test@example.com"
    send_form_confirmation(to_email=recipient, form_title="Contacteer ons", name="Test")
    rows = _logs_for(recipient)
    assert len(rows) == 1
    assert rows[0].status == "sent"
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
    assert rows[0].status == "failed"
    assert "SMTP down" in (rows[0].error_message or "")


def test_failed_send_enqueues_retry_job(monkeypatch):
    from app.domains.mail import service as email_mod
    from app.kernel.jobs import KernelJob

    monkeypatch.setattr(email_mod.settings, "gmail_user", "x@raak.be")
    monkeypatch.setattr(email_mod.settings, "gmail_app_password", "pw")
    monkeypatch.setattr(email_mod.smtplib, "SMTP_SSL",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("SMTP down")))

    recipient = "retry-enqueue@example.com"
    send_form_confirmation(to_email=recipient, form_title="Contacteer ons", name="T")
    log_id = _logs_for(recipient)[0].id

    s = SessionLocal()
    try:
        jobs = (s.query(KernelJob).filter(KernelJob.name == "mail.retry").all())
        assert any(j.payload.get("email_log_id") == log_id and j.status == "pending"
                   for j in jobs)
    finally:
        s.close()


def test_retry_job_resends_and_marks_sent(monkeypatch):
    from app.domains.mail import handlers as mail_handlers
    from app.domains.mail import service as email_mod
    from app.kernel.jobs import KernelJob, run_due_jobs

    # 1. Verzending faalt → log 'failed' + retry-job gepland.
    monkeypatch.setattr(email_mod.settings, "gmail_user", "x@raak.be")
    monkeypatch.setattr(email_mod.settings, "gmail_app_password", "pw")
    monkeypatch.setattr(email_mod.smtplib, "SMTP_SSL",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("SMTP down")))
    recipient = "retry-resend@example.com"
    send_form_confirmation(to_email=recipient, form_title="Contacteer ons", name="T")
    log_id = _logs_for(recipient)[0].id

    # 2. Bij de retry doet SMTP het weer → job draait, log wordt 'sent'.
    class _FakeSMTP:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, *a): pass
        def sendmail(self, *a): pass

    monkeypatch.setattr(mail_handlers.smtplib, "SMTP_SSL", lambda *a, **k: _FakeSMTP())

    s = SessionLocal()
    try:
        run_due_jobs(s)
        row = s.get(EmailLog, log_id)
        assert row.status == "sent" and row.error_message is None
        job_row = (s.query(KernelJob).filter(KernelJob.name == "mail.retry")
                   .order_by(KernelJob.id.desc()).first())
        assert job_row.status == "done"
    finally:
        s.close()


def test_admin_endpoint_requires_admin(client):
    assert client.get("/api/v1/admin/email-log").status_code == 401


def test_admin_endpoint_lists_and_filters(client, admin_headers):
    send_form_confirmation(to_email="listed@example.com", form_title="Contacteer ons", name="T")
    resp = client.get("/api/v1/admin/email-log", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body and "total" in body
    # Filter op type levert enkel form_confirmation op.
    resp2 = client.get("/api/v1/admin/email-log?email_type=form_confirmation", headers=admin_headers)
    assert all(i["email_type"] == "form_confirmation" for i in resp2.json()["items"])


def test_purge_respects_retention(db_session):
    old = EmailLog(
        recipient="old@example.com", subject="oud", email_type="other", status="sent",
        created_at=datetime.now(timezone.utc) - timedelta(days=400),
    )
    recent = EmailLog(
        recipient="recent@example.com", subject="nieuw", email_type="other", status="sent",
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
    db_session.add(EmailLog(
        recipient="keep@example.com", subject="x", email_type="other", status="sent",
        created_at=datetime.now(timezone.utc) - timedelta(days=1000),
    ))
    db_session.flush()
    assert purge_old_email_logs(db_session, retention_days=0) == 0


def test_admin_can_delete_email_log(client, admin_headers, db_session):
    row = EmailLog(recipient="to-delete@example.com", subject="x", email_type="other", status="sent")
    db_session.add(row)
    db_session.flush()
    log_id = row.id
    # Geen token → geweigerd.
    assert client.delete(f"/api/v1/admin/email-log/{log_id}").status_code == 401
    # Admin → verwijderd.
    assert client.delete(f"/api/v1/admin/email-log/{log_id}", headers=admin_headers).status_code == 204
    assert db_session.query(EmailLog).filter(EmailLog.id == log_id).first() is None
    # Onbekende id → 404.
    assert client.delete("/api/v1/admin/email-log/99999999", headers=admin_headers).status_code == 404


def test_mail_requested_event_sends_and_logs(db_session):
    """MailRequested (kernel-contract, #399): publiceren volstaat — het
    mail-component verstuurt en logt via het _send-chokepoint (hier zonder
    credentials → status 'skipped', maar wél gelogd met het juiste type)."""
    from app.kernel.contracts.mail import MailRequested
    from app.kernel.events import publish

    recipient = "event-mail@example.com"
    publish(MailRequested(to_email=recipient, subject="Event-test",
                          body_html="<p>hallo</p>", email_type="other"), db_session)
    rows = _logs_for(recipient)
    assert len(rows) == 1
    assert rows[0].subject == "Event-test" and rows[0].status == "skipped"
