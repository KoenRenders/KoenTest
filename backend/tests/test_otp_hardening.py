"""OTP-login hardening (#268): per-account pogingteller + lockout, en hoogstens
één levende OTP per e-mailadres."""
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.models.login_token import LoginToken
from app.routers.auth import MAX_OTP_ATTEMPTS
from app.limiter import login_limiter
from app.routers import auth as auth_router

FIXED_OTP = "424242"


def _latest_token(db_session, email):
    return (
        db_session.query(LoginToken)
        .filter(LoginToken.email == email)
        .order_by(LoginToken.id.desc())
        .first()
    )


def test_otp_locks_out_after_max_attempts(client, db_session, monkeypatch):
    monkeypatch.setattr(auth_router, "_generate_otp", lambda: FIXED_OTP)
    client.post("/api/v1/auth/request-login", json={"email": SEEDED_ADMIN_EMAIL})
    code = FIXED_OTP
    wrong = "000000"

    # MAX_OTP_ATTEMPTS foute pogingen; de per-IP-limiet neutraliseren zodat we de
    # per-account-lockout zuiver testen (niet de 429 van login_limiter raken).
    for _ in range(MAX_OTP_ATTEMPTS):
        login_limiter._calls.clear()
        bad = client.post(
            "/api/v1/auth/verify-otp",
            json={"email": SEEDED_ADMIN_EMAIL, "code": wrong},
        )
        assert bad.status_code == 401

    # Na de lockout werkt zelfs de JUISTE code niet meer: het token is dood.
    login_limiter._calls.clear()
    good = client.post(
        "/api/v1/auth/verify-otp",
        json={"email": SEEDED_ADMIN_EMAIL, "code": code},
    )
    assert good.status_code == 401


def test_new_request_login_invalidates_previous_otp(client, db_session):
    client.post("/api/v1/auth/request-login", json={"email": SEEDED_ADMIN_EMAIL})
    token1_id = _latest_token(db_session, SEEDED_ADMIN_EMAIL).id

    client.post("/api/v1/auth/request-login", json={"email": SEEDED_ADMIN_EMAIL})
    db_session.expire_all()

    token1 = db_session.query(LoginToken).filter(LoginToken.id == token1_id).first()
    assert token1.used is True  # door de tweede aanvraag geïnvalideerd

    live = (
        db_session.query(LoginToken)
        .filter(LoginToken.email == SEEDED_ADMIN_EMAIL, LoginToken.used == False)
        .count()
    )
    assert live == 1  # hoogstens één levende OTP per e-mail
