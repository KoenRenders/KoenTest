"""The product catalogue (CR-21, phase 1): schema ``product``.

Why this exists: the webshop needs its own master data — an article
(`products`), its sizes (`product_variants`) and the pictures and documents
shown on it (`product_attachments`) — kept apart from any activity (R2). The
life cycle of an article is the code list `product_status`, so a state can be
added later without another migration (Q74); its foreign key holds the values,
where a CHECK would have to be rewritten every time.

No foreign key leaves the schema (`test_schema_boundaries`): `media_asset_id` is
a soft reference to `media.media_assets`. The `sku` is unique per tenant.
"""

import sqlalchemy as sa
from alembic import op

from app.domains.product.codes import PRODUCT_STATUS_CODES
from app.kernel.codes import create_code_list

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: the head is what `alembic heads` says.
revision = "203_2026_10_10_101638"
down_revision = "202_2026_10_09_191828"
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


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS product")

    if not _has_table("product", "products"):
        op.create_table(
            "products",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="CONCEPT"),
            sa.Column("pre_order", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("pre_order_until", sa.Date, nullable=True),
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
            schema="product",
        )

    if not _has_table("product", "product_variants"):
        op.create_table(
            "product_variants",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column(
                "product_id",
                sa.Integer,
                sa.ForeignKey("product.products.id", ondelete="RESTRICT"),
                nullable=False,
                index=True,
            ),
            sa.Column("sku", sa.String(64), nullable=True),
            sa.Column("properties", sa.JSON, nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
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
            sa.UniqueConstraint("tenant_id", "sku", name="uq_product_variants_sku"),
            schema="product",
        )

    if not _has_table("product", "product_attachments"):
        op.create_table(
            "product_attachments",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
            sa.Column(
                "product_id",
                sa.Integer,
                sa.ForeignKey("product.products.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            # A soft reference to media.media_assets (B3a): the asset's kind says
            # whether it is a picture or a document.
            sa.Column("media_asset_id", sa.Integer, nullable=False, index=True),
            sa.Column("title", sa.String(255), nullable=True),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
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
            schema="product",
        )

    # The life cycle is a code list: the foreign key goes on only now, once the
    # `products` table it guards exists.
    create_code_list(
        op,
        schema="product",
        name="product_status",
        codes=PRODUCT_STATUS_CODES,
        fk_from=("product.products.status",),
        code_length=20,
    )


def downgrade() -> None:
    # Schema and the seeded code list only: this migration wrote no product rows,
    # so there is no data to restore — dropping the tables drops their rows.
    op.drop_table("product_attachments", schema="product")
    op.drop_table("product_variants", schema="product")
    op.drop_table("products", schema="product")
    op.drop_table("product_status_labels", schema="product")
    op.drop_table("product_status_codes", schema="product")
