"""A party is the account's; a tenant of the account sees it, another account does not (CR-26 T1, #2020).

The account scope is a loader criterion like the tenant scope, derived from the
current tenant (F2, C4.9): no second context variable. Tested on `Person`, the
first table that carries it.

Proven red, additively (put back): a line `options = options[:1]` added in
`_filter_tenant`, dropping the account criterion → the third test sees the
person from another account.
"""

from __future__ import annotations

import pytest

from app.domains.mdm.models import Person, Tenant
from app.kernel.tenancy import (
    TENANT_MILLEGEM_ID,
    TENANT_VOORBEELD_ID,
    current_tenant_id,
)
from tests._sites import a_tenant_with_id

pytestmark = pytest.mark.ui_agnostisch


def _seen_at(db, tenant_id: int, person_id: int) -> bool:
    token = current_tenant_id.set(tenant_id)
    try:
        db.expire_all()
        return db.query(Person).filter(Person.id == person_id).first() is not None
    finally:
        current_tenant_id.reset(token)


@pytest.fixture
def a_person_of_raak(db_session):
    token = current_tenant_id.set(TENANT_MILLEGEM_ID)
    try:
        person = Person(first_name="Een", last_name="Persoon")
        db_session.add(person)
        db_session.flush()
    finally:
        current_tenant_id.reset(token)
    return person


def test_a_new_person_takes_the_account_of_the_tenant_it_was_made_at(db_session, a_person_of_raak):
    millegem = db_session.get(Tenant, TENANT_MILLEGEM_ID)
    assert a_person_of_raak.account_id == millegem.account_id
    assert a_person_of_raak.party.account_id == millegem.account_id, "its party too"


def test_another_tenant_of_the_account_sees_the_person(db_session, a_person_of_raak):
    assert db_session.get(Tenant, TENANT_VOORBEELD_ID).account_id == (
        db_session.get(Tenant, TENANT_MILLEGEM_ID).account_id
    ), "precondition: the two seeded departments share an account"
    assert _seen_at(db_session, TENANT_MILLEGEM_ID, a_person_of_raak.id)
    assert _seen_at(db_session, TENANT_VOORBEELD_ID, a_person_of_raak.id)


def test_a_tenant_of_another_account_does_not(db_session, a_person_of_raak):
    elsewhere = a_tenant_with_id(db_session, 9_726)
    assert elsewhere.account_id != a_person_of_raak.account_id
    assert not _seen_at(db_session, elsewhere.id, a_person_of_raak.id)
