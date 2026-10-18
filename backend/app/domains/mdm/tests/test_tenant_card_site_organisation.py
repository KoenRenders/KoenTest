"""#1554 — a tenant card names the organisation behind the site when it is not its own.

Since #1550 a tenant's site may show another organisation of its account, and the
card under Tenants did not tell. Now such a card carries a grey line under the
tenant's name, "Organisatie: <name>" — a line, not a badge, so it is not taken
for the blue account badge. The name is asked of the resolver the footer uses
(`site_organization_id`), so the card follows a rename of that organisation.
Since CR-20 (F5) every tenant names the organisation it shows, its own party
included: "its own data" was the row whose id was the tenant's, and that
equality no longer means anything.

Red against master `65a7bd78`: the first test finds no `data-site-org` line.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.mdm.api import Tenant, create_organization, save_organization
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
    """The tenant's row of the list (#1933: the kit's table)."""
    start = html.index(f'data-tenant="{tenant_id}"')
    return html[start : html.index("</tr>", start)]


def test_a_tenant_on_its_accounts_data_names_that_organisation(
    client, platform_workspace, db_session
):
    account = create_organization(db_session, name="Account Vier")
    brand = db_session.get(Tenant, TENANT_VOORBEELD_ID)
    brand.account_id = account.id
    brand.organization_id = account.id
    db_session.commit()
    _operator(client, db_session)

    card = _card(client.get("/admin/tenants").text, brand.id)

    # #1933: the list is the kit's table — the organisation stands in its own
    # column, "Organisatie achter de site", after the tenant's name and code.
    assert card.count("data-site-org") == 1
    cell_at = card.index("data-site-org")
    assert "Account Vier" in card[cell_at : card.index("</td>", cell_at)]
    assert card.index(brand.name) < card.index("data-row-sub") < cell_at

    # The resolver's name, not a copy: a rename of the organisation reaches the card.
    save_organization(db_session, account.id, {"name": "Account Vijf"})
    db_session.commit()
    card = _card(client.get("/admin/tenants").text, brand.id)
    cell_at = card.index("data-site-org")
    assert "Account Vijf" in card[cell_at : card.index("</td>", cell_at)]
    assert "Account Vier" not in card


def test_every_tenant_names_the_organisation_it_shows(client, platform_workspace, db_session):
    """CR-20 F5: every tenant shows an organisation — its own party, its account
    or another of the account — so the column is filled for every row. Until
    CR-20 a tenant on "its own data" (the row whose id was its own) left it
    empty; a tenant id and an organisation id are keys of two tables now, and
    nothing may lean on them being equal (C4.1)."""
    account = create_organization(db_session, name="Account Vier")
    brand = db_session.get(Tenant, TENANT_VOORBEELD_ID)
    brand.account_id = account.id
    db_session.commit()
    _operator(client, db_session)

    html = client.get("/admin/tenants").text

    own = _card(html, brand.id)
    cell_at = own.index("data-site-org")
    assert "Raak Voorbeeldafdeling" in own[cell_at : own.index("</td>", cell_at)]
    assert "data-site-org" in _card(html, TENANT_MILLEGEM_ID)
    # The account badge is still there: the column is not what shows the account.
    assert "Account Vier" in own
