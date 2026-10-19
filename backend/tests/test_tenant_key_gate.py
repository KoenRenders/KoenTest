"""Refuses a tenant table whose `tenant_id` has no key to `mdm.tenants` · ratchet · since #1578.

CR-20 C6 test 7 (#1578): a tenant-scoped row points at a tenant by a foreign
key, so a row can no longer carry a tenant that does not exist. Until CR-20 no
`tenant_id` had a key at all.

The baseline is the `mdm` seam of CR-20 F2: the tables whose `tenant_id` holds
an organisation's id on an organisation's own rows. CR-26 takes them to the
account scope; each one that leaves must leave this list, and none may join it.
The list is compared exactly, so it can only shrink by an edit here.

Proven red (put back each time): `tenant_key = False` added to `Member` → the
first test names `mdm.members`; `mdm.addresses` taken out of `SEAM` → the first
test names it; the mixin's key pointed at `mdm.organizations.id` → both fail.
"""

from __future__ import annotations

import app.models  # noqa: F401 - registers every model
from app.database import Base
from app.kernel.tenancy import TenantMixin

#: CR-20 F2, C4.8: no key until CR-26 phase 1. May only shrink.
SEAM = {
    "mdm.addresses",
    "mdm.address_history",
    "mdm.contact_details",
    "mdm.contact_detail_history",
}


def _tenant_tables():
    return {
        m.class_.__table__.fullname: m.class_.__table__
        for m in Base.registry.mappers
        if issubclass(m.class_, TenantMixin)
    }


def test_every_tenant_table_has_its_key_but_the_seam():
    tables = _tenant_tables()
    assert len(tables) >= 70, f"the gate looks at too few tables: {len(tables)}"
    without = {
        name
        for name, table in tables.items()
        if not any(fk.target_fullname == "mdm.tenants.id" for fk in table.c.tenant_id.foreign_keys)
    }
    assert without == SEAM, (
        "A tenant table without its key to mdm.tenants, or a seam table that has one "
        f"now (take it out of SEAM): {sorted(without ^ SEAM)}"
    )


def test_the_key_points_at_the_tenants_not_at_the_organisations():
    """A tenant id is no organisation id since CR-20 (C4.1). A composite key of
    a table's own (workflow's `(tenant_id, code)`) may stand beside it."""
    targets = {
        fk.target_fullname
        for name, table in _tenant_tables().items()
        if name not in SEAM
        for fk in table.c.tenant_id.foreign_keys
    }
    assert "mdm.tenants.id" in targets
    assert not {t for t in targets if t.startswith("mdm.organizations.")}, targets
