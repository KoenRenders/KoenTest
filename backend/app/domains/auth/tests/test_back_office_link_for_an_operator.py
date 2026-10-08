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

Since #1588 (CR-11 pilot B) the link is no separate yellow "Admin" beside the
navigation: it is the item `data-account-item="admin"` of the account's one
list (`_site_account.html`), rendered twice — in the menu behind the first name
and in the drawer. Who is not admitted has no link to `/admin` on the page at
all.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth import session as auth_session
from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

LINK = re.compile(
    r'<a href="/admin" hx-boost="false" data-account-item="admin"[^>]*>(?:<svg\b.*?</svg>)?Admin</a>',
    re.S,
)


def _links(html: str) -> dict[str, int]:
    """How often the back-office link stands in the menu and in the drawer."""
    menu = html[html.index("data-account-menu") :]
    menu = menu[: menu.index("</header>")]
    drawer = html[html.index("data-drawer-account") :]
    drawer = drawer[: drawer.index("<main")]
    found = {"menu": len(LINK.findall(menu)), "drawer": len(LINK.findall(drawer))}
    assert html.count('href="/admin"') == sum(found.values()), (
        "a link to the back office stands outside the account's list"
    )
    return found


SHOWN = {"menu": 1, "drawer": 1}
ABSENT = {"menu": 0, "drawer": 0}


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

    assert _links(_home_as(client, email)) == SHOWN, "an operator has no way into the back office"


def test_an_admin_still_sees_it(client, db_session):
    email = _user(db_session, "admin-1499@example.com", "ADMIN")

    assert _links(_home_as(client, email)) == SHOWN


def test_a_member_without_a_role_does_not(client, db_session):
    create_test_family(db_session, email="lid-1499@example.com")
    db_session.commit()

    html = _home_as(client, "lid-1499@example.com")

    assert "/leden/gezin" in html, "the member's own link is there, so the header rendered for them"
    assert _links(html) == ABSENT, "a member without a back-office role sees the back-office link"
    assert 'data-account-item="admin"' not in html
    # CR-22 S3 and S6a (#1706, #1710): the account menu is "Mijn <site>", Mijn
    # gegevens and Mijn gezin — each in the menu and in the drawer.
    assert html.count('data-account-item="member"') == 8, "four items, in the menu and the drawer"


def test_the_link_and_the_guard_read_one_set(client, db_session, monkeypatch):
    """Widen `require_admin_ui`'s set by FINANCE: a FINANCE-only user now
    passes the guard — and the header follows without being told."""
    email = _user(db_session, "finance-1499@example.com", "FINANCE")
    assert _links(_home_as(client, email)) == ABSENT, "FINANCE alone is not admitted today"

    monkeypatch.setattr(auth_session, "_GENERAL_ADMIN_ROLES", {"ADMIN", "OPERATOR", "FINANCE"})

    # A screen behind `require_admin_ui` alone (`/admin/gebruikers` adds a
    # check of its own with a literal copy of the set).
    assert client.get("/admin/design-system").status_code == 200, "the guard reads the widened set"
    assert _links(_home_as(client, email)) == SHOWN, "the header kept its own copy of the set"
