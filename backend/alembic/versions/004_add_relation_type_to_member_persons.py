"""Add relation_type to member_persons, replace is_primary

Revision ID: 004
Revises: 003
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("member_persons")]

    if "relation_type" not in columns:
        op.add_column(
            "member_persons",
            sa.Column("relation_type", sa.String(30), nullable=False, server_default="hoofdlid"),
        )

    if "is_primary" in columns:
        op.execute("UPDATE member_persons SET relation_type = 'hoofdlid' WHERE is_primary = TRUE")
        op.execute("UPDATE member_persons SET relation_type = 'partner' WHERE is_primary = FALSE")
        op.drop_column("member_persons", "is_primary")


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("member_persons")]

    if "is_primary" not in columns:
        op.add_column(
            "member_persons",
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        )
        op.execute("UPDATE member_persons SET is_primary = TRUE WHERE relation_type = 'hoofdlid'")

    if "relation_type" in columns:
        op.drop_column("member_persons", "relation_type")
