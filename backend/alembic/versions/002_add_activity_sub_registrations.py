"""Add activity sub registrations and extend activities

Revision ID: 002
Revises: 001
Create Date: 2026-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to activities
    op.add_column("activities", sa.Column("members_only", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("activities", sa.Column("is_cancelled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("activities", sa.Column("date_end", sa.Date(), nullable=True))
    op.add_column("activities", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("activities", sa.Column("updated_at", sa.DateTime(), nullable=True))

    # Rename registration_type to registration_type_code in activities
    op.alter_column("activities", "registration_type", new_column_name="registration_type_code")

    # Create activity_sub_registrations table
    op.create_table(
        "activity_sub_registrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("external_register_url", sa.String(500), nullable=True),
        sa.Column("external_registrations_url", sa.String(500), nullable=True),
        sa.Column("registration_type_code", sa.String(10), nullable=False),
        sa.Column("max_participants", sa.Integer(), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("member_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_free", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"]),
        sa.ForeignKeyConstraint(["registration_type_code"], ["registration_type_codes.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activity_sub_registrations_id", "activity_sub_registrations", ["id"])
    op.create_index("ix_activity_sub_registrations_activity_id", "activity_sub_registrations", ["activity_id"])


def downgrade() -> None:
    op.drop_table("activity_sub_registrations")
    op.alter_column("activities", "registration_type_code", new_column_name="registration_type")
    op.drop_column("activities", "updated_at")
    op.drop_column("activities", "notes")
    op.drop_column("activities", "date_end")
    op.drop_column("activities", "is_cancelled")
    op.drop_column("activities", "members_only")
