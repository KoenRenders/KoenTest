"""OTP-login hardening (#268): per-account pogingteller + lockout, en hoogstens
één levende OTP per e-mailadres.

Until CR-13 phase 4b (#1251) these went through the JSON routes under
`/api/v1/auth`; they walk the sign-in screen now (`POST /aanmelden`,
`POST /aanmelden/code`), which calls the same `start_login` and code check."""

# De OTP-generator woont sinds #635 I in auth/login.py (de aanmeldstap is service,
# geen router); patchen doe je waar de implementatie staat.
from app.domains.auth import login as auth_login
from app.domains.auth.api import SESSION_COOKIE, LoginToken
from app.domains.auth.login import MAX_OTP_ATTEMPTS
from app.limiter import login_limiter
from tests.conftest import SEEDED_ADMIN_EMAIL

FIXED_OTP = "424242"


def _latest_token(db_session, email):
    return (
        db_session.query(LoginToken)
        .filter(LoginToken.email == email)
        .order_by(LoginToken.id.desc())
        .first()
    )


def test_otp_locks_out_after_max_attempts(client, db_session, monkeypatch):
    monkeypatch.setattr(auth_login, "_generate_otp", lambda: FIXED_OTP)
    client.post("/aanmelden", data={"email": SEEDED_ADMIN_EMAIL})
    code = FIXED_OTP
    wrong = "000000"

    # MAX_OTP_ATTEMPTS foute pogingen; de per-IP-limiet neutraliseren zodat we de
    # per-account-lockout zuiver testen (niet de 429 van login_limiter raken).
    for _ in range(MAX_OTP_ATTEMPTS):
        login_limiter._calls.clear()
        bad = client.post("/aanmelden/code", data={"email": SEEDED_ADMIN_EMAIL, "code": wrong})
        assert "Ongeldige of verlopen code." in bad.text
        assert SESSION_COOKIE not in bad.cookies

    # Na de lockout werkt zelfs de JUISTE code niet meer: het token is dood.
    login_limiter._calls.clear()
    good = client.post("/aanmelden/code", data={"email": SEEDED_ADMIN_EMAIL, "code": code})
    assert "Ongeldige of verlopen code." in good.text
    assert SESSION_COOKIE not in good.cookies and "HX-Redirect" not in good.headers


def test_new_request_login_invalidates_previous_otp(client, db_session):
    client.post("/aanmelden", data={"email": SEEDED_ADMIN_EMAIL})
    token1_id = _latest_token(db_session, SEEDED_ADMIN_EMAIL).id

    client.post("/aanmelden", data={"email": SEEDED_ADMIN_EMAIL})
    db_session.expire_all()

    token1 = db_session.query(LoginToken).filter(LoginToken.id == token1_id).first()
    assert token1.used is True  # door de tweede aanvraag geïnvalideerd

    live = (
        db_session.query(LoginToken)
        .filter(LoginToken.email == SEEDED_ADMIN_EMAIL, LoginToken.used == False)
        .count()
    )
    assert live == 1  # hoogstens één levende OTP per e-mail
