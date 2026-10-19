"""Refuses a tenant table whose `tenant_id` has no key to `mdm.tenants` · ratchet · since #1578.

CR-20 C6 test 7 (#1578): a tenant-scoped row points at a tenant by a foreign
key, so a row can no longer carry a tenant that does not exist. Until CR-20 no
`tenant_id` had a key at all.

Until CR-26 a baseline held the `mdm` seam of CR-20 F2: the tables whose
`tenant_id` held an organisation's id on an organisation's own rows. CR-26
phase 1 took them to the account scope (#2020); the baseline and the mixin's
way out went with them, and no tenant table is without its key.

Proven red, additively (put back): a `tenant_id` column without the key
declared on `Membership` itself → the first test names
`membership.memberships`. (CR-20's proof stands too: the mixin's key pointed at
`mdm.organizations.id` → both fail.)
"""

from __future__ import annotations

import app.models  # noqa: F401 - registers every model
from app.database import Base
from app.kernel.tenancy import TenantMixin


def _tenant_tables():
    return {
        m.class_.__table__.fullname: m.class_.__table__
        for m in Base.registry.mappers
        if issubclass(m.class_, TenantMixin)
    }


def test_every_tenant_table_has_its_key():
    tables = _tenant_tables()
    # 69 since CR-26 took the party tables to the account scope.
    assert len(tables) >= 60, f"the gate looks at too few tables: {len(tables)}"
    without = {
        name
        for name, table in tables.items()
        if not any(fk.target_fullname == "mdm.tenants.id" for fk in table.c.tenant_id.foreign_keys)
    }
    assert not without, f"A tenant table without its key to mdm.tenants: {sorted(without)}"


def test_the_key_points_at_the_tenants_not_at_the_organisations():
    """A tenant id is no organisation id since CR-20 (C4.1). A composite key of
    a table's own (workflow's `(tenant_id, code)`) may stand beside it."""
    targets = {
        fk.target_fullname
        for table in _tenant_tables().values()
        for fk in table.c.tenant_id.foreign_keys
    }
    assert "mdm.tenants.id" in targets
    assert not {t for t in targets if t.startswith("mdm.organizations.")}, targets
