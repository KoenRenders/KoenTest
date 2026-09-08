"""Hernummer dubbele posities in het formulierendomein (#725).

Een bewerkt veld sprong naar onderen. Drie lagen samen:

1. veel rijen dragen dezelfde `position` — op HDEV 22 groepen dubbele velden en
   66 groepen dubbele opties, allemaal op 0, afkomstig van een JSON-import die de
   default 0 letterlijk overnam;
2. er werd gesorteerd zonder tiebreaker, en `sorted` is stabiel, dus bij gelijkspel
   bleef de DB-volgorde staan;
3. een UPDATE schrijft in PostgreSQL een nieuwe tupelversie achteraan de heap, dus
   het bewerkte veld schoof naar het einde van zijn gelijkspel-groep.

De code krijgt de tiebreaker `(position, id)`; deze migratie ruimt de dubbels op,
zodat de volgorde ook zonder die tiebreaker eenduidig is. Hernummerd wordt op
`(position, id)` — dezelfde sleutel — zodat de volgorde die de gebruiker vandaag
op het scherm ziet exact bewaard blijft.

Bewust GEEN unieke constraint op `(section_id, position)`: omwisselen gaat door een
tussentoestand met gelijke waarden en zou daarop stuklopen.

Idempotent: `IS DISTINCT FROM` maakt er een no-op van zodra de nummering al dicht
en op volgorde is — een tweede run schrijft geen enkele rij.
"""
from alembic import op

revision = "093"
down_revision = "092"
branch_labels = None
depends_on = None


# Velden hangen aan een formulier én optioneel aan een sectie; losse velden vormen
# hun eigen groep. Vandaar (form_id, section_id) als partitie, met NULL als groep.
HERNUMMERINGEN = (
    ("form.form_sections", "form_id"),
    ("form.form_fields", "form_id, section_id"),
    ("form.form_field_options", "field_id"),
)


def hernummer_sql(tabel: str, partitie: str) -> str:
    """De hernummering als losse SQL, zodat een test haar kan uitvoeren.

    Een migratie draait in de suite vóór er data is, dus wat ze met bestaande
    dubbels doet is anders niet te toetsen — en een datastap die stil niets doet,
    laat precies de rijen staan waarvoor ze geschreven is.
    """
    return f"""
        WITH genummerd AS (
            SELECT id,
                   ROW_NUMBER() OVER (PARTITION BY {partitie}
                                      ORDER BY position, id) - 1 AS nieuw
            FROM {tabel}
        )
        UPDATE {tabel} AS t
           SET position = g.nieuw
          FROM genummerd AS g
         WHERE t.id = g.id
           AND t.position IS DISTINCT FROM g.nieuw
    """


def upgrade() -> None:
    for tabel, partitie in HERNUMMERINGEN:
        op.execute(hernummer_sql(tabel, partitie))


def downgrade() -> None:
    # Niet terug te draaien: de oude posities waren juist de dubbels die hier
    # weggenomen zijn, en welke rij welke dubbel had is nergens bewaard. De nieuwe
    # nummering is een superset van de oude volgorde, dus terugdraaien zou geen
    # informatie herstellen — alleen weer ambiguïteit maken.
    pass
