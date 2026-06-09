"""Activity 3-level model: drop old columns, add is_cancelled, components/products/items tables

Revision ID: 016
Revises: 015
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def _has_column(conn, table, column):
    insp = Inspector.from_engine(conn)
    return column in [c["name"] for c in insp.get_columns(table)]


def _has_table(conn, table):
    insp = Inspector.from_engine(conn)
    return table in insp.get_table_names()


def upgrade() -> None:
    conn = op.get_bind()

    # Drop old activity columns (may already be absent if re-run)
    with op.batch_alter_table("activities") as batch_op:
        for col in ("price", "member_price", "is_archived", "members_only", "registration_type_code", "max_participants"):
            if _has_column(conn, "activities", col):
                batch_op.drop_column(col)

    # Migration 015 wrongly added team_name_required to activities — move it to sub_registrations
    with op.batch_alter_table("activities") as batch_op:
        if _has_column(conn, "activities", "team_name_required"):
            batch_op.drop_column("team_name_required")

    # Add is_cancelled to activities
    with op.batch_alter_table("activities") as batch_op:
        if not _has_column(conn, "activities", "is_cancelled"):
            batch_op.add_column(sa.Column("is_cancelled", sa.Boolean(), nullable=False, server_default="false"))

    # Add team_name_required to activity_sub_registrations
    with op.batch_alter_table("activity_sub_registrations") as batch_op:
        if not _has_column(conn, "activity_sub_registrations", "team_name_required"):
            batch_op.add_column(sa.Column("team_name_required", sa.Boolean(), nullable=False, server_default="false"))
        for col in ("external_register_url", "external_registrations_url", "info_url"):
            if not _has_column(conn, "activity_sub_registrations", col):
                batch_op.add_column(sa.Column(col, sa.String(500), nullable=True))

    # Add phone and team_name to registrations
    with op.batch_alter_table("registrations") as batch_op:
        if not _has_column(conn, "registrations", "phone"):
            batch_op.add_column(sa.Column("phone", sa.String(50), nullable=True))
        if not _has_column(conn, "registrations", "team_name"):
            batch_op.add_column(sa.Column("team_name", sa.String(200), nullable=True))

    # Create activity_products table
    if not _has_table(conn, "activity_products"):
        op.create_table(
            "activity_products",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("component_id", sa.Integer(), sa.ForeignKey("activity_sub_registrations.id"), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("price", sa.Numeric(10, 2), nullable=False, server_default="0"),
            sa.Column("member_price", sa.Numeric(10, 2), nullable=True),
            sa.Column("is_free", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("max_participants", sa.Integer(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )

    # Create registration_items table
    if not _has_table(conn, "registration_items"):
        op.create_table(
            "registration_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("registration_id", sa.Integer(), sa.ForeignKey("registrations.id"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("activity_products.id"), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    op.drop_table("registration_items")
    op.drop_table("activity_products")
    with op.batch_alter_table("registrations") as batch_op:
        batch_op.drop_column("team_name")
        batch_op.drop_column("phone")
    with op.batch_alter_table("activity_sub_registrations") as batch_op:
        batch_op.drop_column("team_name_required")
        batch_op.drop_column("external_register_url")
        batch_op.drop_column("external_registrations_url")
        batch_op.drop_column("info_url")
    with op.batch_alter_table("activities") as batch_op:
        batch_op.drop_column("is_cancelled")
        batch_op.add_column(sa.Column("team_name_required", sa.Boolean(), nullable=False, server_default="false"))
