"""Voeg ontbrekende indexes toe voor veelgebruikte query-velden (#3)

Idempotent: elke index wordt enkel aangemaakt als hij nog niet bestaat.
FK-kolommen op junction-tabellen (member_persons) krijgen al een index van
PostgreSQL bij de FK-constraint; die staan niet in deze lijst.

Revision ID: 041
Revises: 040
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def _table_exists(conn, table):
    return table in Inspector.from_engine(conn).get_table_names()


def _index_exists(conn, table, name):
    return any(ix["name"] == name for ix in Inspector.from_engine(conn).get_indexes(table))


# (tabel, indexnaam, kolom(men))
_INDEXES = [
    ("activities", "ix_activities_date", ["date"]),
    ("activities", "ix_activities_date_end", ["date_end"]),
    ("registrations", "ix_registrations_activity_id", ["activity_id"]),
    ("registrations", "ix_registrations_component_id", ["component_id"]),
    ("registrations", "ix_registrations_is_waitlist", ["is_waitlist"]),
    ("memberships", "ix_memberships_member_id_year", ["member_id", "year"]),
    ("memberships", "ix_memberships_is_active", ["is_active"]),
]


def upgrade():
    conn = op.get_bind()
    for table, name, columns in _INDEXES:
        if not _table_exists(conn, table):
            continue
        if _index_exists(conn, table, name):
            continue
        op.create_index(name, table, columns)


def downgrade():
    conn = op.get_bind()
    for table, name, _columns in _INDEXES:
        if _table_exists(conn, table) and _index_exists(conn, table, name):
            op.drop_index(name, table_name=table)
