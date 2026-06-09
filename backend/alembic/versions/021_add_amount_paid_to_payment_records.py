"""Add amount_paid to payment_records

Revision ID: 021
Revises: 020
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def _has_column(conn, table, column):
    insp = Inspector.from_engine(conn)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade():
    conn = op.get_bind()
    if not _has_column(conn, "payment_records", "amount_paid"):
        op.add_column("payment_records", sa.Column("amount_paid", sa.Numeric(10, 2), nullable=True))


def downgrade():
    op.drop_column("payment_records", "amount_paid")
