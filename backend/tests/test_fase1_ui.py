"""Fase 1 (#399): server-rendered schermen — aanmelden (htmx) en e-maillog."""
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mail.models import EmailLog


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


# ── Aanmelden ──────────────────────────────────────────────────────────────────

def test_aanmelden_page_renders(client):
    resp = client.get("/aanmelden")
    assert resp.status_code == 200 and "E-mailadres" in resp.text


def test_aanmelden_flow_sets_session_cookie(client, monkeypatch):
    from app.domains.auth import router as auth_router
    monkeypatch.setattr(auth_router, "_generate_otp", lambda: "424242")

    step1 = client.post("/aanmelden", data={"email": SEEDED_ADMIN_EMAIL})
    assert step1.status_code == 200 and "code" in step1.text.lower()

    step2 = client.post("/aanmelden/code",
                        data={"email": SEEDED_ADMIN_EMAIL, "code": "424242"})
    assert step2.status_code == 200
    assert SESSION_COOKIE in step2.cookies
    assert step2.headers.get("HX-Redirect") == "/admin/werkbank"


def test_aanmelden_wrong_code_shows_error_without_cookie(client, monkeypatch):
    from app.domains.auth import router as auth_router
    monkeypatch.setattr(auth_router, "_generate_otp", lambda: "424242")
    client.post("/aanmelden", data={"email": SEEDED_ADMIN_EMAIL})

    resp = client.post("/aanmelden/code",
                       data={"email": SEEDED_ADMIN_EMAIL, "code": "000000"})
    assert resp.status_code == 200
    assert "Ongeldige of verlopen code" in resp.text
    assert SESSION_COOKIE not in resp.cookies


def test_aanmelden_unknown_email_shows_same_generic_step(client):
    resp = client.post("/aanmelden", data={"email": "onbekend@example.com"})
    assert resp.status_code == 200
    # Zelfde vervolgstap als voor een gekend adres — geen verklapping.
    assert "gekend is" in resp.text


# ── E-maillog ──────────────────────────────────────────────────────────────────

def test_email_log_page_requires_session(client):
    assert client.get("/admin/e-maillog").status_code == 401


def test_email_log_page_lists_and_filters(client, db_session):
    db_session.add(EmailLog(recipient="ui-test@example.com", subject="UI-testmail",
                            email_type="magic_link", status="sent"))
    db_session.flush()
    _login(client)

    page = client.get("/admin/e-maillog")
    assert page.status_code == 200 and "UI-testmail" in page.text

    gefilterd = client.get("/admin/e-maillog/lijst?email_type=form_confirmation")
    assert gefilterd.status_code == 200 and "UI-testmail" not in gefilterd.text


def test_email_log_delete_requires_csrf(client, db_session):
    row = EmailLog(recipient="del-ui@example.com", subject="Weg ermee",
                   email_type="other", status="sent")
    db_session.add(row)
    db_session.flush()
    csrf = _login(client)

    zonder = client.post(f"/admin/e-maillog/{row.id}/verwijderen", data={})
    assert zonder.status_code == 403

    met = client.post(f"/admin/e-maillog/{row.id}/verwijderen",
                      headers={"X-CSRF-Token": csrf})
    assert met.status_code == 200
    assert db_session.query(EmailLog).filter(EmailLog.id == row.id).first() is None
