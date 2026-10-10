"""the shop joins the modules a tenant can switch on

CR-21, phase 1. A tenant switches the shop on and off like any other module, and
the CHECK on `mdm.tenant_modules.module_code` holds the stored values to the
known codes. Until now the shop's code was not among them, so the first tenant
that switches it on would be refused by the database.

The codes are frozen here on purpose, as in migration 202: a migration never
reads the enum of the day. The eleven of migration 202 plus `shop`.
"""

from alembic import op

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
revision = "207_2026_10_10_101936"
down_revision = "206_2026_10_10_110506"
branch_labels = None
depends_on = None

WITH_SHOP = (
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
    "shop",
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
    _check(WITH_SHOP)


def downgrade() -> None:
    # Schema and data: the shop rows go before the CHECK narrows, so no row is
    # left that the narrower CHECK refuses. The rows themselves are the only
    # data this migration wrote, and nothing else of the shop is lost.
    op.execute("DELETE FROM mdm.tenant_modules WHERE module_code = 'shop'")
    _check(WITH_SHOP[:-1])
