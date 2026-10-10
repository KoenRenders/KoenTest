"""#1513: every place that asks "may this person into the back office" reads the
one set `require_admin_ui` checks, through `auth.admits_admin_ui` (#1499).

The JSON API's `/auth/me` said `is_admin = "ADMIN" in roles`, so an operator —
OPERATOR on every tenant, ADMIN on none — was no admin there: the same gap as
the public header of #1499, on the API side. Red against master on the
operator. The users screen's check, `landing_for` and `admin_nav`'s cut for
FINANCE derived from the same set; `tests/test_role_set_gate.py` held that no
module spelled it out again, until the set itself went with CR-24.

`/auth/me` left with the bearer token (CR-13 phase 4b, #1251). What it was
repaired to say is asked here where every screen asks it: the roles of the
address, through `admits_admin_ui` — and the users screen admits or refuses
the same people.

Since CR-24 (#1722) there is no set of roles to keep in one place: the
question is a right (`may`), the gate asks the same right, and what a role
holds is its bundle. The test holds what #1513 was about — the question
and the gate agree, for the operator too.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import (
    SESSION_COOKIE,
    Right,
    User,
    UserRole,
    make_session_value,
    may,
)


def _user(db, email: str, *roles: str) -> str:
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    for role in roles:
        db.add(UserRole(user_id=user.id, role_code=role))
    db.commit()
    return email


def _enters_the_back_office(client, email: str) -> bool:
    """Signed in as this address, does the users screen open?"""
    client.cookies.set(SESSION_COOKIE, make_session_value(email))
    status = client.get("/admin/gebruikers", follow_redirects=False).status_code
    assert status in (200, 403), status
    return status == 200


@pytest.mark.parametrize(
    "roles,admin",
    [(("OPERATOR",), True), (("ADMIN",), True), (("FINANCE",), False)],
)
def test_is_admin_is_who_the_back_office_admits(client, db_session, roles, admin):
    email = _user(db_session, f"{'-'.join(roles).lower()}-1513@example.com", *roles)

    assert may(db_session, email, Right.USER_VIEW) is admin, roles
    assert _enters_the_back_office(client, email) is admin, roles


def test_an_operator_enters_the_back_office_by_its_start_page(db_session):
    """#1740: the sign-in no longer lands anyone in the back office; which page
    a user enters it by is the back office's own answer — the workbench, for
    everyone with a back-office role (CR-24 Q13), an operator like anyone."""
    from app.domains.auth.api import back_office_home

    email = _user(db_session, "operator-landing-1513@example.com", "OPERATOR")

    assert back_office_home(db_session, email) == "/admin/werkbank"
