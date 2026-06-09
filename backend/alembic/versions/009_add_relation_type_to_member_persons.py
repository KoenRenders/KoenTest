"""Add relation_type to member_persons, replace is_primary

Revision ID: 009
Revises: 008
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "member_persons",
        sa.Column("relation_type", sa.String(20), nullable=False, server_default="hoofdlid"),
    )
    # Migrate existing is_primary=True rows to relation_type="hoofdlid"
    op.execute("""
        UPDATE member_persons SET relation_type = 'hoofdlid' WHERE is_primary = TRUE
    """)
    op.execute("""
        UPDATE member_persons SET relation_type = 'partner' WHERE is_primary = FALSE
    """)
    op.drop_column("member_persons", "is_primary")


def downgrade():
    op.add_column(
        "member_persons",
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.execute("""
        UPDATE member_persons SET is_primary = TRUE WHERE relation_type = 'hoofdlid'
    """)
    op.drop_column("member_persons", "relation_type")
