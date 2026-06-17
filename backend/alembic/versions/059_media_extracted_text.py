"""media_assets.extracted_text + extracted_at — documenttekst-extractie (#206)

De 'zachte' info van een poster of reglement (afbeelding/PDF, opgeslagen als
media_asset) wordt éénmalig uitgelezen naar tekst en op het **media-record**
bewaard — daar hoort de tekst thuis (het is de tekst van dát bestand) en het
generaliseert naar zowel ``activity_poster`` als ``component_info``. De chatbot
(#205) voedt die tekst als context.

Bewust op het asset-record en niet op de activiteit: een nieuwe upload is een
nieuw record (oude wordt hard verwijderd), dus geen aparte hash-logica nodig —
een vers record heeft nog geen ``extracted_text`` en wordt één keer uitgelezen.

Revision ID: 059
Revises: 058
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    cols = [c["name"] for c in inspect(op.get_bind()).get_columns(table)]
    return column in cols


def upgrade():
    if not _has_column("media_assets", "extracted_text"):
        op.add_column("media_assets", sa.Column("extracted_text", sa.Text(), nullable=True))
    if not _has_column("media_assets", "extracted_at"):
        op.add_column(
            "media_assets",
            sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    if _has_column("media_assets", "extracted_at"):
        op.drop_column("media_assets", "extracted_at")
    if _has_column("media_assets", "extracted_text"):
        op.drop_column("media_assets", "extracted_text")
