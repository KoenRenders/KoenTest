"""Fase 1b (#399, §19.3): statische API-keys voor machine-consumenten

Tabel auth.api_keys — de key zelf wordt nooit opgeslagen, enkel een
SHA-256-hash met SECRET_KEY-pepper (zelfde recept als de OTP-hashing, #395).

Revision ID: 077
Revises: 076
"""
from alembic import op
import sqlalchemy as sa

revision = "077"
down_revision = "076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'auth' AND table_name = 'api_keys'")).scalar()
    if exists:
        return
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        schema="auth",
    )


def downgrade() -> None:
    op.drop_table("api_keys", schema="auth")
