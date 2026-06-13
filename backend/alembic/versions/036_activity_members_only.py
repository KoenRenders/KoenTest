"""members_only-vlag op activiteiten

Revision ID: 036
Revises: 035
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    if "activities" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("activities")}
    if "members_only" not in cols:
        op.add_column(
            "activities",
            sa.Column("members_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade():
    op.drop_column("activities", "members_only")
