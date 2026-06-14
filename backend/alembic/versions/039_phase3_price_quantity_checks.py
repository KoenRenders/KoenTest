"""Phase 3 DB constraints: prijs- en aantal-checks (#96)

Idempotent en defensief: elke CHECK wordt enkel toegevoegd als hij nog niet
bestaat én geen bestaande rij hem schendt (zodat een rebuild nooit faalt op
legacy-data). Sluit de gaten t.o.v. de bestaande price-check op activity_products
(migratie 023).

Revision ID: 039
Revises: 038
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def _has_constraint(conn, table, name):
    insp = Inspector.from_engine(conn)
    return any(c["name"] == name for c in insp.get_check_constraints(table))


def _table_exists(conn, table):
    insp = Inspector.from_engine(conn)
    return table in insp.get_table_names()


def _no_violation(conn, table, where_violates):
    """True als geen enkele rij de constraint schendt (veilig om toe te voegen)."""
    n = conn.execute(
        sa.text(f"SELECT COUNT(*) FROM {table} WHERE {where_violates}")
    ).scalar()
    return n == 0


# (tabel, constraint-naam, CHECK-expressie, "rij schendt"-WHERE)
_CHECKS = [
    ("activity_sub_registrations", "ck_activity_sub_registrations_price_non_negative",
     "price >= 0", "price < 0"),
    ("activity_sub_registrations", "ck_activity_sub_registrations_member_price_non_negative",
     "member_price >= 0 OR member_price IS NULL", "member_price < 0"),
    ("activity_products", "ck_activity_products_member_price_non_negative",
     "member_price >= 0 OR member_price IS NULL", "member_price < 0"),
    ("registration_items", "ck_registration_items_quantity_positive",
     "quantity > 0", "quantity <= 0"),
]


def upgrade():
    conn = op.get_bind()
    for table, name, expr, violates in _CHECKS:
        if not _table_exists(conn, table):
            continue
        if _has_constraint(conn, table, name):
            continue
        if _no_violation(conn, table, violates):
            op.create_check_constraint(name, table, expr)


def downgrade():
    conn = op.get_bind()
    for table, name, _expr, _violates in _CHECKS:
        if _table_exists(conn, table) and _has_constraint(conn, table, name):
            op.drop_constraint(name, table, type_="check")
