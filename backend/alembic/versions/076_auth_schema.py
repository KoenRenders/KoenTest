"""Fase 1b (#399): users, user_roles en login_tokens naar Postgres-schema 'auth'

Zelfde recept als 071/075 (§13): puur namespacing via ALTER TABLE ... SET SCHEMA,
geen datawijziging. Indexen en FK's verhuizen mee. De FK user_roles.role_code ->
public.role_codes wordt gedropt (§8: geen cross-schema FK's — die zouden
onafhankelijk deployen breken); rolcode-validatie verhuist naar de servicelaag.

Revision ID: 076
Revises: 075
"""
from alembic import op
import sqlalchemy as sa

revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None

TABLES = ["users", "user_roles", "login_tokens"]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")
    bind = op.get_bind()
    for table in TABLES:
        in_public = bind.execute(sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"), {"t": table}).scalar()
        if in_public:
            op.execute(f"ALTER TABLE public.{table} SET SCHEMA auth")
    # Geen cross-schema FK's (§8): user_roles.role_code -> public.role_codes eruit.
    op.execute("ALTER TABLE auth.user_roles DROP CONSTRAINT IF EXISTS user_roles_role_code_fkey")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"ALTER TABLE auth.{table} SET SCHEMA public")
