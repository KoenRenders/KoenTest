"""Werkbanktaken verwijzen naar hun onderwerp met een tekst-id (#704).

`WorkflowTask.subject_id` (en die van de instantie) was een `Integer`, terwijl `PaymentRecord.id` een UUID in
een `String(36)` is. Het record-id **paste dus niet in de kolom**, en de drie
betaaltaken vulden er `record.payable_id` in — terwijl `subject_type` wél
`"payment_record"` zei. Het type zei iets wat de waarde niet was, en het echte
record-id leefde alleen in de titeltekst.

Dat brak precies de taak die een link het hardst nodig heeft: bij een
`payment.wees_record` bestáát het payable per definitie niet — dat is de aanleiding
van de taak. Een verwijzing die op het payable steunt, is daar per definitie stuk.

Een onderwerp-id is een **ondoorzichtige sleutel**: hij hoort niet te weten of de
bron een getal of een UUID gebruikt. Vandaar tekst en niet een tweede kolom ernaast —
twee onderwerpvelden leveren bij elke lezing de vraag op welke van de twee gevuld is.

Bestaande waarden zijn getallen en gaan als tekst mee (`USING subject_id::text`).
Idempotent: de kolom wordt alleen omgezet als ze nog geen tekst is.

Revision ID: 092
Revises: 091
"""
import sqlalchemy as sa
from alembic import op

revision = "092"
down_revision = "091"
branch_labels = None
depends_on = None


# Taak én instantie: hetzelfde begrip hoort niet in twee vormen te bestaan. Een
# instantie geeft haar `subject_id` bovendien door aan de taak van elke stap.
TABELLEN = ("workflow_tasks", "workflow_instances")


def upgrade() -> None:
    bind = op.get_bind()
    for tabel in TABELLEN:
        soort = bind.execute(sa.text("""
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = 'workflow' AND table_name = :tabel
              AND column_name = 'subject_id'
        """), {"tabel": tabel}).scalar()
        if soort and soort.lower() in ("integer", "bigint", "smallint"):
            op.execute(sa.text(
                f"ALTER TABLE workflow.{tabel} ALTER COLUMN subject_id "
                "TYPE VARCHAR(36) USING subject_id::text"))


def downgrade() -> None:
    # Terug naar integer kan alleen als élke waarde een getal is; een UUID past niet.
    # Rijen die niet passen worden verwijderd — een werkbanktaak is afgeleide staat
    # die de sweep opnieuw aanmaakt, geen bron van waarheid.
    for tabel in TABELLEN:
        op.execute(sa.text(
            f"DELETE FROM workflow.{tabel} WHERE subject_id !~ '^[0-9]+$'"))
        op.execute(sa.text(
            f"ALTER TABLE workflow.{tabel} ALTER COLUMN subject_id "
            "TYPE INTEGER USING subject_id::integer"))
