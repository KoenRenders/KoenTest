"""Tests voor de geünificeerde login (één e-mailgebaseerde flow voor backoffice
én leden) en de per-request afgeleide capabilities.

Bewijst de kerngaranties van de auth-unificatie:
  - onbekend e-mailadres lekt niets en maakt geen token aan;
  - admins loggen in via OTP en zijn admin (rol uit users/user_roles);
  - leden loggen in via magic-link en zijn lid (afgeleid uit ContactDetail);
  - één persoon kan tegelijk admin én lid zijn via hetzelfde e-mailadres,
    zonder opgeslagen koppeling tussen User en Person;
  - rolcontrole (require_roles) blokkeert leden op admin-endpoints;
  - een OTP is eenmalig bruikbaar.
"""
from tests.conftest import seed_postal_code, SEEDED_ADMIN_EMAIL
from app.models.login_token import LoginToken
from app.routers import auth as auth_router

FIXED_OTP = "424242"


def _fix_otp(monkeypatch):
    """De code staat sinds #395 gehasht in de DB - tests pinnen de plaintext."""
    monkeypatch.setattr(auth_router, "_generate_otp", lambda: FIXED_OTP)


def _family_payload(email):
    return {
        "street": "Milostraat", "house_number": "40", "postal_code": "2400",
        "payment_method": "transfer",
        "members": [
            {"last_name": "Lid", "first_name": "Jan", "email": email,
             "mobile": "0470000000", "relation_type": "HOOFDLID"},
        ],
    }


def _seed_member(client, db_session, email):
    seed_postal_code(db_session)
    resp = client.post("/api/v1/families", json=_family_payload(email))
    assert resp.status_code == 201, resp.text


def _latest_token(db_session, email):
    return (
        db_session.query(LoginToken)
        .filter(LoginToken.email == email)
        .order_by(LoginToken.id.desc())
        .first()
    )


# ── request-login ──────────────────────────────────────────────────────────────

def test_request_login_unknown_email_creates_no_token(client, db_session):
    resp = client.post("/api/v1/auth/request-login", json={"email": "niemand@example.com"})
    assert resp.status_code == 200
    assert "gekend" in resp.json()["detail"]  # generieke respons, lekt niets
    assert _latest_token(db_session, "niemand@example.com") is None


def test_request_login_admin_creates_token(client, db_session, monkeypatch):
    _fix_otp(monkeypatch)
    resp = client.post("/api/v1/auth/request-login", json={"email": SEEDED_ADMIN_EMAIL})
    assert resp.status_code == 200
    tok = _latest_token(db_session, SEEDED_ADMIN_EMAIL)
    assert tok is not None and tok.otp_code is not None
    assert len(tok.otp_code) == 64 and tok.otp_code != FIXED_OTP  # gehasht (#395)


def test_request_login_member_creates_token(client, db_session):
    _seed_member(client, db_session, "lid@example.com")
    resp = client.post("/api/v1/auth/request-login", json={"email": "lid@example.com"})
    assert resp.status_code == 200
    assert _latest_token(db_session, "lid@example.com") is not None


# ── verify + /auth/me ────────────────────────────────────────────────────────

def test_admin_login_via_otp_and_capabilities(client, db_session, monkeypatch):
    _fix_otp(monkeypatch)
    client.post("/api/v1/auth/request-login", json={"email": SEEDED_ADMIN_EMAIL})
    code = FIXED_OTP

    resp = client.post("/api/v1/auth/verify-otp", json={"email": SEEDED_ADMIN_EMAIL, "code": code})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["is_admin"] is True
    assert "ADMIN" in body["roles"]
    assert body["is_member"] is False  # admin-mail hangt aan geen persoon


def test_member_login_via_magic_link_and_capabilities(client, db_session):
    _seed_member(client, db_session, "lid@example.com")
    client.post("/api/v1/auth/request-login", json={"email": "lid@example.com"})
    magic = _latest_token(db_session, "lid@example.com").token

    resp = client.get("/api/v1/auth/verify-login", params={"token": magic})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["is_member"] is True
    assert me["member_name"] == "Jan Lid"
    assert me["is_admin"] is False
    assert me["roles"] == []


def test_admin_who_is_also_member(client, db_session, monkeypatch):
    """Eén persoon, één e-mailadres: tegelijk admin (users) én lid (ContactDetail)."""
    _fix_otp(monkeypatch)
    _seed_member(client, db_session, SEEDED_ADMIN_EMAIL)
    client.post("/api/v1/auth/request-login", json={"email": SEEDED_ADMIN_EMAIL})
    code = FIXED_OTP
    token = client.post(
        "/api/v1/auth/verify-otp", json={"email": SEEDED_ADMIN_EMAIL, "code": code}
    ).json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["is_admin"] is True
    assert me["is_member"] is True


# ── autorisatie ────────────────────────────────────────────────────────────────

def test_member_token_forbidden_on_admin_endpoint(client, db_session):
    _seed_member(client, db_session, "lid@example.com")
    client.post("/api/v1/auth/request-login", json={"email": "lid@example.com"})
    magic = _latest_token(db_session, "lid@example.com").token
    token = client.get("/api/v1/auth/verify-login", params={"token": magic}).json()["access_token"]

    resp = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_member_token_can_access_household(client, db_session):
    _seed_member(client, db_session, "lid@example.com")
    client.post("/api/v1/auth/request-login", json={"email": "lid@example.com"})
    magic = _latest_token(db_session, "lid@example.com").token
    token = client.get("/api/v1/auth/verify-login", params={"token": magic}).json()["access_token"]

    resp = client.get("/api/v1/member/household", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text


# ── OTP eenmalig ────────────────────────────────────────────────────────────────

def test_otp_is_single_use(client, db_session, monkeypatch):
    _fix_otp(monkeypatch)
    client.post("/api/v1/auth/request-login", json={"email": SEEDED_ADMIN_EMAIL})
    code = FIXED_OTP

    first = client.post("/api/v1/auth/verify-otp", json={"email": SEEDED_ADMIN_EMAIL, "code": code})
    assert first.status_code == 200
    second = client.post("/api/v1/auth/verify-otp", json={"email": SEEDED_ADMIN_EMAIL, "code": code})
    assert second.status_code == 401
