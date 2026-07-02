"""Tests voor de centrale e-maillog (#328)."""
from datetime import datetime, timezone, timedelta

import pytest

from app.database import SessionLocal
from app.models.email_log import EmailLog
from app.services.email import send_idea_acknowledgement, purge_old_email_logs


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
    send_idea_acknowledgement(to_email=recipient, name="Test", message="hallo")
    rows = _logs_for(recipient)
    assert len(rows) == 1
    assert rows[0].email_type == "idea_ack"
    assert rows[0].status == "skipped"
    assert rows[0].body  # volledige inhoud bewaard


def test_send_logs_sent(monkeypatch):
    from app.services import email as email_mod

    monkeypatch.setattr(email_mod.settings, "gmail_user", "x@raak.be")
    monkeypatch.setattr(email_mod.settings, "gmail_app_password", "pw")

    class _FakeSMTP:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, *a): pass
        def sendmail(self, *a): pass

    monkeypatch.setattr(email_mod.smtplib, "SMTP_SSL", lambda *a, **k: _FakeSMTP())

    recipient = "sent-test@example.com"
    send_idea_acknowledgement(to_email=recipient, name="Test", message="hallo")
    rows = _logs_for(recipient)
    assert len(rows) == 1
    assert rows[0].status == "sent"
    assert rows[0].error_message is None


def test_send_logs_failed(monkeypatch):
    from app.services import email as email_mod

    monkeypatch.setattr(email_mod.settings, "gmail_user", "x@raak.be")
    monkeypatch.setattr(email_mod.settings, "gmail_app_password", "pw")

    def _boom(*a, **k):
        raise OSError("SMTP down")

    monkeypatch.setattr(email_mod.smtplib, "SMTP_SSL", _boom)

    recipient = "failed-test@example.com"
    send_idea_acknowledgement(to_email=recipient, name="Test", message="hallo")
    rows = _logs_for(recipient)
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert "SMTP down" in (rows[0].error_message or "")


def test_admin_endpoint_requires_admin(client):
    assert client.get("/api/v1/admin/email-log").status_code == 401


def test_admin_endpoint_lists_and_filters(client, admin_headers):
    send_idea_acknowledgement(to_email="listed@example.com", name="T", message="x")
    resp = client.get("/api/v1/admin/email-log", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body and "total" in body
    # Filter op type levert enkel idea_ack op.
    resp2 = client.get("/api/v1/admin/email-log?email_type=idea_ack", headers=admin_headers)
    assert all(i["email_type"] == "idea_ack" for i in resp2.json()["items"])


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
