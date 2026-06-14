"""Phase 5 DB constraints: optionele/low-value hardening (#98)

Idempotent en defensief: elke constraint wordt enkel toegevoegd als hij nog niet
bestaat én geen bestaande rij hem schendt — een rebuild faalt dus nooit op
legacy-data.

Afwijking t.o.v. de issue-tekst: de voorgestelde CHECK op
`registrations.payment_method` is **bewust weggelaten**. Die kolom is vandaag
vrije-vorm: de router slaat de ruwe clientwaarde op (`activities.py` zet
`payment_method=data.payment_method` zonder normalisatie), waardoor er naast
'ONLINE'/'OVERSCHRIJVING' ook 'transfer' (o.a. in de testsuite) in voorkomt.
Een CHECK zou bestaande inserts breken. Eerst normaliseren (apart issue), dan
pas een constraint.

Revision ID: 040
Revises: 039
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def _has_constraint(conn, table, name):
    insp = Inspector.from_engine(conn)
    return any(c["name"] == name for c in insp.get_check_constraints(table))


def _table_exists(conn, table):
    insp = Inspector.from_engine(conn)
    return table in insp.get_table_names()


def _index_exists(conn, table, name):
    insp = Inspector.from_engine(conn)
    return any(ix["name"] == name for ix in insp.get_indexes(table))


def _no_violation(conn, table, where_violates):
    n = conn.execute(
        sa.text(f"SELECT COUNT(*) FROM {table} WHERE {where_violates}")
    ).scalar()
    return n == 0


# (tabel, constraint-naam, CHECK-expressie, "rij schendt"-WHERE)
_CHECKS = [
    ("media_assets", "ck_media_assets_kind_valid",
     "kind IN ('sponsor','activity_photo')",
     "kind NOT IN ('sponsor','activity_photo')"),
    ("activity_sub_registrations", "ck_activity_sub_registrations_max_participants_positive",
     "max_participants > 0 OR max_participants IS NULL",
     "max_participants <= 0"),
    ("activity_products", "ck_activity_products_max_participants_positive",
     "max_participants > 0 OR max_participants IS NULL",
     "max_participants <= 0"),
]

# Partiële unieke index: max. één primair contact per (persoon, contacttype).
_PRIMARY_CONTACT_IDX = "uq_contact_details_one_primary_per_type"


def upgrade():
    conn = op.get_bind()
    for table, name, expr, violates in _CHECKS:
        if not _table_exists(conn, table):
            continue
        if _has_constraint(conn, table, name):
            continue
        if _no_violation(conn, table, violates):
            op.create_check_constraint(name, table, expr)

    # Partiële unieke index — enkel als er nog geen dubbele primaire contacten zijn.
    if _table_exists(conn, "contact_details") and not _index_exists(
        conn, "contact_details", _PRIMARY_CONTACT_IDX
    ):
        dupes = conn.execute(sa.text(
            "SELECT COUNT(*) FROM ("
            "  SELECT person_id, contact_type_code FROM contact_details "
            "  WHERE is_primary = true "
            "  GROUP BY person_id, contact_type_code HAVING COUNT(*) > 1"
            ") d"
        )).scalar()
        if dupes == 0:
            op.create_index(
                _PRIMARY_CONTACT_IDX,
                "contact_details",
                ["person_id", "contact_type_code"],
                unique=True,
                postgresql_where=sa.text("is_primary = true"),
            )


def downgrade():
    conn = op.get_bind()
    if _table_exists(conn, "contact_details") and _index_exists(
        conn, "contact_details", _PRIMARY_CONTACT_IDX
    ):
        op.drop_index(_PRIMARY_CONTACT_IDX, table_name="contact_details")
    for table, name, _expr, _violates in _CHECKS:
        if _table_exists(conn, table) and _has_constraint(conn, table, name):
            op.drop_constraint(name, table, type_="check")
