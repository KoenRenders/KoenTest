"""phase1 uniqueness constraints

Revision ID: 033
Revises: 032
Create Date: 2026-06-13
"""
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def _constraint_exists(conn, table, name):
    insp = Inspector.from_engine(conn)
    return any(c["name"] == name for c in insp.get_unique_constraints(table))


def upgrade():
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    tables = set(insp.get_table_names())

    if "memberships" in tables and not _constraint_exists(conn, "memberships", "uq_memberships_member_year"):
        op.create_unique_constraint("uq_memberships_member_year", "memberships", ["member_id", "year"])

    if "member_persons" in tables and not _constraint_exists(conn, "member_persons", "uq_member_persons_member_person"):
        op.create_unique_constraint("uq_member_persons_member_person", "member_persons", ["member_id", "person_id"])

    if "postal_codes" in tables and not _constraint_exists(conn, "postal_codes", "uq_postal_codes_postal_code"):
        op.create_unique_constraint("uq_postal_codes_postal_code", "postal_codes", ["postal_code"])


def downgrade():
    op.drop_constraint("uq_memberships_member_year", "memberships", type_="unique")
    op.drop_constraint("uq_member_persons_member_person", "member_persons", type_="unique")
    op.drop_constraint("uq_postal_codes_postal_code", "postal_codes", type_="unique")
