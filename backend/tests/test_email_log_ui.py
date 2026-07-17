"""E-maillog admin-scherm (#523): strakke lijst + preview 'zoals gemaild'.

De preview toont de body in een gesandboxte iframe (srcdoc) zodat opmaak
(bullets/indents) behouden blijft, en Type is rustige tekst i.p.v. een pill.
"""
from datetime import datetime, timezone

from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mail.models import EmailLog


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _seed(db):
    db.add(EmailLog(
        recipient="jan@example.com",
        subject="Inschrijving bevestigd: E2E-CHECK Product met een lang onderwerp",
        email_type="form_confirmation", status="sent",
        body="<p>Beste Jan</p><ul><li>Punt een</li><li>Punt twee</li></ul>",
        created_at=datetime.now(timezone.utc),
    ))
    db.commit()


def test_email_log_lijst_en_iframe_preview(client, db_session):
    _seed(db_session)
    _login(client)
    resp = client.get("/admin/e-maillog")
    assert resp.status_code == 200
    # Body "zoals gemaild" via een gesandboxte iframe (srcdoc), geen |safe in-page.
    assert "srcdoc=" in resp.text
    assert "sandbox" in resp.text
    # De body-HTML zit attribuut-geëscaped in de srcdoc (niet rauw in de pagina).
    assert "&lt;ul&gt;" in resp.text
    # Onderwerp op één regel (truncate + title-tooltip).
    assert "truncate" in resp.text
    assert 'title="Inschrijving bevestigd' in resp.text
