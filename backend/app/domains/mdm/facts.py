"""Which households and persons a tenant sees: the ones with a fact there (CR-26 F9, C4.3).

Since CR-26 a person and a household belong to the account, and the account
filter alone would show a department every household of the account. What a
department sees is what has a fact at it: a household with a membership row
there (an ended or a deleted one too), a person in such a household or
with a registration, an order or a relation there — and a person with a fact at
no tenant at all, whom every department of the account sees. The rule is two views of
migration 314 (`household_tenants`, `person_tenants`); this module asks them,
for the lists and for the routes that take an id — a household of the account
without a fact here answers as an id that is not yours.

Without a current tenant (a job, a script) nothing is narrowed, as the tenant
filter does.
"""

from __future__ import annotations

from sqlalchemy import select

from app.domains.mdm.models import household_tenants, organisation_tenants, person_tenants
from app.kernel.tenancy import current_tenant_id


def households_of_tenant():
    """The ids of the households at the current tenant, as a select for an
    `in_()`; None without a tenant."""
    tenant = current_tenant_id.get()
    if tenant is None:
        return None
    return select(household_tenants.c.member_id).where(household_tenants.c.tenant_id == tenant)


def persons_of_tenant():
    """The ids of the persons the current tenant sees, as a select for an
    `in_()`; None without a tenant: the persons with a fact here, and the
    persons with a fact at no tenant at all — an account in CR-22's sense, the
    account's and bound to no department yet, so every department of the
    account sees it until it gets a fact somewhere (Koen, 19 October 2026, to
    whether a person without a household is seen by every department of the
    account or by none: "1 voor allen zichtbaar")."""
    from sqlalchemy import exists

    from app.domains.mdm.models import Person

    tenant = current_tenant_id.get()
    if tenant is None:
        return None
    nowhere = select(Person.id).where(~exists().where(person_tenants.c.person_id == Person.id))
    return (
        select(person_tenants.c.person_id)
        .where(person_tenants.c.tenant_id == tenant)
        .union(nowhere)
    )


def household_at_tenant(db, household_id: int) -> bool:
    """Is this household at the current tenant? True without a tenant."""
    here = households_of_tenant()
    if here is None:
        return True
    return db.execute(here.where(household_tenants.c.member_id == household_id)).first() is not None


def person_at_tenant(db, person_id: int) -> bool:
    """Does the current tenant see this person (`party_at_tenant` of F9, for a
    person; `persons_of_tenant`)? True without a tenant."""
    here = persons_of_tenant()
    if here is None:
        return True
    seen = select(here.subquery().c[0]).where(here.subquery().c[0] == person_id)
    return db.execute(seen).first() is not None


def household_here(db, household_id: int):
    """The household with this id when the current tenant sees it (F9), else
    None — the one read of a household by id for a door that names one: an id
    of the account without a fact here answers as an id that is not yours."""
    from app.domains.mdm.models import Member

    household = db.query(Member).filter(Member.id == household_id).first()
    if household is None or not household_at_tenant(db, household_id):
        return None
    return household


def persons_seen_here(query):
    """Narrow a query on persons to the ones the current tenant sees
    (`persons_of_tenant`): Personen, the person pickers, a person by id."""
    from app.domains.mdm.models import Person

    here = persons_of_tenant()
    return query if here is None else query.filter(Person.id.in_(here))


def organisations_of_tenant():
    """The ids of the organisations the current tenant sees, as a select for an
    `in_()`; None without a tenant (CR-26 F9): the ones with a fact here — shown by the
    tenant, named by one of its orders, acted for by a person at it — and the ones with a
    fact at no tenant at all, which every department of their account sees until they get
    one (the rule of `persons_of_tenant`, Koen, 19 October 2026: "1 voor allen zichtbaar").
    The account is the filter's, as for persons."""
    from sqlalchemy import exists

    from app.domains.mdm.models import Organization

    tenant = current_tenant_id.get()
    if tenant is None:
        return None
    nowhere = select(Organization.id).where(
        ~exists().where(organisation_tenants.c.organization_id == Organization.id)
    )
    return (
        select(organisation_tenants.c.organization_id)
        .where(organisation_tenants.c.tenant_id == tenant)
        .union(nowhere)
    )


def organisation_at_tenant(db, organization_id: int) -> bool:
    """Is this organisation at the current tenant (`party_at_tenant` of F9, for an
    organisation)? True without a tenant; a department asks it before it shows a
    record by id, and answers 404 when it is not."""
    here = organisations_of_tenant()
    if here is None:
        return True
    sub = here.subquery()
    return db.execute(select(sub.c[0]).where(sub.c[0] == organization_id)).first() is not None


def organisation_ids_here(db) -> set[int] | None:
    """The ids `organisations_of_tenant` selects, as a set for a list; None without a
    tenant."""
    here = organisations_of_tenant()
    return None if here is None else set(db.execute(here).scalars())
