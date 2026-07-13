"""Fase 4c (#404): cms_pages naar Postgres-schema 'cms'

Revision ID: 083
Revises: 082
"""
from alembic import op
import sqlalchemy as sa

revision = "083"
down_revision = "082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS cms")
    bind = op.get_bind()
    in_public = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'cms_pages'")).scalar()
    if in_public:
        op.execute("ALTER TABLE public.cms_pages SET SCHEMA cms")
    # Soft-ref (§8): chatbot_info.cms_page_id verwijst cross-schema — FK weg.
    rows = bind.execute(sa.text("""
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.constraint_schema = kcu.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public' AND tc.table_name = 'chatbot_info'
          AND kcu.column_name = 'cms_page_id'
    """)).fetchall()
    for (name,) in rows:
        op.execute(f'ALTER TABLE public.chatbot_info DROP CONSTRAINT IF EXISTS "{name}"')


def downgrade() -> None:
    op.execute("ALTER TABLE cms.cms_pages SET SCHEMA public")
