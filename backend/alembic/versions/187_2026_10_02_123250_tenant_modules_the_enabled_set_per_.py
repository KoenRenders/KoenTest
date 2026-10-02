"""tenant modules: the enabled set per tenant

CR-19 (#1468), phase 1 (#1475). One application serves every tenant, and a
company tenant needs fewer modules than an association. What a module owns is
code (`app/kernel/modules.py`); which modules a tenant has on is data, and this
is its table.

The CHECK lists the module codes of today. A new module widens it, by a new
migration — the codes are frozen here on purpose, a migration never reads the
enum of the day.

Seeded full: every UNIT (each tenant today is an association) and the PLATFORM
organisation, whose host resolves to it since #854 — without its rows the
platform's own pages would answer 404. ACCOUNT rows never serve a request.
Nothing visible changes: everyone has everything on.
"""

from alembic import op

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
# `repr` with double quotes (#781): the generated file must already be what
# `ruff format` writes, or every new migration turns CI red. A `repr` still, not
# a bare string, because `down_revision` is a tuple for a merge and None for the
# first migration.
revision = "187_2026_10_02_123250"
down_revision = "186_2026_10_02_114850"
branch_labels = None
depends_on = None

MODULES = (
    "activities",
    "membership",
    "payment",
    "forms",
    "cms",
    "media",
    "newsletter",
    "meetings",
    "designstudio",
    "reporting",
    "workflow",
    "chatbot",
)


def upgrade() -> None:
    allowed = ", ".join(f"'{code}'" for code in MODULES)
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS mdm.tenant_modules (
            tenant_id INTEGER NOT NULL
                REFERENCES mdm.organizations(id) ON DELETE CASCADE,
            module_code VARCHAR(20) NOT NULL
                CONSTRAINT ck_tenant_modules_module_code CHECK (module_code IN ({allowed})),
            PRIMARY KEY (tenant_id, module_code)
        )
        """
    )
    op.execute(
        f"""
        INSERT INTO mdm.tenant_modules (tenant_id, module_code)
        SELECT o.id, m.code
        FROM mdm.organizations o
        CROSS JOIN (VALUES {", ".join(f"('{code}')" for code in MODULES)}) AS m(code)
        WHERE o.org_type IN ('UNIT', 'PLATFORM')
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    # Schema and data: the enabled sets go with the table. Back on the old code
    # every tenant has every module again, which is what the old code knows.
    op.execute("DROP TABLE IF EXISTS mdm.tenant_modules")
