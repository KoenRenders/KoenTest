"""Stock as a ledger (CR-21, phase 1): schema ``stock``.

Why this exists: what is in stock, where, and why it changed (R7). On hand is
the sum of the movements; a reservation is kept apart (D2). A movement carries a
reason (RECEIPT, GOODS_ISSUE, CORRECTION), so the ledger can carry a value later
(R8). One default location per tenant, created on the first write.

No foreign key leaves the schema (`test_schema_boundaries`): `variant_id` and
`order_line_id` are soft references into `product` and `sales`.
"""

import sqlalchemy as sa
from alembic import op

from app.domains.stock.codes import MOVEMENT_REASON_CODES, RESERVATION_STATUS_CODES
from app.kernel.codes import create_code_list

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: the head is what `alembic heads` says.
revision = "205_2026_10_10_105206"
down_revision = "204_2026_10_10_104708"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS stock")

    op.create_table(
        "stock_locations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="stock",
    )
    # One default location per tenant; a plain UNIQUE would allow several
    # non-default rows but the default is what the rule is about.
    op.execute(
        "CREATE UNIQUE INDEX uq_stock_locations_default "
        "ON stock.stock_locations (tenant_id) WHERE is_default"
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
        sa.Column("variant_id", sa.Integer, nullable=False, index=True),
        sa.Column(
            "location_id",
            sa.Integer,
            sa.ForeignKey("stock.stock_locations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("order_line_id", sa.Integer, nullable=True, index=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity <> 0", name="ck_stock_movements_quantity_not_zero"),
        schema="stock",
    )

    op.create_table(
        "stock_reservations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, nullable=False, index=True),
        sa.Column("order_line_id", sa.Integer, nullable=True, index=True),
        sa.Column("variant_id", sa.Integer, nullable=False, index=True),
        sa.Column(
            "location_id",
            sa.Integer,
            sa.ForeignKey("stock.stock_locations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity > 0", name="ck_stock_reservations_quantity_positive"),
        schema="stock",
    )

    # The reasons and statuses are code lists; their foreign keys go on only
    # now, once the tables they guard exist.
    create_code_list(
        op,
        schema="stock",
        name="movement_reason",
        codes=MOVEMENT_REASON_CODES,
        fk_from=("stock.stock_movements.reason",),
        code_length=20,
    )
    create_code_list(
        op,
        schema="stock",
        name="reservation_status",
        codes=RESERVATION_STATUS_CODES,
        fk_from=("stock.stock_reservations.status",),
        code_length=20,
    )


def downgrade() -> None:
    # Schema and the seeded code lists only: this migration wrote no rows, so
    # there is no data to restore — dropping the tables drops their rows.
    op.drop_table("stock_reservations", schema="stock")
    op.drop_table("stock_movements", schema="stock")
    op.drop_table("stock_locations", schema="stock")
    op.drop_table("reservation_status_labels", schema="stock")
    op.drop_table("reservation_status_codes", schema="stock")
    op.drop_table("movement_reason_labels", schema="stock")
    op.drop_table("movement_reason_codes", schema="stock")
