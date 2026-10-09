"""the workbench is core and no module any more

#1876. Since CR-24 the workbench is the one way into the back office: the way
in after signing in, the public header's Admin item and the "geen toegang"
page all lead there. It was also a module an operator could switch off per
tenant, and for such a tenant all three answered "niet gevonden". The platform
owner chose on 9 October 2026 to make it core rather than keep the switch and
search for another landing.

So the stored fact "this tenant has the workbench on" means nothing any more:
its rows go, and the CHECK no longer allows the code — a row with it would be
read by nobody. No tenant had it off on the day this was written.

The codes are frozen here on purpose, as in migration 187: a migration never
reads the enum of the day.
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
revision = "202_2026_10_09_191828"
down_revision = "201_2026_10_09_135402"
branch_labels = None
depends_on = None

REMAINING = (
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
    "chatbot",
)


def _check(codes: tuple[str, ...]) -> None:
    allowed = ", ".join(f"'{code}'" for code in codes)
    op.execute(
        "ALTER TABLE mdm.tenant_modules DROP CONSTRAINT IF EXISTS ck_tenant_modules_module_code"
    )
    op.execute(
        "ALTER TABLE mdm.tenant_modules ADD CONSTRAINT ck_tenant_modules_module_code "
        f"CHECK (module_code IN ({allowed}))"
    )


def upgrade() -> None:
    op.execute("DELETE FROM mdm.tenant_modules WHERE module_code = 'workflow'")
    _check(REMAINING)


def downgrade() -> None:
    # Schema and data, with one loss said out loud: the old code reads the row,
    # so every tenant and the platform get it back — also a tenant that had the
    # workbench switched off before the upgrade. That it was off is not kept
    # (no tenant had it off when this was written), and on is the side that
    # leaves nobody without a way into the back office.
    _check((*REMAINING, "workflow"))
    op.execute(
        """
        INSERT INTO mdm.tenant_modules (tenant_id, module_code)
        SELECT o.id, 'workflow'
        FROM mdm.organizations o
        WHERE o.org_type IN ('UNIT', 'PLATFORM')
        ON CONFLICT DO NOTHING
        """
    )
