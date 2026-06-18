"""Voeg de spraakinvoer-sectie toe aan de privacy-pagina (#282)

Breidt de bestaande privacyverklaring (slug 'privacy', geseed in 049) uit met een
sectie over de spraakinvoer (STT) van chatbot Raakje: waar de spraak verwerkt wordt
afhankelijk van de browser (native cloud-STT buiten de EU, of de EU-fallback via
Voxtral/Mistral, Frankrijk).

Idempotent: voegt enkel toe als de privacy-pagina bestaat én de sectie er nog niet
in staat (marker 'Spraakinvoer'). Bestaande, mogelijk via de CMS aangepaste, content
blijft behouden — de sectie wordt achteraan toegevoegd.

LET OP: deze tekst beschrijft de Voxtral/EU-fallback. Ze is correct zodra STT actief
is (STT_MODE=native_first/provider_only). Draait een omgeving op STT_MODE=browser_only
(geen Voxtral), dan beschrijft ze functionaliteit die daar (nog) niet live is.

Revision ID: 061
Revises: 060
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None

SECTION_MARKER = "Spraakinvoer"

STT_HTML = (
    "<h2>Spraakinvoer (&quot;praten met Raakje&quot;)</h2>"
    "<p>Je kunt vragen aan onze chatbot Raakje ook inspreken in plaats van typen. "
    "Spraakinvoer is volledig optioneel: je kunt elke vraag ook gewoon intypen, en je "
    "microfoon wordt pas gebruikt nadat je daar toestemming voor geeft.</p>"
    "<p>Hoe je spraak wordt verwerkt, hangt af van je browser:</p>"
    "<ul>"
    "<li><strong>Browsers met ingebouwde spraakherkenning</strong> sturen je audio naar "
    "de servers van hun maker, die zich buiten de Europese Unie (in de Verenigde Staten) "
    "bevinden. Dit geldt onder meer voor Google Chrome (Google), Microsoft Edge "
    "(Microsoft) en Safari (Apple). Gebruik je zo'n browser, dan verlaat je gesproken "
    "bericht de EU en gelden mede de privacyvoorwaarden van die leverancier.</li>"
    "<li><strong>Browsers zonder ingebouwde cloud-spraakherkenning</strong> — zoals "
    "Mozilla Firefox, Vivaldi en Opera — sturen je spraak niet naar zulke partijen. Voor "
    "die browsers zetten wij je spraak om via een Europese verwerker (Mistral AI, "
    "Frankrijk), zodat de audio binnen de EU verwerkt wordt.</li>"
    "</ul>"
    "<p>In beide gevallen gebruiken we je spraak uitsluitend om je vraag naar tekst om te "
    "zetten; de audio wordt enkel kortstondig verwerkt en wij bewaren geen opnames.</p>"
    "<p><strong>Wil je dat je gesproken berichten de EU niet verlaten?</strong> Gebruik "
    "dan een browser zonder ingebouwde cloud-spraakherkenning (bijvoorbeeld Mozilla "
    "Firefox, Vivaldi of Opera), of typ je vraag gewoon in.</p>"
)


def upgrade():
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT content FROM cms_pages WHERE slug = :slug"),
        {"slug": "privacy"},
    ).fetchone()
    if row is None:
        return  # privacy-pagina bestaat niet → niets toe te voegen
    content = row[0] or ""
    if SECTION_MARKER in content:
        return  # sectie al aanwezig → niet dubbel toevoegen
    conn.execute(
        sa.text(
            "UPDATE cms_pages SET content = :content, updated_at = now() WHERE slug = :slug"
        ),
        {"content": content + STT_HTML, "slug": "privacy"},
    )


def downgrade():
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT content FROM cms_pages WHERE slug = :slug"),
        {"slug": "privacy"},
    ).fetchone()
    if row is None:
        return
    content = row[0] or ""
    if STT_HTML in content:
        conn.execute(
            sa.text(
                "UPDATE cms_pages SET content = :content, updated_at = now() WHERE slug = :slug"
            ),
            {"content": content.replace(STT_HTML, ""), "slug": "privacy"},
        )
