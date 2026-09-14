"""Seed CMS-blokken: home-intro en site-footer

De content bevat variabelen die bij seeding worden ingevuld vanuit de
app-configuratie (lidmaatschapsprijzen en -datumgrenzen). Zo blijft de
DB-inhoud in sync met de .env-waarden op het moment van de eerste deploy.
Beheerders kunnen de content achteraf aanpassen via de CMS-beheerpagina.

Revision ID: 027
Revises: 026
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def _build_home_intro(price_full: str, price_half: str,
                      half_start: str, half_end: str,
                      next_year_from: str) -> str:
    """Zet MM-DD datumstrings om naar leesbare datums en bouw de intro-HTML."""
    def fmt(md: str) -> str:
        m, d = md.split("-")
        maanden = ["", "januari", "februari", "maart", "april", "mei", "juni",
                   "juli", "augustus", "september", "oktober", "november", "december"]
        return f"{int(d)} {maanden[int(m)]}"

    return (
        f"<p>Heb je zin om lid te worden? Het lidmaatschap bedraagt €{price_full} voor een gezin. "
        f"Van {fmt(half_start)} tot {fmt(half_end)} betaal je slechts €{price_half}. "
        f"Vanaf {fmt(next_year_from)} ben je meteen ook lid voor het volgende jaar.</p>"
        f"<p>Heb je gewoon een vraag? Gebruik het contactformulier hieronder.</p>"
    )


def upgrade():
    conn = op.get_bind()

    # Haal de config-waarden op.  Fallback op standaardwaarden als de
    # settings-module niet beschikbaar is (bv. bij offline migratie-checks).
    try:
        from app.config import settings
        price_full = str(settings.membership_price_full)
        price_half = str(settings.membership_price_half)
        half_start = settings.membership_half_price_start_md
        half_end = settings.membership_half_price_end_md
        next_year_from = settings.membership_next_year_from_md
    except Exception:
        price_full = "35.00"
        price_half = "17.50"
        half_start = "04-16"
        half_end = "09-16"
        next_year_from = "09-17"

    intro_html = _build_home_intro(price_full, price_half, half_start, half_end, next_year_from)

    # PLACEHOLDERS, en met opzet (#917, 14 september 2026). Hier stond de echte
    # contactregel van Raak Millegem: naam, straat, gemeente, e-mailadres, IBAN en
    # BIC. Drie bezwaren, en het derde is het zwaarste:
    #
    # 1. Deze repo is publiek en een rekeningnummer hoort in de linkerkolom van de
    #    maskeertabel in CLAUDE.md.
    # 2. Elke VERSE installatie van deze stack kreeg hiermee de contactgegevens van
    #    één vereniging als standaardfooter. Dat is niet alleen lelijk, het is fout:
    #    de tweede afdeling die dit draait, publiceert andermans adres.
    # 3. Een migratiebestand verdwijnt nooit uit de geschiedenis. Dit vervangen is
    #    dus opruimen en geen ongedaan maken — de oude waarde blijft in de git-log
    #    staan. Om die reden is de BIC hier helemaal weg in plaats van vervangen:
    #    wat niemand nodig heeft, zaaien we niet opnieuw.
    #
    # Dit RAAKT BESTAANDE DATABANKEN NIET. De insert hieronder slaat over wat er al
    # staat, dus een omgeving die 027 ooit gedraaid heeft, houdt haar footer zoals
    # ze is; wie hem daar wil wijzigen, doet dat in het CMS-scherm. Dit blok bepaalt
    # alleen wat een lege databank krijgt.
    #
    # De BETAALGEGEVENS lopen hier niet langs: de overschrijvingsinstructies in de
    # mails en op de lidmaatschapsschermen komen uit `payment_iban` /
    # `payment_beneficiary` (tenant-instelling, met de .env als terugval). Deze
    # footer is contacttekst, geen geldpad — vandaar dat placeholders hier niets
    # kunnen breken aan een betaling.
    footer_html = (
        "<p>&laquo;Naam van de vereniging&raquo; · &laquo;straat en nummer&raquo;, "
        "&laquo;postcode en gemeente&raquo;</p>"
        "<p>📧 &laquo;e-mailadres&raquo; · IBAN: &laquo;rekeningnummer&raquo;</p>"
    )

    for slug, title, content in [
        ("home-intro", "Home intro", intro_html),
        ("site-footer", "Site footer", footer_html),
    ]:
        existing = conn.execute(
            sa.text("SELECT id FROM cms_pages WHERE slug = :slug"),
            {"slug": slug},
        ).fetchone()
        if not existing:
            conn.execute(
                sa.text(
                    "INSERT INTO cms_pages (title, slug, content, is_published, sort_order, created_at, updated_at) "
                    "VALUES (:title, :slug, :content, false, -1, now(), now())"
                ),
                {"title": title, "slug": slug, "content": content},
            )


def downgrade():
    conn = op.get_bind()
    for slug in ("home-intro", "site-footer"):
        conn.execute(sa.text("DELETE FROM cms_pages WHERE slug = :slug"), {"slug": slug})
