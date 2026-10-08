"""#1513: every place that asks "may this person into the back office" reads the
one set `require_admin_ui` checks, through `auth.admits_admin_ui` (#1499).

The JSON API's `/auth/me` said `is_admin = "ADMIN" in roles`, so an operator —
OPERATOR on every tenant, ADMIN on none — was no admin there: the same gap as
the public header of #1499, on the API side. Red against master on the
operator. The users screen's check, `landing_for` and `admin_nav`'s cut for
FINANCE derive from the same set; `tests/test_role_set_gate.py` holds that no
module spells it out again.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import User, UserRole, create_access_token


def _user(db, email: str, *roles: str) -> str:
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    for role in roles:
        db.add(UserRole(user_id=user.id, role_code=role))
    db.commit()
    return email


def _me(client, email: str) -> dict:
    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {create_access_token({'sub': email})}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.parametrize(
    "roles,admin",
    [(("OPERATOR",), True), (("ADMIN",), True), (("FINANCE",), False)],
)
def test_is_admin_is_who_the_back_office_admits(client, db_session, roles, admin):
    email = _user(db_session, f"{'-'.join(roles).lower()}-1513@example.com", *roles)

    assert _me(client, email)["is_admin"] is admin, roles


def test_an_operator_enters_the_back_office_by_its_start_page(db_session):
    """#1740: the sign-in no longer lands anyone in the back office; which page
    a role enters it by is the back office's own answer — and an operator, who
    holds OPERATOR and no ADMIN, gets the start page like an administrator."""
    from app.domains.auth.api import back_office_home, get_user_roles

    email = _user(db_session, "operator-landing-1513@example.com", "OPERATOR")

    assert back_office_home(get_user_roles(db_session, email)) == "/admin"
