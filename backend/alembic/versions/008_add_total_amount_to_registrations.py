"""Add total_amount to registrations

Revision ID: 008
Revises: 007
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("registrations", sa.Column("total_amount", sa.Numeric(10, 2), nullable=True))


def downgrade():
    op.drop_column("registrations", "total_amount")
