"""#1533 (CR-19) — the operator changes a tenant's kind in the tenant editor.

Between VERENIGING and BEDRIJF, with the editor's one Opslaan, through
`save_tenant`. The modules do not follow the new kind; the change is written to
the application log (there is no history table for tenants or organisations).
PLATFORM is never offered, and the platform's own kind cannot be changed.

Added by Koen: the account the tenant hangs under changes in the same place,
chosen from the active accounts, logged the same way; the platform landing of
#1525 then lists the tenant under its new account.

Red against master: the editor showed the kind as text and ignored a posted
`kind`, so the BEDRIJF stayed a BEDRIJF and its header kept its name.

Since #1588 (CR-11 pilot B, decision 11: no typed wordmark) the header shows
the tenant's name for an association too, so it no longer tells the two kinds
apart. What the public site still says differently per kind is the heading of
the sponsor column in the footer — "Partners" for a company, "Met steun van"
for an association — and that is what the first test reads now.
"""

from __future__ import annotations

import logging
import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.mdm.api import (
    Tenant,
    TenantKind,
    create_organization,
    enabled_modules,
)
from app.domains.media.api import MediaAsset, MediaKind
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from tests._sites import as_account, new_site

pytestmark = pytest.mark.ui_serverrendered

COMPANY = {"cms", "media", "forms"}
# The typed RaaK wordmark of before #1588, as test_company_wordmark reads it: gone.
RAAK = re.compile(r'aria-label="Raak">R<span class="text-\[1\.3em\]">aa</span>K</span>')


def _home(client) -> str:
    # #1535: the test runs on the platform host; Raak Millegem is reached by its prefix.
    html = client.get("/raakmillegem/").text
    # The prefix sets the workspace cookie (#889), which would win on the platform
    # host for the next request; this test goes on as the operator on the platform.
    client.cookies.delete("raak_tenant")
    return html


def _home_header(html: str) -> str:
    start = html.index("<header")
    return html[start : html.index("</header>", start)]


def _sponsor_heading(html: str) -> str:
    """The heading of the footer's sponsor column — the words follow the kind."""
    column = html[html.index("data-footer-sponsors") :]
    return re.search(r"<h2>([^<]*)</h2>", column).group(1)


def _footer_sponsor(db) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    asset = MediaAsset(
        kind=MediaKind.SPONSOR,
        data=png,
        content_type="image/png",
        byte_size=len(png),
        title="sponsor",
        sort_order=0,
        is_active=True,
        show_in_footer=True,
    )
    asset.tenant_id = TENANT_MILLEGEM_ID
    db.add(asset)


def _login(client, db, email: str, role: str) -> str:
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code=role))
    db.commit()
    session = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, session)
    return csrf_token_for(session)


def _save(client, csrf: str, tenant_id: int, **data):
    return client.post(
        f"/admin/tenants/{tenant_id}",
        data=data,
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )


def _company(db) -> Tenant:
    org = new_site(db, name="Bakkerij Soort", code="soort-1533", kind=TenantKind.COMPANY)
    db.commit()
    return org


def test_an_operator_makes_a_company_an_association(client, platform_workspace, db_session, caplog):
    # The default tenant, so the public header is served on "/" (as #1496 measures it).
    org = db_session.get(Tenant, TENANT_MILLEGEM_ID)
    org.kind = TenantKind.COMPANY
    org.site_name = "Bakkerij Soort"
    _footer_sponsor(db_session)
    db_session.commit()
    modules_before = enabled_modules(org.id, db=db_session)
    before = _home(client)
    assert 'aria-label="Bakkerij Soort"' in _home_header(before), "a company shows its name"
    assert _sponsor_heading(before) == "Partners", "a company has partners"
    csrf = _login(client, db_session, "operator-1533@example.com", "OPERATOR")

    editor = client.get(f"/admin/tenants/{org.id}?bewerken=1").text
    # #1933: the type is a select (it was a row of chips).
    choice = editor[editor.index('name="kind"') :]
    choice = choice[: choice.index("</select>")]
    assert 'value="VERENIGING"' in choice and 'value="BEDRIJF"' in choice
    assert 'value="PLATFORM"' not in choice
    assert "De modules blijven zoals ze zijn" in editor

    with caplog.at_level(logging.INFO, logger="app.domains.mdm.tenant_service"):
        saved = _save(
            client,
            csrf,
            org.id,
            kind="VERENIGING",
            modules_shown="1",
            modules=sorted(modules_before),
        )
    assert saved.status_code == 200, saved.text[-500:]
    db_session.expire_all()
    assert db_session.get(Tenant, org.id).kind is TenantKind.ASSOCIATION
    assert enabled_modules(org.id, db=db_session) == modules_before, "the modules stay"
    logged = [r.getMessage() for r in caplog.records if "tenant kind changed" in r.getMessage()]
    assert logged == [
        f"tenant kind changed: tenant={org.id} code=raakmillegem BEDRIJF -> VERENIGING "
        "by operator-1533@example.com"
    ]

    client.cookies.clear()
    after = _home(client)
    assert _sponsor_heading(after) == "Met steun van", "the public site follows the new kind"
    header = _home_header(after)
    # #1588: an association shows its name as well; the typed wordmark is gone.
    assert 'aria-label="Bakkerij Soort">Bakkerij Soort</span>' in header
    assert not RAAK.search(header)


