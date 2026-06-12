"""Zet home-intro om naar placeholders i.p.v. ingebakken bedragen/datums

Migratie 027 vulde de prijzen/datums hard in de content. Daardoor liep de tekst
niet meer mee met de config. Deze migratie vervangt de home-intro-content door
een versie met codes ({{lidgeld_vol}} enz.), die bij het tonen vervangen worden
vanuit de configuratie.

Veiligheid: we vervangen ALLEEN als de content nog exact gelijk is aan wat 027
seedde (= onaangeroerd). Heeft een beheerder de tekst al aangepast, dan laten we
ze met rust.

Revision ID: 028
Revises: 027
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


# Nieuwe content met placeholders.
PLACEHOLDER_CONTENT = (
    "<p>Heb je zin om lid te worden? Het lidmaatschap bedraagt €{{lidgeld_vol}} "
    "voor een gezin. Van {{halfprijs_start}} tot {{halfprijs_einde}} betaal je "
    "slechts €{{lidgeld_half}}. Vanaf {{volgend_jaar_vanaf}} ben je meteen ook "
    "lid voor het volgende jaar.</p>"
    "<p>Heb je gewoon een vraag? Gebruik het contactformulier hieronder.</p>"
)


def _seed_027_content():
    """Reconstrueer exact wat migratie 027 in home-intro zette, om te kunnen
    detecteren of de tekst nog onaangeroerd is."""
    try:
        from app.config import settings
        price_full = str(settings.membership_price_full)
        price_half = str(settings.membership_price_half)
        half_start = settings.membership_half_price_start_md
        half_end = settings.membership_half_price_end_md
        next_year_from = settings.membership_next_year_from_md
    except Exception:
        price_full, price_half = "35.00", "17.50"
        half_start, half_end, next_year_from = "04-16", "09-16", "09-17"

    maanden = ["", "januari", "februari", "maart", "april", "mei", "juni",
               "juli", "augustus", "september", "oktober", "november", "december"]

    def fmt(md):
        m, d = md.split("-")
        return f"{int(d)} {maanden[int(m)]}"

    return (
        f"<p>Heb je zin om lid te worden? Het lidmaatschap bedraagt €{price_full} voor een gezin. "
        f"Van {fmt(half_start)} tot {fmt(half_end)} betaal je slechts €{price_half}. "
        f"Vanaf {fmt(next_year_from)} ben je meteen ook lid voor het volgende jaar.</p>"
        f"<p>Heb je gewoon een vraag? Gebruik het contactformulier hieronder.</p>"
    )


def upgrade():
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT content FROM cms_pages WHERE slug = 'home-intro'")
    ).fetchone()
    if not row:
        return
    if row[0] == _seed_027_content():
        conn.execute(
            sa.text("UPDATE cms_pages SET content = :c, updated_at = now() WHERE slug = 'home-intro'"),
            {"c": PLACEHOLDER_CONTENT},
        )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE cms_pages SET content = :c, updated_at = now() WHERE slug = 'home-intro'"),
        {"c": _seed_027_content()},
    )
