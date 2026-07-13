"""Fase 4c (#404): media_assets naar schema 'media'; business_events naar het
rapportageschema 'analytics' (§5.8)

Revision ID: 085
Revises: 084
"""
from alembic import op
import sqlalchemy as sa

revision = "085"
down_revision = "084"
branch_labels = None
depends_on = None

MOVES = [("media", "media_assets"), ("analytics", "business_events")]


def upgrade() -> None:
    bind = op.get_bind()
    for schema, table in MOVES:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        in_public = bind.execute(sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"), {"t": table}).scalar()
        if in_public:
            op.execute(f"ALTER TABLE public.{table} SET SCHEMA {schema}")
    # business_events had FK's naar activiteiten/betalingen? -> soft-refs (§8):
    for column in ("activity_id", "payment_record_id"):
        rows = bind.execute(sa.text("""
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.constraint_schema = kcu.constraint_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'analytics' AND tc.table_name = 'business_events'
              AND kcu.column_name = :c
        """), {"c": column}).fetchall()
        for (name,) in rows:
            op.execute(f'ALTER TABLE analytics.business_events DROP CONSTRAINT IF EXISTS "{name}"')


def downgrade() -> None:
    op.execute("ALTER TABLE analytics.business_events SET SCHEMA public")
    op.execute("ALTER TABLE media.media_assets SET SCHEMA public")
