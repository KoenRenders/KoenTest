"""De interne bestuursnota van een activiteit (#1028).

`activities.notes` bestond sinds #402 en de modelcode zei erbij dat de kolom
nergens getoond werd. Dat klopte niet: `chatbot/tools.py` zette hem in het
antwoord van `get_activity_detail` — de tool van de **publieke** bot. Alles
daarin gaat integraal naar het model en dus naar wie het vraagt.

Een veld dat "interne nota" heet en tegelijk aan de publieke chat hangt, is een
lek dat op iedereen wacht die er ooit iets in typt. De kolom verdwijnt daarom,
en de nieuwe nota begint **leeg** onder een andere naam.

**De inhoud gaat verloren, en dat is een beslissing** (Koen, 19 september 2026):
het is oude rommel uit de vorige toepassing — op HDEV 38 van de 176 rijen, tot
een vijftigtal tekens — en wat eraan relevant was, heeft intussen een eigen veld
(`description`, #1016).

**Hergebruik van de naam is bewust vermeden.** `notes` opnieuw gebruiken met een
andere betekenis, terwijl de bot er nog op aangesloten zou kunnen zijn, is exact
hoe dit gat ontstond: één naam, twee betekenissen, en niemand die het verschil
ziet in een diff.

Idempotent: elke stap kijkt eerst of hij nodig is.
"""
from alembic import op
import sqlalchemy as sa

# De id is een tijdstempel en geen volgnummer (#951) — maar twee CLI's kozen op
# 19 september hetzelfde tijdstip, dus deze draagt een eigen: onder de
# designstudio-migratie die intussen op master stond.
revision = "138_2026_09_19_183000"
down_revision = "137_2026_09_19_160000"
branch_labels = None
depends_on = None


def _has_column(kolom: str) -> bool:
    return bool(op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = 'activities' "
        "AND table_name = 'activities' AND column_name = :c"), {"c": kolom}).scalar())


def upgrade() -> None:
    if not _has_column("board_notes"):
        op.add_column("activities", sa.Column("board_notes", sa.Text, nullable=True),
                      schema="activities")
    if _has_column("notes"):
        op.drop_column("activities", "notes", schema="activities")


def downgrade() -> None:
    # De oude inhoud komt niet terug: ze is bij de upgrade verdwenen en stond
    # nergens anders. Wat een downgrade herstelt is de VORM, niet de gegevens.
    if not _has_column("notes"):
        op.add_column("activities", sa.Column("notes", sa.Text, nullable=True),
                      schema="activities")
    if _has_column("board_notes"):
        op.drop_column("activities", "board_notes", schema="activities")
