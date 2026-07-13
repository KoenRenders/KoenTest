"""Fase 1a (#399): email_log naar eigen Postgres-schema 'mail'

Zelfde recept als 071 (§13): puur namespacing via ALTER TABLE ... SET SCHEMA,
geen datawijziging; pg_dump blijft één commando (§13.1).

Revision ID: 075
Revises: 074
"""
from alembic import op
import sqlalchemy as sa

revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS mail")
    bind = op.get_bind()
    in_public = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'email_log'")).scalar()
    if in_public:
        op.execute("ALTER TABLE public.email_log SET SCHEMA mail")


def downgrade() -> None:
    op.execute("ALTER TABLE mail.email_log SET SCHEMA public")
