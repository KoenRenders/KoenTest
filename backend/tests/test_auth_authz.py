"""Auth/authz-randgevallen (#129): tokenvervaldatum, manipulatie, ontbrekend
token, en eigenaarschap (een lid mag enkel het eigen gezin bewerken).

Vult test_auth_unification.py aan (dat de happy path + rolcontrole dekt)."""
from datetime import timedelta

from app.auth import create_access_token
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

    from app.models.contact import ContactDetail
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
