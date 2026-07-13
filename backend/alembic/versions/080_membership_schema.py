"""Fase 4a (#402): lidmaatschappen naar Postgres-schema 'membership'

Zelfde recept als 071/075/076/078/079 (§13). member_id is al een soft-ref
(FK gedropt in 078), dus geen cross-schema FK's.

Revision ID: 080
Revises: 079
"""
from alembic import op
import sqlalchemy as sa

revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None

TABLES = ["memberships", "membership_history"]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS membership")
    bind = op.get_bind()
    for table in TABLES:
        in_public = bind.execute(sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"), {"t": table}).scalar()
        if in_public:
            op.execute(f"ALTER TABLE public.{table} SET SCHEMA membership")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"ALTER TABLE membership.{table} SET SCHEMA public")
