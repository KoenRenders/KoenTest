"""#1500: Gebruikers per workspace, the boundary between workspaces, and the
operator's overview of every workspace.

Koen, 2 October 2026, on HDEV: a new company's Gebruikers listed people with no
role there. The list showed every account in the system (`list_users`); the
access itself was right — `get_user_roles` reads only this workspace's rows and
the platform-wide ones. These tests prove both halves on requests:

- in workspace B, Gebruikers lists exactly B's role holders and the platform-wide
  ones (the operator), and an ADMIN of A is not among them;
- an ADMIN of A gets 403 on a back-office screen of B;
- the overview of every (account, workspace, role) is 403 for an ADMIN and lists
  every row for an OPERATOR.

Workspace A is Raak Millegem (the test client's default), B the sample unit,
reached by its path prefix. Red against master: B's list held every account.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.kernel.tenancy import TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID

pytestmark = pytest.mark.ui_serverrendered

B = "/raakvoorbeeldafdeling"
EMAILS_IN_LIST = re.compile(
    r'id="gu-email-\d+"[^>]*value="([^"]+)"|value="([^"]+)"[^>]*id="gu-email-\d+"'
)


def _user(db, email: str, *roles: tuple[str, int | None]) -> str:
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    for code, tenant in roles:
        db.add(UserRole(user_id=user.id, role_code=code, tenant_id=tenant))
    db.commit()
    return email


def _as(client, email: str) -> None:
    client.cookies.set(SESSION_COOKIE, make_session_value(email))


def _listed(html: str) -> set[str]:
    return {a or b for a, b in EMAILS_IN_LIST.findall(html)}


@pytest.fixture
def two_workspaces(db_session):
    return {
        "admin_a": _user(db_session, "admin-a-1500@example.com", ("ADMIN", TENANT_MILLEGEM_ID)),
        "admin_b": _user(db_session, "admin-b-1500@example.com", ("ADMIN", TENANT_VOORBEELD_ID)),
        "finance_b": _user(
            db_session, "finance-b-1500@example.com", ("FINANCE", TENANT_VOORBEELD_ID)
        ),
        "operator": _user(db_session, "operator-1500@example.com", ("OPERATOR", None)),
        "nobody": _user(db_session, "geen-rol-1500@example.com"),
    }


def test_b_lists_its_role_holders_and_the_operator(client, db_session, two_workspaces):
    _as(client, two_workspaces["admin_b"])
    html = client.get(f"{B}/admin/gebruikers").text
    listed = _listed(html)

    expected = {
        u.email
        for u in db_session.query(User).all()
        if any(r.tenant_id is None or r.tenant_id == TENANT_VOORBEELD_ID for r in u.roles)
    }
    assert {two_workspaces[k] for k in ("admin_b", "finance_b", "operator")} <= expected
    assert listed == expected, f"listed {sorted(listed)}, expected {sorted(expected)}"
    assert two_workspaces["admin_a"] not in listed, "an ADMIN of A is listed in B"
    assert two_workspaces["nobody"] not in listed
    assert "OPERATOR · alle werkruimtes" in html, "the platform-wide role is marked as such"


def test_an_admin_of_a_gets_403_in_b(client, two_workspaces):
    _as(client, two_workspaces["admin_a"])

    assert client.get("/admin/activiteiten").status_code == 200, "A's ADMIN works in A"
    assert client.get(f"{B}/admin/activiteiten").status_code == 403
    assert client.get(f"{B}/admin/gebruikers").status_code == 403


def test_the_overview_is_the_operators_and_lists_every_row(
    client, platform_workspace, db_session, two_workspaces
):
    _as(client, two_workspaces["admin_a"])
    assert client.get("/admin/gebruikers/alle-werkruimtes").status_code == 403

    _as(client, two_workspaces["operator"])
    html = client.get("/admin/gebruikers/alle-werkruimtes").text

    every = db_session.query(UserRole).execution_options(include_all_tenants=True).all()
    assert html.count("data-access-row") == len(every), "one table row per stored role row"
    for key, workspace in (
        ("admin_a", "Raak Millegem"),
        ("admin_b", None),
        ("operator", "Alle werkruimtes"),
    ):
        row = re.search(
            rf"<tr[^>]*data-access-row>\s*<td[^>]*>{re.escape(two_workspaces[key])}</td>(.*?)</tr>",
            html,
            re.S,
        )
        assert row, f"{two_workspaces[key]} has no row in the overview"
        if workspace:
            assert workspace in row.group(1), (key, row.group(1))
