"""Auth/authz-randgevallen (#129): an identity that is expired, changed or made
up is nobody; and the users service refuses a role that does not exist.

Until CR-13 phase 4b (#1251) the first four held this for the bearer token of
the JSON API (an expired token, a changed signature, no token, a header that is
no token). The token left with the routes that issued it; the session cookie is
the one identity there is, so the same four hold it for the session — on the
function every screen reads it with (`read_session_value`) and on a back-office
screen.

Proven red (9 October 2026): the signature comparison taken out of
`read_session_value` → the changed signature and the changed address are read as
somebody; the expiry check taken out → the expired session is read as somebody.
"""

from __future__ import annotations

import time

import pytest
from fastapi import HTTPException

from app.domains.auth import session as auth_session
from app.domains.auth.api import SESSION_COOKIE, User, make_session_value
from app.domains.auth.session import read_session_value
from app.domains.auth.users import UserCreate, create_user
from tests.conftest import SEEDED_ADMIN_EMAIL


def _flip_middle(text: str) -> str:
    """Change a character in the middle of a signature, where every bit counts —
    the last character of an encoded signature may carry bits nobody reads."""
    middle = len(text) // 2
    other = "a" if text[middle] != "a" else "b"
    return f"{text[:middle]}{other}{text[middle + 1 :]}"


def _signed(email: str, expires: int) -> str:
    base = f"{email}|{expires}"
    return f"{base}|{auth_session._sign(base)}"


def _parts(value: str) -> tuple[str, str, str]:
    email, expires, signature = value.rsplit("|", 2)
    return email, expires, signature


# ── the session as an identity ───────────────────────────────────────────────


def test_a_session_as_it_was_made_is_read():
    """The other tests refuse; this one shows that the reader is not refusing everything."""
    assert read_session_value(make_session_value(SEEDED_ADMIN_EMAIL)) == SEEDED_ADMIN_EMAIL


def test_expired_session_is_rejected():
    """Signed with the real key, and past its time: the signature alone is not enough."""
    expired = _signed(SEEDED_ADMIN_EMAIL, int(time.time()) - 300)
    assert read_session_value(expired) is None


def test_tampered_session_is_rejected():
    email, expires, signature = _parts(make_session_value(SEEDED_ADMIN_EMAIL))
    changed = f"{email}|{expires}|{_flip_middle(signature)}"
    assert changed != f"{email}|{expires}|{signature}"
    assert read_session_value(changed) is None


def test_a_session_with_another_address_under_the_old_signature_is_rejected():
    """The signature covers the address: nobody turns his own session into an admin's."""
    _email, expires, signature = _parts(make_session_value("lid@example.com"))
    assert read_session_value(f"{SEEDED_ADMIN_EMAIL}|{expires}|{signature}") is None


def test_a_session_with_a_later_time_under_the_old_signature_is_rejected():
    """The signature covers the expiry too: nobody gives his session more time."""
    email, expires, signature = _parts(make_session_value(SEEDED_ADMIN_EMAIL))
    assert read_session_value(f"{email}|{int(expires) + 86_400}|{signature}") is None


@pytest.mark.parametrize(
    "cookie", ["", "not-a-session", "a|b", f"{SEEDED_ADMIN_EMAIL}|9999999999|", "a|b|c|d"]
)
def test_garbage_session_is_rejected(cookie):
    assert read_session_value(cookie) is None


@pytest.mark.parametrize("which", ["none", "garbage", "expired", "tampered"])
def test_a_back_office_screen_asks_for_a_sign_in_without_a_valid_session(client, which):
    """On the screen itself: no identity, no way in — the visitor is sent to sign in."""
    good = make_session_value(SEEDED_ADMIN_EMAIL)
    email, expires, signature = _parts(good)
    cookie = {
        "none": None,
        "garbage": "not-a-session",
        "expired": _signed(SEEDED_ADMIN_EMAIL, int(time.time()) - 300),
        "tampered": f"{email}|{expires}|{_flip_middle(signature)}",
    }[which]
    if cookie is not None:
        client.cookies.set(SESSION_COOKIE, cookie)
    answer = client.get("/admin/gebruikers", follow_redirects=False)
    assert answer.status_code == 303
    assert answer.headers["location"].startswith("/aanmelden")
    # And the same screen opens for the session as it was made.
    client.cookies.set(SESSION_COOKIE, good)
    assert client.get("/admin/gebruikers", follow_redirects=False).status_code == 200


# ── autorisatie in het gebruikersbeheer ──────────────────────────────────────


def test_create_user_rejects_unknown_role_code(db_session):
    """Sinds migratie 076 is er geen FK meer naar public.role_codes (§8);
    de servicelaag moet onbekende rolcodes met een nette 400 weigeren.

    Until CR-13 phase 4b this asked the JSON route `POST /api/v1/users`; it asks the
    function behind it, which the users screen calls."""
    with pytest.raises(HTTPException) as refused:
        create_user(UserCreate(email="nieuwe@example.com", role_codes=["NEPROL"]), db_session)
    assert refused.value.status_code == 400
    assert "NEPROL" in refused.value.detail
    db_session.rollback()
    assert db_session.query(User).filter(User.email == "nieuwe@example.com").first() is None
