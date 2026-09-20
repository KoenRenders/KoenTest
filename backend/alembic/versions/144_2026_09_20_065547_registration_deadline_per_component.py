"""The registration deadline moves from the activity to the component (#1053).

Koen, 20 September 2026, with a real case: at *Brood en Spelen* the barbecue stops
taking registrations a week before the day, while cornhole and sjoelbak stay open
until the day itself. One deadline on the activity cannot say that — it closes
every component at once.

So the column does not get a twin on the component with the activity as a fallback:
it MOVES. One place per fact was worth more to Koen than saving a form field.

**The copy step matters even though it counts nothing today.** PROD runs v2.4.0 and
does not know the column at all; on HDEV exactly one activity of 177 had a date. But
the v2.5 chain replays #974 (add the column) and then this one on PROD, so the copy
has to be there for the case it never meets.

Idempotent in both directions: the copy only runs while the old column still exists,
and each column is only added when it is missing.
"""
from alembic import op
import sqlalchemy as sa


# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = '144_2026_09_20_065547'
down_revision = '143_2026_09_20_062539'
branch_labels = None
depends_on = None

KOLOM = "registration_closes_on"

#: De kopieerstap als losse tekst, zodat `tests/test_inschrijfdatum_per_onderdeel.py`
#: hem kan draaien zonder een alembic-context. Eén bron: een test die de SQL
#: overtypt, toetst haar eigen kopie.
KOPIEER = (
    "UPDATE activities.activity_sub_registrations c "
    f"SET {KOLOM} = a.{KOLOM} "
    "FROM activities.activities a "
    f"WHERE c.activity_id = a.id AND a.{KOLOM} IS NOT NULL "
    f"AND c.{KOLOM} IS NULL")

#: De omkering: terug naar één datum per activiteit. Zie `downgrade`.
HERSTEL = (
    "UPDATE activities.activities a "
    f"SET {KOLOM} = (SELECT MIN(c.{KOLOM}) "
    "  FROM activities.activity_sub_registrations c "
    f" WHERE c.activity_id = a.id AND c.{KOLOM} IS NOT NULL)")


def _heeft_kolom(tabel: str) -> bool:
    return bool(op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'activities' AND table_name = :t "
        "AND column_name = :k"), {"t": tabel, "k": KOLOM}).scalar())


def upgrade() -> None:
    if not _heeft_kolom("activity_sub_registrations"):
        op.add_column("activity_sub_registrations",
                      sa.Column(KOLOM, sa.Date, nullable=True),
                      schema="activities")
    # Kopiëren vóór laten vallen, en alleen zolang de oude kolom er nog is.
    if _heeft_kolom("activities"):
        op.execute(sa.text(KOPIEER))
        op.drop_column("activities", KOLOM, schema="activities")


def downgrade() -> None:
    """Herstelt het schema én zoveel van de data als eerlijk kan.

    Terug naar één datum per activiteit betekent kiezen welke: verschillende
    datums per onderdeel passen niet in één kolom. De downgrade neemt de VROEGSTE
    — dat is de veilige kant, want ze sluit eerder in plaats van iemand binnen te
    laten na de dag waarop zijn onderdeel al dicht was.
    """
    if not _heeft_kolom("activities"):
        op.add_column("activities", sa.Column(KOLOM, sa.Date, nullable=True),
                      schema="activities")
    if _heeft_kolom("activity_sub_registrations"):
        op.execute(sa.text(HERSTEL))
        op.drop_column("activity_sub_registrations", KOLOM, schema="activities")
