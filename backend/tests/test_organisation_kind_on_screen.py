"""What the organisation kind decided on the screens (CR-12 phase 2 remainder),
and what is left of it since CR-20.

Phase 2 made `Organization.org_type` an `OrganizationType` member, and four
screens kept comparing it with a string. CR-20 (#1578) took the kind off the
organisation: a tenant is its own record, an organisation is a party, and a role
is read from the tenants that name it. Of the four, two still decide something:

| Screen | What it decides | Broken as |
|---|---|---|
| organisation record | the link to the site settings | gone, or to an editor of the same id |
| tenant list | the platform's kind badge (#1533), the code without a slash | the platform as `/platform` |

The list badge, the kind filter and the word "Account" (#1945) went with the
column; their tests went with them.
"""

import pytest
from sqlalchemy import text

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.auth.models import User, UserRole
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client, db, *, operator: bool = False):
    if operator:
        user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
        if not db.query(UserRole).filter_by(user_id=user.id, role_code="OPERATOR").first():
            db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
            db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _row(html: str, organisation_id: int) -> str:
    """The `<tr>` of this organisation's row on the kit's table (#1932)."""
    at = html.index(f'data-organisation="{organisation_id}"')
    return html[html.rindex("<tr", 0, at) : html.index("</tr>", at)]


def test_the_editor_of_a_unit_links_to_its_site_settings(client, platform_workspace, db_session):
    _login(client, db_session)
    millegem = db_session.execute(
        text("SELECT id, organization_id, account_id FROM mdm.tenants WHERE code = 'raakmillegem'")
    ).one()

    shown = client.get(f"/admin/organisaties/{millegem.organization_id}").text
    assert f'href="/admin/tenants/{millegem.id}"' in shown
    assert "/admin/tenants/" not in client.get(f"/admin/organisaties/{millegem.account_id}").text, (
        "no tenant shows the account; a link there would end on another site"
    )


def test_the_tenant_list_marks_the_platform(client, platform_workspace, db_session):
    _login(client, db_session, operator=True)
    html = client.get("/admin/tenants").text
    code = db_session.execute(
        text("SELECT code FROM mdm.tenants WHERE kind = 'PLATFORM'")
    ).scalar_one()

    # #1933: the code stands under the name in the row (`ui.row_link`'s sub).
    assert f">{code}</small>" in html and f">/{code}</small>" not in html, (
        "the platform opens no site, so its code carries no slash"
    )
    # #1533: one badge, the kind's; the old blue "platform" badge is gone.
    # `>platform</span>` once: the code itself (its code is "platform"), no second badge.
    assert html.count(">Platform</td>") == 1 and html.count(">platform</small>") == 1
