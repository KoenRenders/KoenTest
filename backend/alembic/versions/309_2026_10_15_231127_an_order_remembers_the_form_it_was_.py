"""an order remembers the form it was placed by

#1987: a shown order form is accepted once, exactly as a registration form. A
second post of the same form answers with the order the first one made, and two
posts at the same moment are decided by the database — a unique key per tenant,
one order, one payment, one provider call. Existing orders have no key (NULL),
and the index leaves those out; a deleted order frees its key.
Idempotent: the column and the index are made only when they are not there.
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
revision = "309_2026_10_15_231127"
down_revision = "308_2026_10_15_052633"
branch_labels = None
depends_on = None

INDEX = "uq_sales_orders_submission_key"


def upgrade() -> None:
    op.execute("ALTER TABLE sales.sales_orders ADD COLUMN IF NOT EXISTS submission_key VARCHAR(64)")
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX} "
        "ON sales.sales_orders (tenant_id, submission_key) "
        "WHERE submission_key IS NOT NULL AND deleted_at IS NULL"
    )


def downgrade() -> None:
    # Schema and data: the keys are dropped with their column. An order loses
    # nothing it needs; only a repeat of a form shown before the downgrade is no
    # longer recognised.
    op.execute(f"DROP INDEX IF EXISTS sales.{INDEX}")
    op.execute("ALTER TABLE sales.sales_orders DROP COLUMN IF EXISTS submission_key")
