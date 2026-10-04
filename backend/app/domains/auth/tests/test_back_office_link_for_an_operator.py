"""#1499: the public header shows the back-office link to whoever the back
office admits — an operator too.

Koen, 2 October 2026, on HDEV: signed in on a tenant's public site with only
the platform-wide OPERATOR role, he had no link to the back office. The header
asked for ADMIN alone; `require_admin_ui` admits ADMIN or OPERATOR, and an
operator holds OPERATOR everywhere and ADMIN on no tenant (#963).

Measured on the rendered public home page. The last test holds that the link
and `require_admin_ui` read one set: widened by one role, both admit it. A
second copy of the set in the header would stay behind and turn it red.

Red against master: the operator saw no link, and the widened set reached
the back office but not the header.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth import session as auth_session
from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

LINK = re.compile(r'<a href="/admin" hx-boost="false"[^>]*>\s*Admin\s*</a>')


def _user(db, email: str, *roles: str) -> str:
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    for role in roles:
        db.add(UserRole(user_id=user.id, role_code=role))
    db.commit()
    return email


def _home_as(client, email: str) -> str:
    client.cookies.set(SESSION_COOKIE, make_session_value(email))
    response = client.get("/")
    assert response.status_code == 200
    assert "Uitloggen" in response.text, "the visitor is signed in, else this proves nothing"
    return response.text


def test_an_operator_sees_the_back_office_link(client, db_session):
    email = _user(db_session, "operator-1499@example.com", "OPERATOR")

    assert LINK.search(_home_as(client, email)), "an operator has no way into the back office"


def test_an_admin_still_sees_it(client, db_session):
    email = _user(db_session, "admin-1499@example.com", "ADMIN")

    assert LINK.search(_home_as(client, email))


def test_a_member_without_a_role_does_not(client, db_session):
    create_test_family(db_session, email="lid-1499@example.com")
    db_session.commit()

    html = _home_as(client, "lid-1499@example.com")

    assert "/leden/gezin" in html, "the member's own link is there, so the header rendered for them"
    assert not LINK.search(html), "a member without a back-office role sees the back-office link"


def test_the_link_and_the_guard_read_one_set(client, db_session, monkeypatch):
    """Widen `require_admin_ui`'s set by FINANCE: a FINANCE-only user now
    passes the guard — and the header follows without being told."""
    email = _user(db_session, "finance-1499@example.com", "FINANCE")
    assert not LINK.search(_home_as(client, email)), "FINANCE alone is not admitted today"

    monkeypatch.setattr(auth_session, "_GENERAL_ADMIN_ROLES", {"ADMIN", "OPERATOR", "FINANCE"})

    # A screen behind `require_admin_ui` alone (`/admin/gebruikers` adds a
    # check of its own with a literal copy of the set).
    assert client.get("/admin/design-system").status_code == 200, "the guard reads the widened set"
    assert LINK.search(_home_as(client, email)), "the header kept its own copy of the set"
