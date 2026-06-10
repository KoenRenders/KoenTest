"""Fix registration_items: add product_id, remove old columns

Revision ID: 020
Revises: 019
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def _has_column(table, column):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name=:t AND column_name=:c"
    ), {"t": table, "c": column})
    return result.fetchone() is not None


def upgrade():
    conn = op.get_bind()

    # Add product_id if missing
    if not _has_column("registration_items", "product_id"):
        op.add_column("registration_items", sa.Column(
            "product_id", sa.Integer(), nullable=True
        ))
        # Add FK constraint
        op.create_foreign_key(
            "fk_registration_items_product_id",
            "registration_items", "activity_products",
            ["product_id"], ["id"],
        )

    # Remove old columns that no longer exist on the model
    for col in ("sub_registration_id", "unit_price", "created_at", "updated_at"):
        if _has_column("registration_items", col):
            # Drop FK on sub_registration_id first if it exists
            if col == "sub_registration_id":
                try:
                    op.drop_constraint(
                        "registration_items_sub_registration_id_fkey",
                        "registration_items", type_="foreignkey"
                    )
                except Exception:
                    pass
            op.drop_column("registration_items", col)

    # Make product_id NOT NULL after backfill (existing rows get deleted — they're test data)
    conn.execute(sa.text("DELETE FROM registration_items WHERE product_id IS NULL"))
    with op.batch_alter_table("registration_items") as batch_op:
        batch_op.alter_column("product_id", nullable=False)


def downgrade():
    pass
