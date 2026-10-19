"""A tenant for a test, the way most tests need one (CR-20).

Until CR-20 `create_tenant(name=…, code=…)` wrote one organisation row that was
the site and the party at once. Since then a tenant names an organisation as its
account and one it shows, and `create_tenant` writes no organisation. Most tests
only need "a site with this name and code", so this helper makes what the old
call made: an organisation of that name, and a tenant that shows it — under the
given account, or as its own account when none is given.
"""

from __future__ import annotations


def new_site(db, *, name: str, code: str, account_id: int | None = None, **kwargs):
    """The organisation `name` and a tenant `code` that shows it. Returns the tenant."""
    from app.domains.mdm.api import create_organization, create_tenant

    party = create_organization(db, name=name)
    return create_tenant(
        db,
        code=code,
        account_id=account_id if account_id is not None else party.id,
        organization_id=party.id,
        **kwargs,
    )


def a_tenant_with_id(db, tenant_id: int, *, code: str | None = None):
    """A tenant with exactly this id — for a test that stood "another tenant" up
    as a bare number. Since CR-20 a `tenant_id` has a key to `mdm.tenants`
    (C6 test 10), so the number must be a tenant. Made once; its account and the
    organisation it shows are one new organisation. Does not commit."""
    from app.domains.mdm.api import Organization, Tenant, TenantKind

    existing = db.get(Tenant, tenant_id)
    if existing is not None:
        return existing
    party = Organization(name=f"Organisatie {tenant_id}", is_active=True)
    db.add(party)
    db.flush()
    tenant = Tenant(
        id=tenant_id,
        code=code or f"tenant-{tenant_id}",
        kind=TenantKind.ASSOCIATION,
        account_id=party.id,
        organization_id=party.id,
        is_active=True,
    )
    db.add(tenant)
    db.flush()
    return tenant


def committed_tenant(tenant_id: int):
    """A tenant with this id, committed in a session of its own — for a test
    whose code under test writes through its own session (the AI log's sink),
    which cannot see what `db_session` only flushed. A generator for a fixture:
    the tenant is removed again after the test, when nothing points at it."""
    from sqlalchemy import text

    from app.database import SessionLocal

    own = SessionLocal()
    try:
        made = (
            own.execute(text("SELECT 1 FROM mdm.tenants WHERE id = :t"), {"t": tenant_id}).first()
            is None
        )
        tenant = a_tenant_with_id(own, tenant_id)
        party = tenant.organization_id
        own.commit()
    finally:
        own.close()
    yield tenant_id
    if not made:
        return
    own = SessionLocal()
    try:
        own.execute(text("DELETE FROM mdm.tenants WHERE id = :t"), {"t": tenant_id})
        own.execute(text("DELETE FROM mdm.organizations WHERE id = :p"), {"p": party})
        own.commit()
    finally:
        own.close()
