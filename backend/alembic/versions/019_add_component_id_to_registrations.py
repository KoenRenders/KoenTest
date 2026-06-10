"""Add component_id to registrations

Revision ID: 019
Revises: 018
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
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
    if not _has_column("registrations", "component_id"):
        op.add_column("registrations", sa.Column(
            "component_id", sa.Integer(),
            sa.ForeignKey("activity_sub_registrations.id", ondelete="SET NULL"),
            nullable=True,
        ))


def downgrade():
    op.drop_column("registrations", "component_id")
