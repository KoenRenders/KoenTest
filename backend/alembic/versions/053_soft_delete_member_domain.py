"""Soft delete — leden-domein: deleted_at + partiële uniciteit (#166)

Voegt ``deleted_at`` toe aan de leden-domeintabellen en zet de unieke constraints
om naar **partiële** unieke indexen (``WHERE deleted_at IS NULL``), zodat een
zacht-verwijderd record een nieuw record met dezelfde sleutel niet blokkeert
(bv. opnieuw inschrijven na een verwijderd lidmaatschap).

Revision ID: 050
Revises: 049
"""
from alembic import op
import sqlalchemy as sa

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None

_TABLES = [
    "members", "persons", "member_persons", "memberships",
    "addresses", "contact_details", "external_numbers",
]


def _add_deleted_at(insp, table):
    cols = [c["name"] for c in insp.get_columns(table)]
    if "deleted_at" not in cols:
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index(f"ix_{table}_deleted_at", table, ["deleted_at"])


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in _TABLES:
        _add_deleted_at(insp, table)

    # Volledige uniciteit → partiële uniciteit (enkel op niet-verwijderde rijen).
    op.execute("ALTER TABLE memberships DROP CONSTRAINT IF EXISTS uq_memberships_member_year")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_memberships_member_year "
               "ON memberships (member_id, year) WHERE deleted_at IS NULL")

    op.execute("ALTER TABLE member_persons DROP CONSTRAINT IF EXISTS uq_member_persons_member_person")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_member_persons_member_person "
               "ON member_persons (member_id, person_id) WHERE deleted_at IS NULL")

    op.execute("ALTER TABLE addresses DROP CONSTRAINT IF EXISTS addresses_person_id_key")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_addresses_person_id "
               "ON addresses (person_id) WHERE deleted_at IS NULL")

    op.execute("ALTER TABLE external_numbers DROP CONSTRAINT IF EXISTS uq_external_numbers_source_external_id")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_external_numbers_source_external_id "
               "ON external_numbers (source, external_id) WHERE deleted_at IS NULL")

    # Primary-contact partial index: ook deleted_at meenemen.
    op.execute("DROP INDEX IF EXISTS uq_contact_details_one_primary_per_type")
    op.execute("CREATE UNIQUE INDEX uq_contact_details_one_primary_per_type "
               "ON contact_details (person_id, contact_type_code) "
               "WHERE is_primary = true AND deleted_at IS NULL")


def downgrade():
    # Partiële indexen terug naar volledige constraints (best-effort).
    op.execute("DROP INDEX IF EXISTS uq_memberships_member_year")
    op.execute("ALTER TABLE memberships ADD CONSTRAINT uq_memberships_member_year UNIQUE (member_id, year)")
    op.execute("DROP INDEX IF EXISTS uq_member_persons_member_person")
    op.execute("ALTER TABLE member_persons ADD CONSTRAINT uq_member_persons_member_person UNIQUE (member_id, person_id)")
    op.execute("DROP INDEX IF EXISTS uq_addresses_person_id")
    op.execute("ALTER TABLE addresses ADD CONSTRAINT addresses_person_id_key UNIQUE (person_id)")
    op.execute("DROP INDEX IF EXISTS uq_external_numbers_source_external_id")
    op.execute("ALTER TABLE external_numbers ADD CONSTRAINT uq_external_numbers_source_external_id UNIQUE (source, external_id)")
    op.execute("DROP INDEX IF EXISTS uq_contact_details_one_primary_per_type")
    op.execute("CREATE UNIQUE INDEX uq_contact_details_one_primary_per_type "
               "ON contact_details (person_id, contact_type_code) WHERE is_primary = true")

    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in _TABLES:
        cols = [c["name"] for c in insp.get_columns(table)]
        if "deleted_at" in cols:
            op.drop_index(f"ix_{table}_deleted_at", table_name=table)
            op.drop_column(table, "deleted_at")
