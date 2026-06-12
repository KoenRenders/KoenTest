"""Add CHECK price >= 0 on activity_products

Revision ID: 023
Revises: 022
Create Date: 2026-06-12
"""
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "ck_activity_products_price_non_negative"


def _has_constraint(conn, table, name):
    insp = Inspector.from_engine(conn)
    return any(c["name"] == name for c in insp.get_check_constraints(table))


def upgrade():
    conn = op.get_bind()
    if not _has_constraint(conn, "activity_products", CONSTRAINT_NAME):
        op.create_check_constraint(CONSTRAINT_NAME, "activity_products", "price >= 0")


def downgrade():
    op.drop_constraint(CONSTRAINT_NAME, "activity_products", type_="check")
