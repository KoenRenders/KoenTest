"""#1554 — a tenant card names the organisation behind the site when it is not its own.

Since #1550 a tenant's site may show another organisation of its account, and the
card under Tenants did not tell. Now such a card carries a grey line under the
tenant's name, "Organisatie: <name>" — a line, not a badge, so it is not taken
for the blue account badge. The name is asked of the resolver the footer uses
(`site_organization_id`), so the card follows a rename of that organisation. A
tenant on its own data shows nothing new.

Red against master `65a7bd78`: the first test finds no `data-site-org` line.
Additive counter-proof on this branch: with the `if` around the line taken out
of the template, the second test fails (every card would carry a line).
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.mdm.api import Organization, create_account, save_organization
from app.kernel.tenancy import TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID

pytestmark = pytest.mark.ui_serverrendered


def _operator(client, db) -> None:
    email = "operator-1554@example.com"
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="OPERATOR", tenant_id=None))
    db.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(email))


def _card(html: str, tenant_id: int) -> str:
    start = html.index(f'href="/admin/tenants/{tenant_id}"')
    return html[start : html.index("</a>", start)]


def test_a_tenant_on_its_accounts_data_names_that_organisation(
    client, platform_workspace, db_session
):
    account = create_account(db_session, name="Account Vier", code="vier-1554")
    brand = db_session.get(Organization, TENANT_VOORBEELD_ID)
    brand.parent_id = account.id
    brand.site_organization_id = account.id
    db_session.commit()
    _operator(client, db_session)

    card = _card(client.get("/admin/tenants").text, brand.id)

    assert card.count("data-site-org") == 1
    line_at = card.index("data-site-org")
    assert "Organisatie: Account Vier" in card[line_at : card.index("</div>", line_at)]
    # Under the name, above the row of badges.
    assert card.index(brand.name) < line_at < card.index("font-mono")

    # The resolver's name, not a copy: a rename of the organisation reaches the card.
    save_organization(db_session, account.id, {"name": "Account Vijf"})
    db_session.commit()
    card = _card(client.get("/admin/tenants").text, brand.id)
    assert "Organisatie: Account Vijf" in card and "Account Vier" not in card.split("font-mono")[0]


def test_a_tenant_on_its_own_data_shows_no_such_line(client, platform_workspace, db_session):
    account = create_account(db_session, name="Account Vier", code="vier-1554-eigen")
    brand = db_session.get(Organization, TENANT_VOORBEELD_ID)
    brand.parent_id = account.id
    db_session.commit()
    _operator(client, db_session)

    html = client.get("/admin/tenants").text

    assert "data-site-org" not in html
    assert "Organisatie:" not in _card(html, brand.id)
    assert "Organisatie:" not in _card(html, TENANT_MILLEGEM_ID)
    # The account badge is still there: the line is not what shows the account.
    assert "Account Vier" in _card(html, brand.id)
