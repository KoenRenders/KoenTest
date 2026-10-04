"""#1536 — the workspace switch route sets or clears the workspace, and only
into a workspace the account has a role in.

A department is chosen by its path prefix (which sets the `raak_tenant` cookie,
#889); the platform by clearing that cookie, because on a platform host it wins
over the platform. Any other id is a 404, the same answer as a workspace that
does not exist.

Red against master: the route did not exist.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.mdm.api import platform_tenant_id
from app.kernel.tenancy import TENANT_MILLEGEM_ID

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db, email: str, role: str, tenant_id: int | None) -> None:
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code=role, tenant_id=tenant_id))
    db.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(email))


def test_the_operator_switches_to_the_platform_and_the_cookie_is_cleared(client, db_session):
    _login(client, db_session, "operator-1536@example.com", "OPERATOR", None)
    platform = platform_tenant_id(db_session)

    to_platform = client.get(f"/admin/werkruimte-wisselen/{platform}", follow_redirects=False)
    assert to_platform.status_code == 303
    assert to_platform.headers["location"] == "/admin"
    cleared = to_platform.headers.get("set-cookie", "")
    assert cleared.startswith("raak_tenant=") and "Max-Age=0" in cleared, cleared

    to_unit = client.get(f"/admin/werkruimte-wisselen/{TENANT_MILLEGEM_ID}", follow_redirects=False)
    assert to_unit.status_code == 303
    assert to_unit.headers["location"] == "/raakmillegem/admin"


def test_the_switcher_links_the_platform_through_the_route(client, db_session):
    _login(client, db_session, "operator2-1536@example.com", "OPERATOR", None)
    page = client.get("/admin/werkruimte-wisselen").text
    assert f'/admin/werkruimte-wisselen/{platform_tenant_id(db_session)}"' in page
    assert 'href="/raakmillegem/admin"' in page, "a department keeps its prefix link"


def test_no_switch_into_a_workspace_without_a_role(client, db_session):
    _login(client, db_session, "admin-1536@example.com", "ADMIN", TENANT_MILLEGEM_ID)
    platform = platform_tenant_id(db_session)
    refused = client.get(f"/admin/werkruimte-wisselen/{platform}", follow_redirects=False)
    assert refused.status_code == 404
    assert "set-cookie" not in refused.headers or "raak_tenant" not in refused.headers["set-cookie"]
    own = client.get(f"/admin/werkruimte-wisselen/{TENANT_MILLEGEM_ID}", follow_redirects=False)
    assert own.status_code == 303
