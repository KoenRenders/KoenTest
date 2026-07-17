"""#530 (security): gebruikersbeheer is ADMIN-only.

`require_admin_ui` laat de bredere backoffice-set (ADMIN/FINANCE/ACCOUNT_ADMIN/
OPERATOR) toe zodat die rollen de admin-schil kunnen gebruiken. Maar accounts en
rollen beheren — met name de ADMIN-rol toekennen — mag enkel een ADMIN; anders kan
een FINANCE-account zichzelf via dit server-rendered scherm naar ADMIN escaleren
(de JSON-API dwong dit al af, het UI-pad omzeilde het).
"""
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import (
    SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value)


def _session(client, email):
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _make_backoffice(db, email, role):
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code=role))
    db.flush()
    return user


def test_finance_kan_gebruikersbeheer_niet_openen(client, db_session):
    _make_backoffice(db_session, "fin@example.com", "FINANCE")
    _session(client, "fin@example.com")
    assert client.get("/admin/gebruikers").status_code == 403


def test_finance_kan_geen_admin_aanmaken(client, db_session):
    """De kern van de escalatie: FINANCE mag geen nieuwe (ADMIN-)gebruiker maken."""
    _make_backoffice(db_session, "fin2@example.com", "FINANCE")
    csrf = _session(client, "fin2@example.com")
    resp = client.post(
        "/admin/gebruikers",
        data={"email": "nieuw-admin@example.com", "role_codes": "ADMIN"},
        headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 403
    assert db_session.query(User).filter(
        User.email == "nieuw-admin@example.com").first() is None


def test_operator_kan_gebruiker_niet_verwijderen(client, db_session):
    slachtoffer = _make_backoffice(db_session, "victim@example.com", "OPERATOR")
    _make_backoffice(db_session, "op@example.com", "OPERATOR")
    csrf = _session(client, "op@example.com")
    resp = client.post(f"/admin/gebruikers/{slachtoffer.id}/verwijderen",
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 403


def test_admin_kan_gebruikersbeheer_wel(client, db_session):
    """Regressie: een echte ADMIN houdt volledige toegang tot gebruikersbeheer."""
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    assert client.get("/admin/gebruikers").status_code == 200
