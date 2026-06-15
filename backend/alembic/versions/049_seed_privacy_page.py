"""Seed CMS-pagina 'privacy' (privacyverklaring) (#152)

Een gepubliceerde, bewerkbare privacyverklaring met o.a. de vereiste regel over
de zelf-gehoste, cookieloze web-analytics (Umami, laag 1). De pagina is bewust
NIET in de hoofdnavigatie opgenomen (de frontend filtert slug 'privacy' eruit);
ze wordt gelinkt vanuit de footer. Beheerders kunnen de tekst achteraf aanpassen
via de CMS-beheerpagina.

Idempotent: voegt enkel in als de slug nog niet bestaat (raakt een bestaande,
mogelijk al aangepaste, pagina niet aan).

Revision ID: 049
Revises: 048
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None

PRIVACY_HTML = (
    "<p><em>Laatst bijgewerkt: bij de invoering van bezoekersstatistieken. "
    "Pas deze tekst gerust aan via de CMS-beheerpagina.</em></p>"
    "<h2>Wie zijn we?</h2>"
    "<p>Deze website wordt beheerd door de feitelijke vereniging Raak Millegem "
    "(Milostraat 40, 2400 Mol). Voor vragen over je gegevens kan je ons bereiken "
    "via <a href=\"mailto:raakmillegem@gmail.com\">raakmillegem@gmail.com</a>.</p>"
    "<h2>Welke gegevens verwerken we?</h2>"
    "<ul>"
    "<li><strong>Lidmaatschap en inschrijvingen:</strong> naam, contactgegevens en "
    "gezinssamenstelling die je zelf invult om lid te worden of in te schrijven voor "
    "een activiteit.</li>"
    "<li><strong>Betalingen:</strong> online betalingen verlopen via onze "
    "betaalpartner Mollie. Wij bewaren geen kaart- of rekeninggegevens.</li>"
    "</ul>"
    "<h2>Waarvoor gebruiken we ze?</h2>"
    "<p>Uitsluitend voor onze ledenadministratie, de organisatie van activiteiten en "
    "de afhandeling van betalingen. We verkopen of delen je gegevens niet met derden "
    "voor commerciële doeleinden.</p>"
    "<h2>Bezoekersstatistieken</h2>"
    "<p>Deze website gebruikt Umami, een zelf-gehoste en cookieloze "
    "bezoekersstatistiek. Er worden geen persoonsgegevens verzameld en je IP-adres "
    "wordt geanonimiseerd. We respecteren de Do-Not-Track-instelling van je browser.</p>"
    "<h2>Jouw rechten</h2>"
    "<p>Je kan je gegevens altijd inkijken, laten verbeteren of laten verwijderen. "
    "Stuur daarvoor een e-mail naar "
    "<a href=\"mailto:raakmillegem@gmail.com\">raakmillegem@gmail.com</a>.</p>"
)


def upgrade():
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT id FROM cms_pages WHERE slug = :slug"),
        {"slug": "privacy"},
    ).fetchone()
    if not existing:
        conn.execute(
            sa.text(
                "INSERT INTO cms_pages (title, slug, content, is_published, sort_order, created_at, updated_at) "
                "VALUES (:title, :slug, :content, true, 100, now(), now())"
            ),
            {"title": "Privacyverklaring", "slug": "privacy", "content": PRIVACY_HTML},
        )


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM cms_pages WHERE slug = :slug"), {"slug": "privacy"})
