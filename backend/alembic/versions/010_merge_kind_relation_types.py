"""Merge 'kind' and 'meerderjarig kind' into '(meerderjarig) kind'

Revision ID: 010
Revises: 009
Create Date: 2026-06-05
"""
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE member_persons
        SET relation_type = '(meerderjarig) kind'
        WHERE relation_type IN ('kind', 'meerderjarig kind')
    """)


def downgrade():
    pass
