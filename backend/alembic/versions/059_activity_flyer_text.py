"""activities.flyer_text + flyer_text_hash — flyertekst-extractie (#206)

De zachte info van een poster (afbeelding/PDF, opgeslagen als media_asset) wordt
éénmalig uitgelezen naar tekst en hier bewaard, zodat de chatbot (#205) ze als
context kan voeden en ze herbruikbaar is als alt-tekst/SEO. ``flyer_text_hash``
is de sha256 van de posterbytes op het moment van extractie, om bij ongewijzigde
poster geen dubbel werk (en geen OCR-kost) te doen.

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
    if not _has_column("activities", "flyer_text"):
        op.add_column("activities", sa.Column("flyer_text", sa.Text(), nullable=True))
    if not _has_column("activities", "flyer_text_hash"):
        op.add_column(
            "activities", sa.Column("flyer_text_hash", sa.String(length=64), nullable=True)
        )


def downgrade():
    if _has_column("activities", "flyer_text_hash"):
        op.drop_column("activities", "flyer_text_hash")
    if _has_column("activities", "flyer_text"):
        op.drop_column("activities", "flyer_text")
