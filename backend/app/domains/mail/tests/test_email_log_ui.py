"""E-maillog admin-scherm (#523): the mail 'zoals gemaild'.

The body stands in a sandboxed iframe (srcdoc), so its layout (bullets,
indents) survives. Since #1925 it stands on the mail's own page, which the
list's row opens; the list shows the subject as the row's link.
"""

from datetime import datetime, timezone

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mail.models import EmailLog
from tests.conftest import SEEDED_ADMIN_EMAIL


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _seed(db):
    db.add(
        EmailLog(
            recipient="jan@example.com",
            subject="Inschrijving bevestigd: E2E-CHECK Product met een lang onderwerp",
            email_type="form_confirmation",
            status="sent",
            body="<p>Beste Jan</p><ul><li>Punt een</li><li>Punt twee</li></ul>",
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def test_email_log_lijst_en_iframe_preview(client, db_session):
    _seed(db_session)
    _login(client)
    lijst = client.get("/admin/e-maillog")
    assert lijst.status_code == 200
    log = db_session.query(EmailLog).filter(EmailLog.recipient == "jan@example.com").one()
    assert f'href="/admin/e-maillog/{log.id}' in lijst.text, "the row opens the mail's page"
    assert "srcdoc=" not in lijst.text, "no mail in the list itself"

    resp = client.get(f"/admin/e-maillog/{log.id}")
    assert resp.status_code == 200
    # Body "zoals gemaild" via een gesandboxte iframe (srcdoc), geen |safe in-page.
    assert "srcdoc=" in resp.text
    assert "sandbox" in resp.text
    # De body-HTML zit attribuut-geëscaped in de srcdoc (niet rauw in de pagina).
    assert "&lt;ul&gt;" in resp.text
    assert "Aan: jan@example.com" in resp.text
    assert "Inschrijving bevestigd: E2E-CHECK" in resp.text


def test_een_onbekende_mail_is_een_404(client, db_session):
    _login(client)
    assert client.get("/admin/e-maillog/999999").status_code == 404
