"""Fase 4a (#402): activiteiten en registraties naar Postgres-schema 'activities'

Zelfde recept als de vorige schema-verhuizen (§13). Extra: de cross-schema
FK's naar public.registration_type_codes worden gedropt (§8) — de code wordt
door de Pydantic-schema's gevalideerd; registrations.person_id was al een
soft-ref (078).

Revision ID: 081
Revises: 080
"""
from alembic import op
import sqlalchemy as sa

revision = "081"
down_revision = "080"
branch_labels = None
depends_on = None

TABLES = [
    "activities", "activity_dates", "activity_sub_registrations",
    "activity_products", "registrations", "registration_items",
    "registration_item_history", "activity_history", "activity_date_history",
    "component_history", "product_history",
]

CODE_FKS = [("activities", "registrations", "registration_type"),
            ("activities", "activity_sub_registrations", "registration_type_code"),
            # media_assets blijft in public; FK's naar activiteiten worden soft-refs (§8)
            ("public", "media_assets", "activity_id"),
            ("public", "media_assets", "component_id")]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS activities")
    bind = op.get_bind()
    for table in TABLES:
        in_public = bind.execute(sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"), {"t": table}).scalar()
        if in_public:
            op.execute(f"ALTER TABLE public.{table} SET SCHEMA activities")

    for schema, table, column in CODE_FKS:
        rows = bind.execute(sa.text("""
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.constraint_schema = kcu.constraint_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = :s AND tc.table_name = :t
              AND kcu.column_name = :c
        """), {"s": schema, "t": table, "c": column}).fetchall()
        for (name,) in rows:
            op.execute(f'ALTER TABLE {schema}.{table} DROP CONSTRAINT IF EXISTS "{name}"')


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"ALTER TABLE activities.{table} SET SCHEMA public")
