"""Prices over time (CR-21, phase 1): schema ``pricing``.

Why this exists: an article can have different prices over time, and at any
moment it is clear what the price is (R6). A price has a start date only; it ends
where the next one of the same type starts. The member price is a second row with
a type, never a column `member_price` (B3a).

No foreign key leaves the schema (`test_schema_boundaries`): `product_id` and
`variant_id` are soft references into `product`. The key that makes overlap
impossible is `UNIQUE NULLS NOT DISTINCT` — a plain UNIQUE would let two
product-level prices of one type and date in, because two NULL variants count as
different (the same reason migration 186 wrote it for the media tags).
"""

import sqlalchemy as sa
from alembic import op

from app.domains.pricing.codes import PRICE_TYPE_CODES
from app.kernel.codes import create_code_list

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: the head is what `alembic heads` says.
revision = "204_2026_10_10_104708"
down_revision = "203_2026_10_10_101638"
branch_labels = None
depends_on = None


def _has_table(schema: str, table: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :s AND table_name = :t"
            ),
            {"s": schema, "t": table},
        )
        .scalar()
    )


def _has_constraint(schema: str, table: str, name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM information_schema.table_constraints "
                "WHERE constraint_schema = :s AND table_name = :t AND constraint_name = :n"
            ),
            {"s": schema, "t": table, "n": name},
        )
        .scalar()
    )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS pricing")

    if not _has_table("pricing", "prices"):
        op.create_table(
            "prices",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("product_id", sa.Integer, nullable=False, index=True),
            sa.Column("variant_id", sa.Integer, nullable=True, index=True),
            sa.Column("price_type", sa.String(20), nullable=False),
            sa.Column("amount", sa.Numeric(10, 2), nullable=False),
            sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
            sa.Column("valid_from", sa.Date, nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint("amount >= 0", name="ck_prices_amount_nonnegative"),
            schema="pricing",
        )
        # Overlap impossible at rest, NULL variant included (C4.2).
        op.execute(
            "ALTER TABLE pricing.prices ADD CONSTRAINT uq_prices_validity "
            "UNIQUE NULLS NOT DISTINCT (tenant_id, product_id, variant_id, price_type, valid_from)"
        )
    elif not _has_constraint("pricing", "prices", "uq_prices_validity"):
        op.execute(
            "ALTER TABLE pricing.prices ADD CONSTRAINT uq_prices_validity "
            "UNIQUE NULLS NOT DISTINCT (tenant_id, product_id, variant_id, price_type, valid_from)"
        )

    # The type's foreign key goes on only now, once the table it guards exists.
    create_code_list(
        op,
        schema="pricing",
        name="price_type",
        codes=PRICE_TYPE_CODES,
        fk_from=("pricing.prices.price_type",),
        code_length=20,
    )


def downgrade() -> None:
    # Schema and the seeded code list only: this migration wrote no price rows,
    # so there is no data to restore — dropping the table drops its rows.
    op.drop_table("prices", schema="pricing")
    op.drop_table("price_type_labels", schema="pricing")
    op.drop_table("price_type_codes", schema="pricing")
