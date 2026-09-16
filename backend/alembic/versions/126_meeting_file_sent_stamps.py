"""Verstuurde bijlagen stempelen i.p.v. afleiden (#258).

Koen, 16 september 2026, tijdens het testen op HDEV: *"Als een vergadering
afgesloten is kan je niet zien of een toegevoegde bijlage bij het verslag of de
agenda verstuurd werd."*

Er stond ook niets om te tonen. Een bijlage droeg twee aanvinkvakjes — *mee met
de agenda*, *mee met het verslag* — en dat is een **voornemen**. Of ze echt
vertrokken is werd erbij geredeneerd: "de agendamail is weg én dit vakje stond
aan". Die redenering is fout voor het geval dat het vaakst voorkomt: een bijlage
die je ná de agendamail uploadt voor bij het verslag staat standaard óók voor de
agenda aangevinkt, las dus als verstuurd, en was daarna niet meer te verwijderen
of om te zetten — terwijl ze nooit iemand bereikt had.

Vandaar twee stempels naast de twee vlaggen. Ze worden gezet in dezelfde
transactie als de verzending zelf, dus wat verstuurd is en de vaststelling dát
het verstuurd is kunnen niet uit elkaar lopen.

De backfill zet voor bestaande rijen de best beschikbare waarheid: de oude
afleiding, aangescherpt met de voorwaarde dat het bestand er al wás toen de mail
vertrok. Ouder materiaal krijgt daarmee geen stempel dat het niet verdient.
"""
import sqlalchemy as sa
from alembic import op

revision = "126"
down_revision = "125"
branch_labels = None
depends_on = None


def _kolommen(conn) -> set[str]:
    rijen = conn.execute(sa.text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'meetings' AND table_name = 'meeting_files'
    """)).fetchall()
    return {r[0] for r in rijen}


def upgrade() -> None:
    conn = op.get_bind()
    bestaand = _kolommen(conn)
    if "sent_with_agenda_at" not in bestaand:
        op.add_column("meeting_files",
                      sa.Column("sent_with_agenda_at", sa.DateTime(timezone=True),
                                nullable=True),
                      schema="meetings")
    if "sent_with_report_at" not in bestaand:
        op.add_column("meeting_files",
                      sa.Column("sent_with_report_at", sa.DateTime(timezone=True),
                                nullable=True),
                      schema="meetings")

    # Backfill: alleen waar de mail écht vertrok én het bestand toen al bestond.
    for kolom, vlag, moment in (("sent_with_agenda_at", "on_agenda_mail", "agenda_sent_at"),
                                ("sent_with_report_at", "on_report_mail", "report_sent_at")):
        conn.execute(sa.text(f"""
            UPDATE meetings.meeting_files f
               SET {kolom} = m.{moment}
              FROM meetings.meetings m
             WHERE f.meeting_id = m.id
               AND f.{kolom} IS NULL
               AND f.purpose = 'attachment'
               AND f.{vlag} IS TRUE
               AND m.{moment} IS NOT NULL
               AND f.created_at <= m.{moment}
        """))


def downgrade() -> None:
    op.drop_column("meeting_files", "sent_with_report_at", schema="meetings")
    op.drop_column("meeting_files", "sent_with_agenda_at", schema="meetings")
