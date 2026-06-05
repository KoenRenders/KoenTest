"""Add info_url to activity_sub_registrations

Revision ID: 003
Revises: 002
Create Date: 2026-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activity_sub_registrations", sa.Column("info_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("activity_sub_registrations", "info_url")
