"""a shop contact person is soft-deleted like the order

R41: a contact person is chosen from Personen and can be removed again. The sales
domain soft-deletes everything (a PaymentRecord may point at a row through
`payable_type`/`payable_id` with no foreign key), so `shop_contacts` gains
`deleted_at` and the removal marks the row instead of deleting it. Nothing else
reads a removed contact; the buyer's pages see only the living ones.
"""

import sqlalchemy as sa
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
revision = "310_2026_10_16_104128"
down_revision = "309_2026_10_15_231127"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shop_contacts",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema="sales",
    )
    op.create_index(
        "ix_sales_shop_contacts_deleted_at",
        "shop_contacts",
        ["deleted_at"],
        schema="sales",
    )


def downgrade() -> None:
    # Schema only: a downgrade drops the column and the soft-deleted rows with it,
    # so a contact person removed after this migration is gone after a downgrade —
    # the same as it was before the migration, and nothing points at it.
    op.drop_index("ix_sales_shop_contacts_deleted_at", table_name="shop_contacts", schema="sales")
    op.drop_column("shop_contacts", "deleted_at", schema="sales")
