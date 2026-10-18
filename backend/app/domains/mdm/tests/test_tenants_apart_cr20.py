"""CR-20 (#1578) — a tenant is its own thing, apart from the organisation it shows.

C6 test 1 (a tenant is a tenant), test 2 (the account is a party a tenant names),
test 15 (the tenants of an account), and F11 (the meeting circle hangs on the
party the current tenant shows). The migration's own tests stand in
`tests/test_tenants_apart_migration_cr20.py`, the key gate in
`tests/test_tenant_key_gate.py`.

Proven red (put back each time): `create_tenant` made to write an organisation
of the tenant's name again → test 1 counts one more organisation;
`is_account` made to answer True for every organisation → the second assertion
of test 2 fails; `circle_organization` back on the platform's party → the circle
test finds the platform's party, not the department's.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from app.domains.mdm.api import (
    Organization,
    Tenant,
    TenantFout,
    accounts,
    circle_organization,
    create_organization,
    create_tenant,
    is_account,
    tenants_of_account,
)
from app.kernel.tenancy import TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID, current_tenant_id

pytestmark = pytest.mark.ui_agnostisch


def test_a_tenant_is_a_tenant_and_writes_no_organisation(db_session):
    """C6 test 1."""
    account = create_organization(db_session, name="Firma Een")
    before = db_session.query(Organization).count()

    tenant = create_tenant(db_session, code="firma-een-cr20", account_id=account.id)

    assert db_session.query(Organization).count() == before, "no organisation was written"
    assert db_session.get(Tenant, tenant.id).code == "firma-een-cr20"
    assert tenant.account_id == account.id
    assert tenant.organization_id == account.id, "it shows its account until told otherwise"


def test_a_tenant_without_an_account_is_refused(db_session):
    """CR-20 F1: `account_id` is NOT NULL — every tenant hangs under an account."""
    with pytest.raises(TenantFout, match="actief account"):
        create_tenant(db_session, code="zonder-account-cr20", account_id=None)


def test_the_account_is_a_party_a_tenant_names(db_session):
    """C6 test 2: being an account is read from the tenants, never stored."""
    named = create_organization(db_session, name="Firma Twee")
    unnamed = create_organization(db_session, name="Firma Drie")
    create_tenant(db_session, code="firma-twee-cr20", account_id=named.id)

    assert is_account(db_session, named.id)
    assert not is_account(db_session, unnamed.id)
    listed = {a.id for a in accounts(db_session)}
    assert named.id in listed and unnamed.id not in listed
    columns = {c["name"] for c in inspect(db_session.bind).get_columns("organizations", "mdm")}
    assert not columns & {"role", "org_type"}, "no role column on the party"


def test_the_tenants_of_an_account(db_session):
    """C6 test 15: the door to an account workspace is this query (R6)."""
    account = create_organization(db_session, name="Firma Vier")
    other = create_organization(db_session, name="Firma Vijf")
    first = create_tenant(db_session, code="vier-a-cr20", account_id=account.id)
    second = create_tenant(db_session, code="vier-b-cr20", account_id=account.id)
    create_tenant(db_session, code="vijf-cr20", account_id=other.id)

    assert [t.id for t in tenants_of_account(db_session, account.id)] == [first.id, second.id]


def test_a_tenant_may_not_show_an_organisation_another_account_names(db_session):
    """#1550 (Koen: no data across accounts), by the tenants that name it since
    CR-20 — an organisation carries no account of its own until CR-26."""
    mine = create_organization(db_session, name="Firma Zes")
    theirs = create_organization(db_session, name="Firma Zeven")
    create_tenant(db_session, code="zeven-cr20", account_id=theirs.id)

    with pytest.raises(TenantFout, match="eigen account"):
        create_tenant(db_session, code="zes-cr20", account_id=mine.id, organization_id=theirs.id)


def test_the_circle_hangs_on_the_party_the_current_tenant_shows(db_session):
    """F11: each department's circle on its own shown party — under CR-26 the
    platform's party lies in another account than a department's persons."""
    for tenant_id in (TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID):
        token = current_tenant_id.set(tenant_id)
        try:
            shown = db_session.get(Tenant, tenant_id).organization_id
            assert circle_organization(db_session).id == shown
        finally:
            current_tenant_id.reset(token)
