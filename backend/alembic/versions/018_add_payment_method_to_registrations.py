"""Add payment_method to registrations

Revision ID: 018
Revises: 017
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def _has_column(table, column):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name=:t AND column_name=:c"
    ), {"t": table, "c": column})
    return result.fetchone() is not None


def upgrade():
    if not _has_column("registrations", "payment_method"):
        op.add_column("registrations", sa.Column("payment_method", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("registrations", "payment_method")
