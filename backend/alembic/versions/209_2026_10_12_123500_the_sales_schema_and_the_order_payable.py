"""the sales schema and the order payable (CR-21, phase 2)

The webshop's own domain: an order and its lines (soft-deleted as a registration,
Q61), the shop's intro and its contact persons — and the third payable type, an
order, which `payment` learns from `sales` through the describer.

`payment_method` points at `mdm.payment_method_codes` like the registration's
column does (migration 153); `variant_id` and `person_id` stay soft references,
because no foreign key leaves the schema.
"""

import sqlalchemy as sa
from alembic import op

from app.domains.payment.codes import PAYABLE_TYPE_CODES
from app.kernel.codes import add_code_fk, create_code_list

# The id is a timestamp, not a sequence number (#951). The number at the front
# of the FILE NAME is for readability only — alembic ignores it; the head is
# what `alembic heads` says.
revision = "209_2026_10_12_123500"
down_revision = "208_2026_10_12_070910"
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

    if not _has_table("sales", "sales_orders"):
        op.create_table(
            "sales_orders",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("person_id", sa.Integer(), nullable=True, index=True),
            sa.Column("guest_name", sa.String(200), nullable=True),
            sa.Column("guest_email", sa.String(200), nullable=True),
            sa.Column("guest_mobile", sa.String(200), nullable=True),
            sa.Column("payment_method", sa.String(20), nullable=True),
            sa.Column(
                "placed_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True),
            schema="sales",
        )
    add_code_fk(op, "sales.sales_orders.payment_method", "mdm", "payment_method")

    if not _has_table("sales", "sales_order_lines"):
        op.create_table(
            "sales_order_lines",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("order_id", sa.Integer(), nullable=False, index=True),
            sa.Column("variant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit_code", sa.String(8), nullable=False, server_default="C62"),
            sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True),
            sa.ForeignKeyConstraint(["order_id"], ["sales.sales_orders.id"], ondelete="CASCADE"),
            sa.CheckConstraint("quantity > 0", name="ck_sales_order_lines_quantity_positive"),
            schema="sales",
        )

    if not _has_table("sales", "shop_settings"):
        op.create_table(
            "shop_settings",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("intro", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            schema="sales",
        )

    if not _has_table("sales", "shop_contacts"):
        op.create_table(
            "shop_contacts",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column("person_id", sa.Integer(), nullable=False, index=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            schema="sales",
        )


def downgrade() -> None:
    op.execute("DELETE FROM payment.payable_type_labels WHERE code = 'order'")
    op.execute("DELETE FROM payment.payable_type_codes WHERE code = 'order'")

    op.drop_table("shop_contacts", schema="sales")
    op.drop_table("shop_settings", schema="sales")
    op.drop_table("sales_order_lines", schema="sales")
    op.drop_table("sales_orders", schema="sales")
    op.execute("DROP SCHEMA IF EXISTS sales")
