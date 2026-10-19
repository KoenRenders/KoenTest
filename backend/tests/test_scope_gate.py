"""Refuses a party table on the tenant scope, or a fact table on the account scope · hard · since #2020.

CR-26 T2, C7 (the scope gate): a person, a household and an organisation exist
once per account, so the tables of the party and of what hangs on it carry
`AccountMixin`; what a party does at a tenant is a fact, in a table with
`TenantMixin`. A table carries one of the two, never both (C4.2, C4.10) — a
member number is issued per department, so `external_numbers` stays a fact.

The list is compared exactly both ways: a party table that loses the account
scope fails, and so does a table that gains it without being named here.

Proven red, additively (put back each time): `TenantMixin` added beside
`AccountMixin` on `Person` → the second test names `mdm.persons`;
`AccountMixin` added beside `TenantMixin` on `ExternalNumber` → the first test
(the set differs) and the second (`mdm.external_numbers`) fail.
"""

from __future__ import annotations

import app.models  # noqa: F401 - registers every model
from app.database import Base
from app.kernel.tenancy import AccountMixin, TenantMixin

#: CR-26 F1, F3, F5, F13: the party and what hangs on it (phase 1; the
#: identifications since phase 3).
ACCOUNT_SCOPED = {
    "mdm.parties",
    "mdm.persons",
    "mdm.organizations",
    "mdm.members",
    "mdm.member_persons",
    "mdm.addresses",
    "mdm.contact_details",
    "mdm.bank_accounts",
    "mdm.party_identifications",
    "mdm.party_relationships",
    "mdm.person_history",
    "mdm.member_history",
    "mdm.member_person_history",
    "mdm.address_history",
    "mdm.contact_detail_history",
}


def _tables_with(mixin) -> set[str]:
    return {
        m.class_.__table__.fullname for m in Base.registry.mappers if issubclass(m.class_, mixin)
    }


def test_the_party_tables_and_only_they_carry_the_account_scope():
    assert _tables_with(AccountMixin) == ACCOUNT_SCOPED


def test_no_table_carries_both_scopes():
    both = _tables_with(AccountMixin) & _tables_with(TenantMixin)
    assert not both, f"a table carries the tenant and the account scope: {sorted(both)}"


def test_the_member_number_is_a_fact_per_department():
    tenant_scoped = _tables_with(TenantMixin)
    assert len(tenant_scoped) >= 60, f"the gate looks at too few tables: {len(tenant_scoped)}"
    assert {"mdm.external_numbers", "mdm.external_number_history"} <= tenant_scoped
