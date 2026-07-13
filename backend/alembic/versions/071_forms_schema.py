"""Fase 0 (#397): forms-tabellen naar eigen Postgres-schema 'form'

Data-verhuis conform §13: puur namespacing (ALTER TABLE ... SET SCHEMA), geen
datawijziging; pg_dump blijft één commando (§13.1).

Revision ID: 071
Revises: 070
"""
from alembic import op
import sqlalchemy as sa

revision = "071"
down_revision = "070"
branch_labels = None
depends_on = None

TABLES = ["forms", "form_sections", "form_fields", "form_field_options",
          "form_submissions", "form_submission_answers"]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS form")
    bind = op.get_bind()
    for table in TABLES:
        in_public = bind.execute(sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"), {"t": table}).scalar()
        if in_public:
            op.execute(f"ALTER TABLE public.{table} SET SCHEMA form")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"ALTER TABLE form.{table} SET SCHEMA public")
