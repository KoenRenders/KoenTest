"""Auth/authz-randgevallen (#129): tokenvervaldatum, manipulatie, ontbrekend
token, en eigenaarschap (een lid mag enkel het eigen gezin bewerken).

Vult test_auth_unification.py aan (dat de happy path + rolcontrole dekt)."""

from datetime import timedelta

from app.domains.auth.api import create_access_token


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _family_payload(email):
    return {
        "street": "Milostraat",
        "house_number": "40",
        "postal_code": "2400",
        "payment_method": "transfer",
        "members": [
            {
                "last_name": "Lid",
                "first_name": "Jan",
                "email": email,
                "mobile": "0470000000",
                "date_of_birth": "1980-01-01",
                "gender_code": "M",
                "relation_type": "HOOFDLID",
            },
        ],
    }


# ── tokenvalidatie ───────────────────────────────────────────────────────────


def test_expired_token_is_rejected(client):
    token = create_access_token({"sub": "iemand@example.com"}, expires_delta=timedelta(minutes=-5))
    resp = client.get("/api/v1/auth/me", headers=_headers(token))
    assert resp.status_code == 401


def test_tampered_token_is_rejected(client):
    """Een gewijzigde handtekening wordt geweigerd.

    Niet de LAATSTE tekens vervangen: een HMAC-SHA256-handtekening is 32 bytes en
    dus 43 base64url-tekens, waarvan het laatste teken maar 2 betekenisvolle bits
    draagt — de andere vier worden genegeerd. Twee verschillende slotletters
    kunnen dus dezelfde bytes opleveren, en dan is het "gewijzigde" token nog
    geldig. Deze test sloeg daardoor af en toe over in groen zonder iets te
    bewijzen; ze faalde op run 33987137054 met 200 i.p.v. 401.

    Nu wordt een teken in het MIDDEN van de handtekening omgezet: daar telt elk
    bit mee, dus de bytes verschillen gegarandeerd.
    """
    token = create_access_token({"sub": "iemand@example.com"})
    kop, payload, handtekening = token.split(".")
    midden = len(handtekening) // 2
    anders = "A" if handtekening[midden] != "A" else "B"
    tampered = f"{kop}.{payload}.{handtekening[:midden]}{anders}{handtekening[midden + 1 :]}"
    assert tampered != token
    resp = client.get("/api/v1/auth/me", headers=_headers(tampered))
    assert resp.status_code == 401


def test_missing_token_on_protected_endpoint(client):
    # The member's own JSON endpoint; the household view that stood here lost its
    # route with CR-13 phase 4b (#1251).
    resp = client.get("/api/v1/auth/member/me")
    assert resp.status_code == 401


def test_garbage_authorization_header_is_rejected(client):
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


# ── autorisatie op beheer-endpoints ──────────────────────────────────────────


def test_create_user_rejects_unknown_role_code(client, admin_headers, db_session):
    """Sinds migratie 076 is er geen FK meer naar public.role_codes (§8);
    de servicelaag moet onbekende rolcodes met een nette 400 weigeren."""
    resp = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={"email": "nieuwe@example.com", "role_codes": ["NEPROL"]},
    )
    assert resp.status_code == 400
    assert "NEPROL" in resp.json()["detail"]

    from app.domains.auth.api import User

    assert db_session.query(User).filter(User.email == "nieuwe@example.com").first() is None
