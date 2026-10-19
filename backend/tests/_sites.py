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
    from app.domains.mdm.tenant_service import _move_to_account

    party = Organization(name=f"Organisatie {tenant_id}", is_active=True)
    db.add(party)
    db.flush()
    # Its own account (CR-26 C4.9): the tenant names the organisation's party.
    _move_to_account(db, party, party.party_id)
    tenant = Tenant(
        id=tenant_id,
        code=code or f"tenant-{tenant_id}",
        kind=TenantKind.ASSOCIATION,
        account_id=party.party_id,
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
        party_row = tenant.account_id
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
        own.execute(text("DELETE FROM mdm.parties WHERE id = :p"), {"p": party_row})
        own.commit()
    finally:
        own.close()


def as_account(db, organization) -> int:
    """Make this organisation its own account and give the party a tenant names
    as its account (CR-26 C4.9) — for a test that hangs a tenant under an
    account by hand. Does not commit."""
    from app.domains.mdm.tenant_service import _move_to_account

    _move_to_account(db, organization, organization.party_id)
    return organization.party_id


def at_tenant(db, household, tenant_id: int = 2, year: int | None = None):
    """Put a household at a tenant, the way the board's list sees it since CR-26
    (F9): a membership row there — this one not paid, so not valid. For a test
    that made a household and needs it listed or reported at a tenant. Flushes."""
    from app.domains.membership.api import Membership
    from app.kernel.clock import belgian_today

    if household.id is None:
        db.flush()
    row = Membership(
        tenant_id=tenant_id,
        member_id=household.id,
        year=year or belgian_today().year,
        # Not paid: a membership turns active when its payment is confirmed.
        is_active=False,
    )
    db.add(row)
    db.flush()
    return row


def in_the_circle(db, person, tenant_id: int = 2):
    """Give a person who is in no household a fact at a tenant (CR-26 F9): a
    place in its meeting circle, on the organisation the tenant shows. For a
    test whose board member or organiser must be named at that tenant. Flushes."""
    from app.domains.mdm.api import Organization, PartyRelationship, Tenant

    tenant = db.get(Tenant, tenant_id)
    organization = db.get(Organization, tenant.organization_id)
    row = PartyRelationship(
        from_party_id=person.party_id,
        to_party_id=organization.party_id,
        kind="BOARD_MEETING",
    )
    db.add(row)
    db.flush()
    return row


def party_of(db, person_id: int) -> int:
    """The party of a person by id — a deleted person's too (CR-26 F3): what
    hangs on a person (an address, a contact, a member number) points at it."""
    from app.domains.mdm.api import Person

    return (
        db.query(Person.party_id)
        .filter(Person.id == person_id)
        .execution_options(include_deleted=True, include_all_tenants=True)
        .scalar()
    )


def organization_party(db, organization_id: int) -> int:
    """The party of an organisation by id (CR-26 F3), across accounts."""
    from app.domains.mdm.api import Organization

    return (
        db.query(Organization.party_id)
        .filter(Organization.id == organization_id)
        .execution_options(include_all_tenants=True)
        .scalar()
    )
