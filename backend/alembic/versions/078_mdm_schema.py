"""Fase 2 (#400): masterdata naar Postgres-schema 'mdm' + survivorship + organisaties

Zelfde recept als 071/075/076 (§13): namespacing via ALTER TABLE ... SET SCHEMA.
Daarnaast:
- soft-ref-patroon (§6/§8): de cross-schema FK's van buiten naar de masterdata
  (registrations.person_id, memberships.member_id) worden gedropt — consumenten
  bewaren het id als waarde en lezen via de mdm-facade;
- persons.superseded_by_id (merge/survivorship, binnen-schema-FK);
- nieuwe tabel mdm.organizations (ACCOUNT/UNIT, zelf-refererend).

Revision ID: 078
Revises: 077
"""
from alembic import op
import sqlalchemy as sa

revision = "078"
down_revision = "077"
branch_labels = None
depends_on = None

TABLES = [
    "persons", "members", "member_persons", "addresses", "contact_details",
    "postal_codes", "external_numbers", "gender_codes", "contact_type_codes",
    "relation_type_codes", "person_history", "member_history",
    "member_person_history", "address_history", "contact_detail_history",
]

# (schema.tabel, kolom) van buitenaf → masterdata: FK weg, waarde blijft.
SOFT_REFS = [
    ("public", "registrations", "person_id"),
    ("public", "memberships", "member_id"),
]


def _drop_fk(bind, schema: str, table: str, column: str) -> None:
    rows = bind.execute(sa.text("""
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.constraint_schema = kcu.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = :s AND tc.table_name = :t AND kcu.column_name = :c
    """), {"s": schema, "t": table, "c": column}).fetchall()
    for (name,) in rows:
        op.execute(f'ALTER TABLE {schema}.{table} DROP CONSTRAINT IF EXISTS "{name}"')


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS mdm")
    bind = op.get_bind()
    for table in TABLES:
        in_public = bind.execute(sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"), {"t": table}).scalar()
        if in_public:
            op.execute(f"ALTER TABLE public.{table} SET SCHEMA mdm")

    for schema, table, column in SOFT_REFS:
        _drop_fk(bind, schema, table, column)

    has_col = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = 'mdm' "
        "AND table_name = 'persons' AND column_name = 'superseded_by_id'")).scalar()
    if not has_col:
        op.add_column("persons", sa.Column("superseded_by_id", sa.Integer(),
                                           sa.ForeignKey("mdm.persons.id"), nullable=True),
                      schema="mdm")
        op.create_index("ix_mdm_persons_superseded_by_id", "persons",
                        ["superseded_by_id"], schema="mdm")

    has_org = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'mdm' AND table_name = 'organizations'")).scalar()
    if not has_org:
        op.create_table(
            "organizations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("parent_id", sa.Integer(), sa.ForeignKey("mdm.organizations.id"), nullable=True),
            sa.Column("org_type", sa.String(10), nullable=False, server_default="ACCOUNT"),
            sa.Column("code", sa.String(50), nullable=False, unique=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("org_type IN ('ACCOUNT', 'UNIT')", name="ck_org_type"),
            schema="mdm",
        )


def downgrade() -> None:
    op.drop_table("organizations", schema="mdm")
    op.drop_index("ix_mdm_persons_superseded_by_id", "persons", schema="mdm")
    op.drop_column("persons", "superseded_by_id", schema="mdm")
    for table in reversed(TABLES):
        op.execute(f"ALTER TABLE mdm.{table} SET SCHEMA public")
