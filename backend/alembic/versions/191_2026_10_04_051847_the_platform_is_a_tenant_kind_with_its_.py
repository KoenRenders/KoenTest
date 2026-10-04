"""the platform is a tenant kind with its own module set

CR-19 (#1468), #1523. The platform organisation had no kind (NULL) and every
module on: #1475 seeded it full so that nothing changed visibly. Its back-office
menu therefore showed Activiteiten, Leden, Vergaderingen and the rest, none of
which means anything for platform administration. Koen, 3 October 2026: the
platform is a tenant kind of its own, with — for now — a company's modules
(pages, media, forms, the workbench).

So: the code PLATFORM joins the tenant-kind list, the PLATFORM organisation
takes it, and its enabled set becomes that default. Switching a module off
deletes nothing (CR-19 §C4.3): its rows stay, unreachable until it is switched
on again. The module lists are written out here, frozen, and not read from the
registry: a migration says what it did on the day it ran.
"""

from alembic import op

from app.domains.mdm.codes import TENANT_KIND_CODES
from app.kernel.codes import create_code_list

#: The platform's module set on this day (`DEFAULTS["PLATFORM"]`, #1523).
PLATFORM_MODULES = ("cms", "media", "forms", "workflow")
#: Every module on this day: what #1475 seeded the platform with, and what the
#: downgrade gives back.
EVERY_MODULE = (
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
revision = "191_2026_10_04_051847"
down_revision = "190_2026_10_03_000631"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The code PLATFORM and its labels; the list exists (188), the rows are
    # upserted, so this adds only what is new.
    create_code_list(op, schema="mdm", name="tenant_kind", codes=TENANT_KIND_CODES, code_length=20)
    op.execute(
        "UPDATE mdm.organizations SET kind = 'PLATFORM' WHERE org_type = 'PLATFORM' AND kind IS NULL"
    )
    keep = ", ".join(f"'{code}'" for code in PLATFORM_MODULES)
    op.execute(
        f"""
        DELETE FROM mdm.tenant_modules
        WHERE module_code NOT IN ({keep})
          AND tenant_id IN (SELECT id FROM mdm.organizations WHERE org_type = 'PLATFORM')
        """
    )
    op.execute(
        f"""
        INSERT INTO mdm.tenant_modules (tenant_id, module_code)
        SELECT o.id, m.code
        FROM mdm.organizations o
        CROSS JOIN (VALUES {", ".join(f"('{code}')" for code in PLATFORM_MODULES)}) AS m(code)
        WHERE o.org_type = 'PLATFORM'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    # Schema and data, as before this migration: the platform has no kind and
    # every module on again (what #1475 seeded), and the code PLATFORM goes.
    # The modules' own data was never touched, so there is nothing to restore.
    op.execute(
        f"""
        INSERT INTO mdm.tenant_modules (tenant_id, module_code)
        SELECT o.id, m.code
        FROM mdm.organizations o
        CROSS JOIN (VALUES {", ".join(f"('{code}')" for code in EVERY_MODULE)}) AS m(code)
        WHERE o.org_type = 'PLATFORM'
        ON CONFLICT DO NOTHING
        """
    )
    op.execute("UPDATE mdm.organizations SET kind = NULL WHERE kind = 'PLATFORM'")
    op.execute("DELETE FROM mdm.tenant_kind_labels WHERE code = 'PLATFORM'")
    op.execute("DELETE FROM mdm.tenant_kind_codes WHERE code = 'PLATFORM'")
