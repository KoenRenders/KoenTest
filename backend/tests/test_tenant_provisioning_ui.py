"""Tenant-provisioning (#546 fase 3): OPERATOR maakt een tenant aan; ADMIN mag niet.
De nieuw aangemaakte UNIT-organization resolvet daarna dynamisch (zonder codewijziging).
"""
from app.domains.auth.api import (
    SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value)


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


def test_tenants_scherm_operator_only(client, db_session):
    _user(db_session, "adminonly@example.com", "ADMIN")
    _session(client, "adminonly@example.com")
    assert client.get("/admin/tenants").status_code == 403


def test_operator_maakt_tenant_aan_en_resolvet(client, db_session):
    from app.domains.mdm.api import Organization, tenant_codes

    _user(db_session, "op@example.com", "OPERATOR")
    csrf = _session(client, "op@example.com")
    resp = client.post("/admin/tenants",
                       data={"name": "Raak Teststad", "code": "raakteststad"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    db_session.expire_all()
    org = db_session.query(Organization).filter(
        Organization.code == "raakteststad").one()
    assert org.org_type == "UNIT" and org.is_active is True
    # De dynamische code→id-map bevat de nieuwe tenant → hij resolvet.
    assert tenant_codes(db=db_session).get("raakteststad") == org.id


def test_ongeldige_code_geweigerd(client, db_session):
    _user(db_session, "op2@example.com", "OPERATOR")
    csrf = _session(client, "op2@example.com")
    resp = client.post("/admin/tenants",
                       data={"name": "X", "code": "Foute Code!"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200 and "geldige code" in resp.text.lower()
