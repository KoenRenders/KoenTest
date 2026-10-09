"""#1499: the public header shows the back-office link to whoever the back
office admits — an operator too.

Koen, 2 October 2026, on HDEV: signed in on a tenant's public site with only
the platform-wide OPERATOR role, he had no link to the back office. The header
asked for ADMIN alone; `require_admin_ui` admits ADMIN or OPERATOR, and an
operator holds OPERATOR everywhere and ADMIN on no tenant (#963).

Measured on the rendered public home page. Since CR-24 the link shows for
everyone with a back-office role (Q16) and leads to the workbench (Q13); the
last test holds that the link and the workbench's gate ask one right: taken
out of a bundle, both refuse. A rule of its own in the header would stay
behind and turn it red.

Red against master: the operator saw no link, and the widened set reached
the back office but not the header.

Since #1588 (CR-11 pilot B) the link is no separate yellow "Admin" beside the
navigation: it is the item `data-account-item="admin"` of the account's one
list (`_site_account.html`), rendered twice — in the menu behind the first name
and in the drawer. Who is not admitted has no link into `/admin` on the page
at all.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text as sql

from app.domains.auth.api import (
    SESSION_COOKIE,
    User,
    UserRole,
    back_office_home,
    make_session_value,
)
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

LINK = re.compile(
    r'<a href="/admin/werkbank" hx-boost="false" data-account-item="admin"[^>]*>'
    r"(?:<svg\b.*?</svg>)?Admin</a>",
    re.S,
)


def _links(html: str) -> dict[str, int]:
    """How often the back-office link stands in the menu and in the drawer."""
    menu = html[html.index("data-account-menu") :]
    menu = menu[: menu.index("</header>")]
    drawer = html[html.index("data-drawer-account") :]
    drawer = drawer[: drawer.index("<main")]
    found = {"menu": len(LINK.findall(menu)), "drawer": len(LINK.findall(drawer))}
    assert html.count('href="/admin') == sum(found.values()), (
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


def test_boekhouding_sees_it_too(client, db_session):
    """CR-24 Q16: the link shows for everyone with a back-office role, Boekhouding
    included — until then a FINANCE-only user had payments and no link to them
    but the address itself."""
    email = _user(db_session, "finance-1499@example.com", "FINANCE")
    assert _links(_home_as(client, email)) == SHOWN
    assert back_office_home(db_session, email) == "/admin/werkbank", "the address it carries"


def test_the_link_and_the_gate_ask_one_right(client, db_session):
    """The link is there for who may open what it leads to, and for nobody else:
    the header asks the right the workbench's own gate asks. Taken out of
    Boekhouding's bundle, the workbench refuses — and the header follows without
    being told. A second rule in the header would stay behind."""
    email = _user(db_session, "finance-right-1499@example.com", "FINANCE")
    assert _links(_home_as(client, email)) == SHOWN
    assert client.get("/admin/werkbank").status_code == 200

    gone = db_session.execute(
        sql(
            "DELETE FROM auth.role_rights "
            "WHERE role_code = 'FINANCE' AND right_code = 'workbench.use'"
        )
    ).rowcount
    assert gone == 1, "Boekhouding's bundle held no workbench right — nothing was taken away"

    assert client.get("/admin/werkbank", follow_redirects=False).status_code == 403
    assert _links(_home_as(client, email)) == ABSENT, "the header kept a rule of its own"
