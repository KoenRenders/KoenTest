"""The organisations a tenant sees, by fact (CR-26 phase 2, F9; T10 for organisations).

Three facts put an organisation at a tenant: the tenant shows it, an order of the tenant
names its party as the buyer, a person who acts for it is at the tenant. An organisation
with none is at no tenant; a soft-deleted order or relation is no fact.

Red proof (19 October 2026, put back): the `deleted_at IS NULL` of the order branch left
out of migration 318's view -> the deleted-order organisation shows at the tenant.
"""

from __future__ import annotations

from app.domains.mdm.api import (
    PaymentMethod,
    Tenant,
    act_for,
    create_organization,
    organisation_at_tenant,
    organisations_of_tenant,
)
from app.domains.mdm.tests.test_acting_for_organisation_cr26 import _person
from app.domains.sales.models import SalesOrder
from app.kernel.tenancy import TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID, current_tenant_id
from app.soft_delete import soft_delete


def _order(db, **columns) -> SalesOrder:
    order = SalesOrder(
        guest_name="Gast",
        guest_email="gast@example.com",
        guest_mobile="0470000000",
        payment_method=PaymentMethod.TRANSFER,
        secret_key=f"k-{db.query(SalesOrder).count()}-{columns.get('person_id')}",
        **columns,
    )
    db.add(order)
    db.flush()
    return order


def _here(db, tenant_id: int) -> set[int]:
    token = current_tenant_id.set(tenant_id)
    try:
        return set(db.execute(organisations_of_tenant()).scalars())
    finally:
        current_tenant_id.reset(token)


def test_three_facts_put_an_organisation_at_a_tenant(db_session):
    shown = create_organization(db_session, name="Getoond vzw")
    db_session.get(Tenant, TENANT_VOORBEELD_ID).organization_id = shown.id
    ordered = create_organization(db_session, name="Besteld vzw")
    _order(db_session, buyer_party_id=ordered.party_id)
    acted = create_organization(db_session, name="Namens vzw")
    person = _person(db_session)
    person.account_id = acted.account_id
    db_session.flush()
    _order(db_session, person_id=person.id)
    act_for(db_session, person.id, acted.id)
    nobody = create_organization(db_session, name="Nergens vzw")
    gone = create_organization(db_session, name="Verwijderd vzw")
    soft_delete(_order(db_session, buyer_party_id=gone.party_id))
    db_session.commit()

    millegem = _here(db_session, TENANT_MILLEGEM_ID)
    assert {ordered.id, acted.id} <= millegem
    assert shown.id not in millegem
    assert nobody.id not in millegem and gone.id not in millegem
    assert shown.id in _here(db_session, TENANT_VOORBEELD_ID)
    assert ordered.id not in _here(db_session, TENANT_VOORBEELD_ID)


def test_the_by_id_guard_answers_by_the_same_fact(db_session):
    ordered = create_organization(db_session, name="Guard vzw")
    _order(db_session, buyer_party_id=ordered.party_id)
    db_session.commit()
    token = current_tenant_id.set(TENANT_MILLEGEM_ID)
    try:
        assert organisation_at_tenant(db_session, ordered.id)
        current_tenant_id.set(TENANT_VOORBEELD_ID)
        assert not organisation_at_tenant(db_session, ordered.id)
    finally:
        current_tenant_id.reset(token)
    assert organisation_at_tenant(db_session, ordered.id), "True without a tenant"
