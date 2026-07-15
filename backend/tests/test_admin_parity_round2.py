"""Pariteitsronde 2 (#476): admin-restpunten.
- E-maillog: zoeken op ontvanger + leesbare type/status-labels.
- Media: activiteit koppelen bij upload via een naam-dropdown (niet een vrij ID).
"""
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mail.models import EmailLog


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _seed_email(db, recipient, email_type="membership_confirmation", status="sent"):
    db.add(EmailLog(recipient=recipient, subject="Test", email_type=email_type,
                    status=status, body="x"))
    db.flush()


def test_emaillog_recipient_search_filters(client, db_session):
    _seed_email(db_session, "an@example.com")
    _seed_email(db_session, "bob@example.com")
    db_session.commit()
    _login(client)

    html = client.get("/admin/e-maillog/lijst?recipient=an@").text
    assert "an@example.com" in html
    assert "bob@example.com" not in html


def test_emaillog_shows_friendly_labels(client, db_session):
    _seed_email(db_session, "cara@example.com", email_type="magic_link", status="failed")
    db_session.commit()
    _login(client)
    html = client.get("/admin/e-maillog/lijst").text
    # Leesbare labels i.p.v. ruwe codes.
    assert "Inloglink" in html and "Mislukt" in html
    assert "magic_link" not in html


def test_emaillog_has_recipient_search_box(client, db_session):
    _login(client)
    html = client.get("/admin/e-maillog").text
    assert 'name="recipient"' in html


def test_media_upload_has_activity_dropdown(client, db_session):
    from tests.conftest import seed_activity_with_product
    seed_activity_with_product(db_session)
    db_session.commit()
    _login(client)
    html = client.get("/admin/media?kind=activity_photo").text
    # Upload-form gebruikt een select (geen vrij ID-nummerveld meer).
    assert '<select name="activity_id" id="me-activity"' in html
    assert "Kies een activiteit" in html
