"""#530 rolmodel: FINANCE = enkel betalingen; algemene admin-schermen = ADMIN/OPERATOR.

- Een FINANCE-only account mag WEL de betalingen-schermen openen, maar krijgt 403 op
  de algemene admin-schermen (leden/CMS/dashboard/werkbank).
- ADMIN mag de algemene schermen én betalingen bekijken (schrijven op betalingen
  blijft FINANCE/OPERATOR — financiële scheiding #83).
- OPERATOR (platform-superuser) mag alles.
"""
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import (
    SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value)

GENERAL_SCREENS = ["/admin", "/admin/werkbank", "/admin/leden", "/admin/paginas"]


def _session(client, email):
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _user(db, email, *roles):
    u = User(email=email, is_active=True)
    db.add(u)
    db.flush()
    for r in roles:
        db.add(UserRole(user_id=u.id, role_code=r))
    db.flush()
    return u


def test_finance_only_geen_algemene_schermen(client, db_session):
    _user(db_session, "fin-only@example.com", "FINANCE")
    _session(client, "fin-only@example.com")
    for pad in GENERAL_SCREENS:
        assert client.get(pad).status_code == 403, pad


def test_finance_only_wel_betalingen(client, db_session):
    _user(db_session, "fin-only2@example.com", "FINANCE")
    _session(client, "fin-only2@example.com")
    resp = client.get("/admin/betalingen")
    assert resp.status_code == 200
    # Role-aware nav: enkel Betalingen, geen algemene items.
    assert "/admin/betalingen" in resp.text
    assert "/admin/leden" not in resp.text


def test_admin_wel_algemene_schermen_en_betalingen_bekijken(client, db_session):
    # De geseede beheerder heeft ADMIN.
    _session(client, SEEDED_ADMIN_EMAIL)
    for pad in GENERAL_SCREENS + ["/admin/betalingen"]:
        assert client.get(pad).status_code == 200, pad


def test_operator_mag_alles(client, db_session):
    _user(db_session, "op-only@example.com", "OPERATOR")
    _session(client, "op-only@example.com")
    for pad in GENERAL_SCREENS + ["/admin/betalingen"]:
        assert client.get(pad).status_code == 200, pad
