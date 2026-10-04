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
"""

from __future__ import annotations

import logging
import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.mdm.api import (
    Organization,
    OrganizationType,
    TenantKind,
    create_account,
    create_tenant,
    enabled_modules,
)
from app.kernel.tenancy import TENANT_MILLEGEM_ID

pytestmark = pytest.mark.ui_serverrendered

COMPANY = {"cms", "media", "forms", "workflow"}
# The association's wordmark without a logo (#1496), as test_company_wordmark reads it.
RAAK = re.compile(r'aria-label="Raak">R<span class="text-\[1\.3em\]">aa</span>K</span>')


def _home_header(client) -> str:
    html = client.get("/").text
    start = html.index("<header")
    return html[start : html.index("</header>", start)]


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


def _company(db) -> Organization:
    org = create_tenant(db, name="Bakkerij Soort", code="soort-1533", kind=TenantKind.COMPANY)
    db.commit()
    return org


def test_an_operator_makes_a_company_an_association(client, db_session, caplog):
    # The default tenant, so the public header is served on "/" (as #1496 measures it).
    org = db_session.get(Organization, TENANT_MILLEGEM_ID)
    org.kind = TenantKind.COMPANY
    org.name = "Bakkerij Soort"
    db_session.commit()
    modules_before = enabled_modules(org.id, db=db_session)
    assert 'aria-label="Bakkerij Soort"' in _home_header(client), "a company shows its name"
    csrf = _login(client, db_session, "operator-1533@example.com", "OPERATOR")

    editor = client.get(f"/admin/tenants/{org.id}").text
    assert 'name="kind" value="VERENIGING"' in editor and 'name="kind" value="BEDRIJF"' in editor
    assert 'name="kind" value="PLATFORM"' not in editor
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
    assert db_session.get(Organization, org.id).kind is TenantKind.ASSOCIATION
    assert enabled_modules(org.id, db=db_session) == modules_before, "the modules stay"
    logged = [r.getMessage() for r in caplog.records if "tenant kind changed" in r.getMessage()]
    assert logged == [
        f"tenant kind changed: tenant={org.id} code=raakmillegem BEDRIJF -> VERENIGING "
        "by operator-1533@example.com"
    ]

    client.cookies.clear()
    header = _home_header(client)
    assert RAAK.search(header) and 'aria-label="Bakkerij Soort"' not in header


def test_platform_is_never_chosen_and_the_platforms_kind_is_fixed(client, db_session):
    org = _company(db_session)
    csrf = _login(client, db_session, "operator2-1533@example.com", "OPERATOR")

    refused = _save(client, csrf, org.id, kind="PLATFORM")
    assert refused.status_code == 422
    assert "Kies het type: vereniging of bedrijf." in refused.text
    db_session.expire_all()
    assert db_session.get(Organization, org.id).kind is TenantKind.COMPANY

    platform = (
        db_session.query(Organization)
        .filter(Organization.org_type == OrganizationType.PLATFORM)
        .execution_options(include_all_tenants=True)
        .one()
    )
    assert 'name="kind"' not in client.get(f"/admin/tenants/{platform.id}").text
    refused = _save(client, csrf, platform.id, kind="VERENIGING")
    assert refused.status_code == 422
    assert "Het type van het platform ligt vast." in refused.text
    db_session.expire_all()
    assert db_session.get(Organization, platform.id).kind is TenantKind.PLATFORM


def test_an_admin_cannot_change_a_kind(client, db_session):
    org = _company(db_session)
    csrf = _login(client, db_session, "admin-1533@example.com", "ADMIN")
    assert _save(client, csrf, org.id, kind="VERENIGING").status_code == 403
    db_session.expire_all()
    assert db_session.get(Organization, org.id).kind is TenantKind.COMPANY


PLATFORM_HOST = "platform.example.test"


@pytest.fixture
def platform_host(monkeypatch):
    from app.config import settings
    from app.domains.mdm.api import invalidate_tenant_codes

    monkeypatch.setattr(settings, "platform_hosts", PLATFORM_HOST)
    invalidate_tenant_codes()
    yield PLATFORM_HOST
    invalidate_tenant_codes()


def _landing_groups(client) -> dict[str, list[str]]:
    html = client.get("/", headers={"host": PLATFORM_HOST}).text
    main = html.split("Aanmelden als platformbeheerder")[0]
    parts = re.split(r"<h2[^>]*>\s*(.*?)\s*</h2>", main, flags=re.S)
    return {
        parts[i]: re.findall(r'<span class="font-semibold text-ink">(.*?)</span>', parts[i + 1])
        for i in range(1, len(parts), 2)
    }


def test_an_operator_moves_a_tenant_to_another_account(client, db_session, platform_host, caplog):
    first = create_account(db_session, name="Account Een", code="een-1533")
    second = create_account(db_session, name="Account Twee", code="twee-1533")
    org = create_tenant(db_session, name="Proefclub", code="proefclub-1533", parent_id=first.id)
    db_session.commit()
    modules_before = enabled_modules(org.id, db=db_session)
    assert _landing_groups(client)["Account Een"] == ["Proefclub"]
    csrf = _login(client, db_session, "operator3-1533@example.com", "OPERATOR")

    editor = client.get(f"/admin/tenants/{org.id}").text
    assert re.search(rf'<option value="{first.id}"\s+selected>Account Een</option>', editor)
    assert f'<option value="{second.id}">Account Twee</option>' in editor

    with caplog.at_level(logging.INFO, logger="app.domains.mdm.tenant_service"):
        saved = _save(client, csrf, org.id, account_id=str(second.id))
    assert saved.status_code == 200, saved.text[-500:]
    db_session.expire_all()
    assert db_session.get(Organization, org.id).parent_id == second.id
    assert enabled_modules(org.id, db=db_session) == modules_before, "the modules stay"
    logged = [r.getMessage() for r in caplog.records if "tenant account changed" in r.getMessage()]
    assert logged == [
        f"tenant account changed: tenant={org.id} code=proefclub-1533 een-1533 -> twee-1533 "
        "by operator3-1533@example.com"
    ]

    client.cookies.clear()
    groups = _landing_groups(client)
    print("MEASURE", groups)
    assert groups["Account Twee"] == ["Proefclub"]
    assert "Account Een" not in groups, "an account left without a tenant drops off"


def test_only_an_active_account_is_taken_and_the_platform_has_none(client, db_session):
    gone = create_account(db_session, name="Account Weg", code="weg-1533")
    gone.is_active = False
    org = _company(db_session)
    csrf = _login(client, db_session, "operator4-1533@example.com", "OPERATOR")

    refused = _save(client, csrf, org.id, account_id=str(gone.id))
    assert refused.status_code == 422
    assert "Kies een actief account." in refused.text
    db_session.expire_all()
    assert db_session.get(Organization, org.id).parent_id is None

    platform = (
        db_session.query(Organization)
        .filter(Organization.org_type == OrganizationType.PLATFORM)
        .execution_options(include_all_tenants=True)
        .one()
    )
    assert 'name="account_id"' not in client.get(f"/admin/tenants/{platform.id}").text
    refused = _save(client, csrf, platform.id, account_id=str(gone.id))
    assert refused.status_code == 422
    assert "Het platform hangt onder geen account." in refused.text
