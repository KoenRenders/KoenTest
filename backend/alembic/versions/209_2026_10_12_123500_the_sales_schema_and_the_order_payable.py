"""the sales schema and the order payable (CR-21, phase 2)

The webshop's own domain: an order and its lines (soft-deleted as a registration,
Q61), the shop's intro and its contact persons — and the third payable type, an
order, which `payment` learns from `sales` through the describer.
"""

import sqlalchemy as sa
from alembic import op

from app.domains.payment.codes import PAYABLE_TYPE_CODES
from app.kernel.codes import create_code_list

# The id is a timestamp, not a sequence number (#951). The number at the front
# of the FILE NAME is for readability only — alembic ignores it; the head is
# what `alembic heads` says.
revision = "209_2026_10_12_123500"
down_revision = "208_2026_10_12_070910"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The order payable: the list exists (migration 153); the helper is
    # idempotent and adds only the `order` row.
    create_code_list(
        op,
        schema="payment",
        name="payable_type",
        codes=PAYABLE_TYPE_CODES,
        fk_from=("payment.payment_records.payable_type",),
        code_length=50,
    )

    op.execute("CREATE SCHEMA IF NOT EXISTS sales")

    op.create_table(
        "sales_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("guest_name", sa.String(200), nullable=True),
        sa.Column("guest_email", sa.String(200), nullable=True),
        sa.Column("guest_mobile", sa.String(200), nullable=True),
        sa.Column("payment_method", sa.String(20), nullable=True),
        sa.Column(
            "placed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema="sales",
    )
    op.create_index("ix_sales_orders_id", "sales_orders", ["id"], schema="sales")
    op.create_index("ix_sales_orders_tenant_id", "sales_orders", ["tenant_id"], schema="sales")
    op.create_index("ix_sales_orders_person_id", "sales_orders", ["person_id"], schema="sales")
    op.create_index("ix_sales_orders_deleted_at", "sales_orders", ["deleted_at"], schema="sales")

    op.create_table(
        "sales_order_lines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_code", sa.String(8), nullable=False, server_default="C62"),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["sales.sales_orders.id"], ondelete="CASCADE"),
        sa.CheckConstraint("quantity > 0", name="ck_sales_order_lines_quantity_positive"),
        schema="sales",
    )
    op.create_index("ix_sales_order_lines_id", "sales_order_lines", ["id"], schema="sales")
    op.create_index(
        "ix_sales_order_lines_tenant_id", "sales_order_lines", ["tenant_id"], schema="sales"
    )
    op.create_index(
        "ix_sales_order_lines_order_id", "sales_order_lines", ["order_id"], schema="sales"
    )
    op.create_index(
        "ix_sales_order_lines_variant_id", "sales_order_lines", ["variant_id"], schema="sales"
    )
    op.create_index(
        "ix_sales_order_lines_deleted_at", "sales_order_lines", ["deleted_at"], schema="sales"
    )

    op.create_table(
        "shop_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("intro", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="sales",
    )
    op.create_index("ix_shop_settings_id", "shop_settings", ["id"], schema="sales")
    op.create_index("ix_shop_settings_tenant_id", "shop_settings", ["tenant_id"], schema="sales")

    op.create_table(
        "shop_contacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="sales",
    )
    op.create_index("ix_shop_contacts_id", "shop_contacts", ["id"], schema="sales")
    op.create_index("ix_shop_contacts_tenant_id", "shop_contacts", ["tenant_id"], schema="sales")
    op.create_index("ix_shop_contacts_person_id", "shop_contacts", ["person_id"], schema="sales")


def downgrade() -> None:
    op.execute("DELETE FROM payment.payable_type_labels WHERE code = 'order'")
    op.execute("DELETE FROM payment.payable_type_codes WHERE code = 'order'")

    op.drop_table("shop_contacts", schema="sales")
    op.drop_table("shop_settings", schema="sales")
    op.drop_table("sales_order_lines", schema="sales")
    op.drop_table("sales_orders", schema="sales")
    op.execute("DROP SCHEMA IF EXISTS sales")
