"""add team_name_required to components, activity_products table, registration_items

Revision ID: 004
Revises: 003
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove price, member_price, is_archived, members_only, registration_type_code from activities
    with op.batch_alter_table("activities") as batch_op:
        batch_op.drop_column("price")
        batch_op.drop_column("member_price")
        batch_op.drop_column("is_archived")
        batch_op.drop_column("members_only")
        batch_op.drop_column("registration_type_code")

    # Add team_name_required to components (activity_sub_registrations)
    with op.batch_alter_table("activity_sub_registrations") as batch_op:
        batch_op.add_column(sa.Column("team_name_required", sa.Boolean(), nullable=False, server_default="false"))

    # Add phone and team_name to registrations
    with op.batch_alter_table("registrations") as batch_op:
        batch_op.add_column(sa.Column("phone", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("team_name", sa.String(200), nullable=True))

    # Create activity_products table
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

    # Create registration_items table (links registration to product)
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
    with op.batch_alter_table("activities") as batch_op:
        batch_op.add_column(sa.Column("price", sa.Numeric(10, 2), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("member_price", sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"))
        batch_op.add_column(sa.Column("members_only", sa.Boolean(), nullable=False, server_default="false"))
        batch_op.add_column(sa.Column("registration_type_code", sa.String(10), nullable=True))