def test_platform_is_never_chosen_and_the_platforms_kind_is_fixed(
    client, platform_workspace, db_session
):
    org = _company(db_session)
    csrf = _login(client, db_session, "operator2-1533@example.com", "OPERATOR")

    refused = _save(client, csrf, org.id, kind="PLATFORM")
    assert refused.status_code == 422
    assert "Kies het type: vereniging of bedrijf." in refused.text
    db_session.expire_all()
    assert db_session.get(Tenant, org.id).kind is TenantKind.COMPANY

    platform = db_session.query(Tenant).filter(Tenant.kind == TenantKind.PLATFORM).one()
    assert 'name="kind"' not in client.get(f"/admin/tenants/{platform.id}?bewerken=1").text
    refused = _save(client, csrf, platform.id, kind="VERENIGING")
    assert refused.status_code == 422
    assert "Het type van het platform ligt vast." in refused.text
    db_session.expire_all()
    assert db_session.get(Tenant, platform.id).kind is TenantKind.PLATFORM


def test_an_admin_cannot_change_a_kind(client, platform_workspace, db_session):
    org = _company(db_session)
    csrf = _login(client, db_session, "admin-1533@example.com", "ADMIN")
    assert _save(client, csrf, org.id, kind="VERENIGING").status_code == 403
    db_session.expire_all()
    assert db_session.get(Tenant, org.id).kind is TenantKind.COMPANY


def test_an_existing_tenant_never_changes_its_account(client, platform_workspace, db_session):
    """CR-26: a tenant's parties are its account's, so a tenant never moves
    (Koen, 19 October 2026, to whether an empty tenant may still move: "1").
    The editor shows the account as a fact, for a unit and for the platform; an
    account posted all the same is refused and nothing changes. Until CR-26 the
    operator could move a tenant (#1533) and hang the platform under an account
    (#1542); that went with this rule."""
    other = create_organization(db_session, name="Ander Account")
    org = _company(db_session)
    platform = _the_platform(db_session)
    before = {org.id: org.account_id, platform.id: platform.account_id}
    csrf = _login(client, db_session, "operator4-1533@example.com", "OPERATOR")

    for tenant_id in (org.id, platform.id):
        editor = client.get(f"/admin/tenants/{tenant_id}?bewerken=1").text
        assert 'data-setting="account_id"' in editor and 'name="account_id"' not in editor
        refused = _save(client, csrf, tenant_id, account_id=str(other.id))
        assert refused.status_code == 422
        assert "Het account van een bestaande tenant verandert niet." in refused.text
        db_session.expire_all()
        assert db_session.get(Tenant, tenant_id).account_id == before[tenant_id]


def _the_platform(db) -> Tenant:
    return db.query(Tenant).filter(Tenant.kind == TenantKind.PLATFORM).one()


def test_an_admin_cannot_change_the_platforms_account(client, platform_workspace, db_session):
    account = create_organization(db_session, name="Account Vier")
    db_session.commit()
    platform = _the_platform(db_session)
    account_before = platform.account_id
    csrf = _login(client, db_session, "admin-1542@example.com", "ADMIN")
    assert _save(client, csrf, platform.id, account_id=str(account.id)).status_code == 403
    db_session.expire_all()
    assert _the_platform(db_session).account_id == account_before


def test_the_tenant_list_shows_each_sites_account(client, platform_workspace, db_session):
    """#1542 (Koen): an account badge beside the kind badge, the platform's too.
    Since CR-20 every site has an account; a site that is its own account names
    itself there."""
    account = create_organization(db_session, name="Account Zeven")
    new_site(db_session, name="Zevenclub", code="zevenclub-1542", account_id=account.id)
    new_site(db_session, name="Losse Zeven", code="los-zeven-1542")
    platform = _the_platform(db_session)
    platform.account_id = as_account(db_session, account)
    db_session.commit()
    _login(client, db_session, "operator7-1542@example.com", "OPERATOR")

    html = client.get("/admin/tenants").text

    def card(name: str) -> str:
        # #1933: the tenant's row of the kit's table, not the sidebar brand.
        start = html.rindex("<tr", 0, html.index(f">{name}</a>"))
        return html[start : html.index("</tr>", start)]

    assert "Account Zeven" in card("Zevenclub")
    assert "Account Zeven" in card(platform.name), "the platform's account too"
    assert "Account" not in card("Losse Zeven"), "its own account, not another's"
