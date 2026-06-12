"""Voeg valid_from en valid_to toe aan memberships

Revision ID: 024
Revises: 023
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def _has_column(conn, table, column):
    insp = Inspector.from_engine(conn)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade():
    conn = op.get_bind()
    if not _has_column(conn, "memberships", "valid_from"):
        op.add_column("memberships", sa.Column("valid_from", sa.Date, nullable=True))
    if not _has_column(conn, "memberships", "valid_to"):
        op.add_column("memberships", sa.Column("valid_to", sa.Date, nullable=True))


def downgrade():
    op.drop_column("memberships", "valid_to")
    op.drop_column("memberships", "valid_from")
