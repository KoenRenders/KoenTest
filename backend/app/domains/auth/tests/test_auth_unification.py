"""Tests voor de geünificeerde login (één e-mailgebaseerde flow voor backoffice
én leden) en de per-request afgeleide capabilities.

Bewijst de kerngaranties van de auth-unificatie:
  - onbekend e-mailadres lekt niets en maakt geen token aan;
  - admins loggen in via OTP en zijn admin (rol uit users/user_roles);
  - leden loggen in via magic-link en zijn lid (afgeleid uit ContactDetail);
  - één persoon kan tegelijk admin én lid zijn via hetzelfde e-mailadres,
    zonder opgeslagen koppeling tussen User en Person;
  - een lid komt het beheer niet binnen;
  - een OTP is eenmalig bruikbaar.

Until CR-13 phase 4b (#1251) these went through the JSON routes under
`/api/v1/auth`, which had no caller and left with the bearer token. They hold
the same guarantees through the sign-in screen (`POST /aanmelden`,
`POST /aanmelden/code`, the mail's link `GET /login/verify`) and, for what
someone may, through the functions every screen asks: `get_user_roles`,
`admits_admin_ui`, `login_person_for_email`.
"""

# De OTP-generator woont sinds #635 I in auth/login.py (de aanmeldstap is service,
# geen router); patchen doe je waar de implementatie staat.
from app.domains.auth import login as auth_login
from app.domains.auth.api import (
    SESSION_COOKIE,
    LoginToken,
    back_office_home,
    get_user_roles,
    login_person_for_email,
)
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_postal_code, sign_up_at_the_door

FIXED_OTP = "424242"


def _fix_otp(monkeypatch):
    """De code staat sinds #395 gehasht in de DB - tests pinnen de plaintext."""
    monkeypatch.setattr(auth_login, "_generate_otp", lambda: FIXED_OTP)


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


def _seed_member(client, db_session, email):
    seed_postal_code(db_session)
    resp = sign_up_at_the_door(client, json=_family_payload(email))
    assert resp.status_code == 201, resp.text


def _latest_token(db_session, email):
    return (
        db_session.query(LoginToken)
        .filter(LoginToken.email == email)
        .order_by(LoginToken.id.desc())
        .first()
    )


# ── asking for a code ────────────────────────────────────────────────────────


def _ask(client, email):
    return client.post("/aanmelden", data={"email": email})


def _code(client, email, code=FIXED_OTP):
    return client.post("/aanmelden/code", data={"email": email, "code": code})


def _signed_in(answer) -> bool:
    """The code step signs in by setting the session cookie and sending the browser on."""
    return SESSION_COOKIE in answer.cookies and "HX-Redirect" in answer.headers


def test_request_login_unknown_email_creates_no_token(client, db_session):
    known = _ask(client, SEEDED_ADMIN_EMAIL)
    resp = _ask(client, "niemand@example.com")
    assert resp.status_code == 200
    # Generieke respons, lekt niets: het vervolg is voor een onbekend adres hetzelfde
    # scherm als voor een gekend — de codestap.
    assert 'name="code"' in resp.text and 'name="code"' in known.text
    assert _latest_token(db_session, "niemand@example.com") is None


def test_request_login_admin_creates_token(client, db_session, monkeypatch):
    _fix_otp(monkeypatch)
    resp = _ask(client, SEEDED_ADMIN_EMAIL)
    assert resp.status_code == 200
    tok = _latest_token(db_session, SEEDED_ADMIN_EMAIL)
    assert tok is not None and tok.otp_code is not None
    assert len(tok.otp_code) == 64 and tok.otp_code != FIXED_OTP  # gehasht (#395)


def test_request_login_member_creates_token(client, db_session):
    _seed_member(client, db_session, "lid@example.com")
    resp = _ask(client, "lid@example.com")
    assert resp.status_code == 200
    assert _latest_token(db_session, "lid@example.com") is not None


