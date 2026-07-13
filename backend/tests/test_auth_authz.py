"""Auth/authz-randgevallen (#129): tokenvervaldatum, manipulatie, ontbrekend
token, en eigenaarschap (een lid mag enkel het eigen gezin bewerken).

Vult test_auth_unification.py aan (dat de happy path + rolcontrole dekt)."""
from datetime import timedelta

from app.domains.auth.api import create_access_token
from tests.conftest import seed_postal_code


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _family_payload(email):
    return {
        "street": "Milostraat", "house_number": "40", "postal_code": "2400",
        "payment_method": "transfer",
        "members": [
            {"last_name": "Lid", "first_name": "Jan", "email": email,
             "mobile": "0470000000", "relation_type": "HOOFDLID"},
        ],
    }


# ── tokenvalidatie ───────────────────────────────────────────────────────────

def test_expired_token_is_rejected(client):
    token = create_access_token({"sub": "iemand@example.com"}, expires_delta=timedelta(minutes=-5))
    resp = client.get("/api/v1/auth/me", headers=_headers(token))
    assert resp.status_code == 401


def test_tampered_token_is_rejected(client):
    token = create_access_token({"sub": "iemand@example.com"})
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    resp = client.get("/api/v1/auth/me", headers=_headers(tampered))
    assert resp.status_code == 401


def test_missing_token_on_protected_endpoint(client):
    resp = client.get("/api/v1/member/household")
    assert resp.status_code == 401


def test_garbage_authorization_header_is_rejected(client):
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


# ── eigenaarschap ────────────────────────────────────────────────────────────

def test_member_cannot_edit_other_household(client, db_session):
    """Een ingelogd lid mag geen persoon van een ánder gezin bewerken (403)."""
    seed_postal_code(db_session)
    assert client.post("/api/v1/families", json=_family_payload("lid1@example.com")).status_code == 201
    assert client.post("/api/v1/families", json=_family_payload("lid2@example.com")).status_code == 201

    from app.domains.mdm.api import ContactDetail
    other_pid = (
        db_session.query(ContactDetail.person_id)
        .filter(ContactDetail.value == "lid2@example.com")
        .scalar()
    )
    assert other_pid is not None

    token = create_access_token({"sub": "lid1@example.com"})
    resp = client.put(
        f"/api/v1/member/household/persons/{other_pid}",
        headers=_headers(token),
        json={"first_name": "Hacker"},
    )
    assert resp.status_code == 403


# ── autorisatie op beheer-endpoints ──────────────────────────────────────────

def test_create_member_requires_admin(client, admin_headers):
    """POST /members is een beheerendpoint (#262): zonder admin-token mag niemand
    ongeauthenticeerd gezin-/persoonsrecords aanmaken; met admin-token werkt het."""
    resp = client.post("/api/v1/members", json={"persons": []})
    assert resp.status_code in (401, 403)

    ok = client.post("/api/v1/members", headers=admin_headers, json={"persons": []})
    assert ok.status_code == 200


def test_create_user_rejects_unknown_role_code(client, admin_headers, db_session):
    """Sinds migratie 076 is er geen FK meer naar public.role_codes (§8);
    de servicelaag moet onbekende rolcodes met een nette 400 weigeren."""
    resp = client.post("/api/v1/users", headers=admin_headers,
                       json={"email": "nieuwe@example.com", "role_codes": ["NEPROL"]})
    assert resp.status_code == 400
    assert "NEPROL" in resp.json()["detail"]

    from app.domains.auth.api import User
    assert db_session.query(User).filter(User.email == "nieuwe@example.com").first() is None
