"""Unieke leesbare deellink per formulier (#690).

De kolom `form.forms.slug` bestond al en `get_form_by_slug` deed er al een
`.first()` op — zonder dat iets twee formulieren met dezelfde slug tegenhield. Die
`.first()` koos er dan stil één, en welk formulier je te zien kreeg hing af van de
volgorde waarin Postgres de rijen teruggaf. Bij `/berichten` betekende dat: een
tweede formulier met die slug kaapt het contactformulier van de site.

Een partiële unieke index (`WHERE slug IS NOT NULL`), want de slug is optioneel:
zonder `WHERE` zou PostgreSQL wél meerdere NULLs toestaan, maar de partiële vorm
zegt duidelijker wat de regel is en houdt de index klein — de meeste formulieren
hebben geen slug.

Idempotent: `IF NOT EXISTS`, zodat een herdraai niet breekt.

De service weigert een dubbele slug al met een leesbare melding (#690); deze index
is het vangnet daaronder (§ validatielagen: integriteit-in-rust hoort in de DB).

Revision ID: 091
Revises: 090
"""
import sqlalchemy as sa
from alembic import op

revision = "091"
down_revision = "090"
branch_labels = None
depends_on = None

INDEX = "ix_forms_slug_uniek"


def upgrade() -> None:
    bind = op.get_bind()
    # Bestaande dubbels zouden het aanmaken van de index laten falen. Ze horen er
    # niet te zijn, maar de import en de JSON-import konden ze aanmaken; maak ze
    # daarom eerst uniek in plaats van de migratie te laten stranden op data die
    # niemand meer kan verklaren. De jongste behoudt zijn slug.
    bind.execute(sa.text("""
        UPDATE form.forms SET slug = slug || '-' || id
        WHERE slug IS NOT NULL AND id NOT IN (
            SELECT MIN(id) FROM form.forms WHERE slug IS NOT NULL GROUP BY slug)
    """))
    op.execute(sa.text(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX} "
        "ON form.forms (slug) WHERE slug IS NOT NULL"))


def downgrade() -> None:
    op.execute(sa.text(f"DROP INDEX IF EXISTS form.{INDEX}"))
