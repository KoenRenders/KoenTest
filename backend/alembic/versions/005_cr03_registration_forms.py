"""CR-03: registration form types and registration items

Revision ID: 005
Revises: 004
Create Date: 2026-06-05
"""
from datetime import datetime
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("reg_form_type", sa.String(20), nullable=False, server_default="NONE"))
    op.add_column("activities", sa.Column("age_category_config", sa.Text(), nullable=True))

    op.add_column("activity_sub_registrations", sa.Column("reg_form_type", sa.String(20), nullable=True))

    op.add_column("registrations", sa.Column("contact_phone", sa.String(30), nullable=True))
    op.add_column("registrations", sa.Column("team_name", sa.String(200), nullable=True))
    op.add_column("registrations", sa.Column("group_size", sa.Integer(), nullable=True))
    op.add_column("registrations", sa.Column("age_categories", sa.Text(), nullable=True))
    op.add_column("registrations", sa.Column("remarks", sa.Text(), nullable=True))
    op.add_column("registrations", sa.Column("payment_method", sa.String(20), nullable=True))
    op.add_column("registrations", sa.Column("payment_status", sa.String(20), nullable=True))
    op.add_column("registrations", sa.Column("sub_registration_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_registrations_sub_registration_id",
        "registrations", "activity_sub_registrations",
        ["sub_registration_id"], ["id"],
    )

    op.create_table(
        "registration_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("registration_id", sa.Integer(), sa.ForeignKey("registrations.id"), nullable=False),
        sa.Column("sub_registration_id", sa.Integer(), sa.ForeignKey("activity_sub_registrations.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("registration_items")
    op.drop_constraint("fk_registrations_sub_registration_id", "registrations", type_="foreignkey")
    op.drop_column("registrations", "sub_registration_id")
    op.drop_column("registrations", "payment_status")
    op.drop_column("registrations", "payment_method")
    op.drop_column("registrations", "remarks")
    op.drop_column("registrations", "age_categories")
    op.drop_column("registrations", "group_size")
    op.drop_column("registrations", "team_name")
    op.drop_column("registrations", "contact_phone")
    op.drop_column("activity_sub_registrations", "reg_form_type")
    op.drop_column("activities", "age_category_config")
    op.drop_column("activities", "reg_form_type")
