"""Voeg media_assets-tabel toe (assetbibliotheek in Postgres)

Bewaart sponsorlogo's en activiteitenfoto's als BYTEA, met een aparte
thumbnail. Idempotent: maakt de tabel alleen als ze nog niet bestaat.

Revision ID: 030
Revises: 029
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    if "media_assets" in set(insp.get_table_names()):
        return

    op.create_table(
        "media_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("thumbnail", sa.LargeBinary(), nullable=True),
        sa.Column("thumb_content_type", sa.String(50), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("link_url", sa.String(500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_media_assets_kind", "media_assets", ["kind"])
    op.create_index("ix_media_assets_activity_id", "media_assets", ["activity_id"])


def downgrade():
    op.drop_index("ix_media_assets_activity_id", "media_assets")
    op.drop_index("ix_media_assets_kind", "media_assets")
    op.drop_table("media_assets")
