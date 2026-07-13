"""Fase 4c (#404): chatbot_info naar Postgres-schema 'ai'

Revision ID: 084
Revises: 083
"""
from alembic import op
import sqlalchemy as sa

revision = "084"
down_revision = "083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ai")
    bind = op.get_bind()
    in_public = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'chatbot_info'")).scalar()
    if in_public:
        op.execute("ALTER TABLE public.chatbot_info SET SCHEMA ai")
    # Soft-ref (§8): FK naar public.media_assets weg (cross-schema).
    rows = bind.execute(sa.text("""
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.constraint_schema = kcu.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'ai' AND tc.table_name = 'chatbot_info'
          AND kcu.column_name = 'media_asset_id'
    """)).fetchall()
    for (name,) in rows:
        op.execute(f'ALTER TABLE ai.chatbot_info DROP CONSTRAINT IF EXISTS "{name}"')


def downgrade() -> None:
    op.execute("ALTER TABLE ai.chatbot_info SET SCHEMA public")
