"""a shop contact person is soft-deleted like the order

R41: a contact person is chosen from Personen and can be removed again. The sales
domain soft-deletes everything (a PaymentRecord may point at a row through
`payable_type`/`payable_id` with no foreign key), so `shop_contacts` gains
`deleted_at` and the removal marks the row instead of deleting it. Nothing else
reads a removed contact; the buyer's pages see only the living ones.
"""

from alembic import op

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
revision = "310_2026_10_16_104128"
down_revision = "309_2026_10_15_231127"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sales.shop_contacts ADD COLUMN IF NOT EXISTS deleted_at "
        "TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sales_shop_contacts_deleted_at "
        "ON sales.shop_contacts (deleted_at)"
    )


def downgrade() -> None:
    # Schema only: a downgrade drops the column and the soft-deleted rows with it,
    # so a contact person removed after this migration is gone after a downgrade —
    # the same as it was before the migration, and nothing points at it.
    op.execute("DROP INDEX IF EXISTS sales.ix_sales_shop_contacts_deleted_at")
    op.execute("ALTER TABLE sales.shop_contacts DROP COLUMN IF EXISTS deleted_at")