# ── signing in, and what someone may ─────────────────────────────────────────


def test_admin_login_via_otp_and_capabilities(client, db_session, monkeypatch):
    _fix_otp(monkeypatch)
    _ask(client, SEEDED_ADMIN_EMAIL)

    resp = _code(client, SEEDED_ADMIN_EMAIL)
    assert resp.status_code == 200, resp.text
    assert _signed_in(resp)

    roles = get_user_roles(db_session, SEEDED_ADMIN_EMAIL)
    assert "ADMIN" in roles
    assert back_office_home(db_session, SEEDED_ADMIN_EMAIL) is not None
    assert login_person_for_email(db_session, SEEDED_ADMIN_EMAIL) is None  # hangt aan geen persoon
    # En het beheer laat hem binnen.
    assert client.get("/admin/gebruikers", follow_redirects=False).status_code == 200


def test_member_login_via_magic_link_and_capabilities(client, db_session):
    _seed_member(client, db_session, "lid@example.com")
    _ask(client, "lid@example.com")
    magic = _latest_token(db_session, "lid@example.com").token

    resp = client.get("/login/verify", params={"token": magic}, follow_redirects=False)
    assert resp.status_code in (302, 303), resp.text[:200]
    assert SESSION_COOKIE in resp.cookies

    person = login_person_for_email(db_session, "lid@example.com")
    assert person is not None
    assert f"{person.first_name} {person.last_name}" == "Jan Lid"
    roles = get_user_roles(db_session, "lid@example.com")
    assert sorted(roles) == []
    assert back_office_home(db_session, "lid@example.com") is None


def test_admin_who_is_also_member(client, db_session, monkeypatch):
    """Eén persoon, één e-mailadres: tegelijk admin (users) én lid (ContactDetail)."""
    _fix_otp(monkeypatch)
    _seed_member(client, db_session, SEEDED_ADMIN_EMAIL)
    _ask(client, SEEDED_ADMIN_EMAIL)
    assert _signed_in(_code(client, SEEDED_ADMIN_EMAIL))

    assert back_office_home(db_session, SEEDED_ADMIN_EMAIL) is not None
    assert login_person_for_email(db_session, SEEDED_ADMIN_EMAIL) is not None


# ── autorisatie ──────────────────────────────────────────────────────────────


def _sign_in_by_link(client, db_session, email):
    _ask(client, email)
    magic = _latest_token(db_session, email).token
    answer = client.get("/login/verify", params={"token": magic}, follow_redirects=False)
    assert SESSION_COOKIE in answer.cookies
    client.cookies.set(SESSION_COOKIE, answer.cookies[SESSION_COOKIE])


def test_a_member_does_not_enter_the_back_office(client, db_session):
    """Was `test_member_token_forbidden_on_admin_endpoint`: a member's sign-in is
    no way into the back office."""
    _seed_member(client, db_session, "lid@example.com")
    _sign_in_by_link(client, db_session, "lid@example.com")

    resp = client.get("/admin/gebruikers", follow_redirects=False)
    assert resp.status_code == 403


def test_a_member_reaches_the_members_own_page(client, db_session):
    """Was `test_member_token_reaches_the_members_own_endpoint`."""
    _seed_member(client, db_session, "lid@example.com")
    _sign_in_by_link(client, db_session, "lid@example.com")

    resp = client.get("/mijn", follow_redirects=False)
    assert resp.status_code == 200, resp.text[:200]


# ── OTP eenmalig ─────────────────────────────────────────────────────────────


def test_otp_is_single_use(client, db_session, monkeypatch):
    _fix_otp(monkeypatch)
    _ask(client, SEEDED_ADMIN_EMAIL)

    first = _code(client, SEEDED_ADMIN_EMAIL)
    assert _signed_in(first)
    client.cookies.clear()
    second = _code(client, SEEDED_ADMIN_EMAIL)
    assert not _signed_in(second)
    assert "Ongeldige of verlopen code." in second.text
