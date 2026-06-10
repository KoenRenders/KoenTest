"""Add remarks to registrations

Revision ID: 022
Revises: 021
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def _has_column(conn, table, column):
    insp = Inspector.from_engine(conn)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade():
    conn = op.get_bind()
    if not _has_column(conn, "registrations", "remarks"):
        op.add_column("registrations", sa.Column("remarks", sa.Text, nullable=True))


def downgrade():
    op.drop_column("registrations", "remarks")
