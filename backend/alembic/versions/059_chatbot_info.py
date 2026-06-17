"""chatbot_info — aparte tabel voor alle tekst die naar de chatbot gaat (#206, #205)

Eén tabel verzamelt alle chatbot-context, los van de domeintabellen:
- een rij kan verwijzen naar een **media-asset** (poster/reglement) → ``extracted_text``
  is de machine-lezing (PDF-tekstlaag/OCR);
- of naar een **CMS-pagina** → opt-out/override van die pagina in de bot-context;
- of naar **niets** → een vrijstaande 'eigen AI-context'-notitie.

Per rij hoogstens één FK (CHECK). Effectieve tekst = COALESCE(text_override, basis)
+ text_addition, met basis = extracted_text (media) of de live pagina-inhoud (cms).
``is_active=false`` → de rij gaat niet naar de bot.

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


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade():
    if _has_table("chatbot_info"):
        return
    op.create_table(
        "chatbot_info",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "media_asset_id", sa.Integer(),
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "cms_page_id", sa.Integer(),
            sa.ForeignKey("cms_pages.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("text_override", sa.Text(), nullable=True),
        sa.Column("text_addition", sa.Text(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_chatbot_info_media_asset_id", "chatbot_info", ["media_asset_id"])
    op.create_index("ix_chatbot_info_cms_page_id", "chatbot_info", ["cms_page_id"])
    # Hoogstens één FK ingevuld: de rij gaat ondubbelzinnig over één ding (#94).
    op.create_check_constraint(
        "ck_chatbot_info_single_fk", "chatbot_info",
        "(CASE WHEN media_asset_id IS NULL THEN 0 ELSE 1 END"
        " + CASE WHEN cms_page_id IS NULL THEN 0 ELSE 1 END) <= 1",
    )


def downgrade():
    if _has_table("chatbot_info"):
        op.drop_table("chatbot_info")
