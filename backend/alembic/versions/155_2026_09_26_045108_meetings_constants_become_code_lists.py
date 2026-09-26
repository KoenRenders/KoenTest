"""meetings constants become code lists

CR-12 phase 3, the meetings domain. Three lists that were module constants:
the section kinds, the attendance and the purpose of a file. The fourth —
the meeting status — was the pilot of phase 0 and is already done.

Three `CHECK` constraints go with them, for the reason phases 1 and 2 already
met twice: each of them says exactly what its new foreign key says, and with
one in place a fourth value would cost a row *and* a migration. All three are
from #258's own migration: the attendance, the file purpose and the section
kind.

No data change. Every value the three columns hold is in its list; the helper
counts the rows before it adds each key and aborts naming what does not fit.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.meetings.codes import (
    ATTENDANCE_CODES,
    FILE_PURPOSE_CODES,
    SECTION_KIND_CODES,
)
from app.kernel.codes import create_code_list


# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = '155_2026_09_26_045108'
down_revision = '154_2026_09_26_014501'
branch_labels = None
depends_on = None

LIJSTEN = (
    ("section_kind", SECTION_KIND_CODES, 20, "meetings.meeting_sections.kind"),
    ("attendance", ATTENDANCE_CODES, 10, "meetings.meeting_attendances.status"),
    ("file_purpose", FILE_PURPOSE_CODES, 20, "meetings.meeting_files.purpose"),
)

#: De CHECK-constraints die hetzelfde zeggen als de nieuwe foreign keys.
CHECKS = (("meeting_attendances", "ck_meeting_attendances_status"),
          ("meeting_files", "ck_meeting_files_purpose"),
          ("meeting_sections", "ck_meeting_sections_kind"))


def upgrade() -> None:
    for naam, codes, lengte, kolom in LIJSTEN:
        create_code_list(op, schema="meetings", name=naam, codes=codes,
                         fk_from=(kolom,), code_length=lengte)

    bestaand = {}
    for tabel, _c in CHECKS:
        bestaand[tabel] = {c["name"] for c in
                           sa.inspect(op.get_bind()).get_check_constraints(
                               tabel, schema="meetings")}
    for tabel, constraint in CHECKS:
        if constraint in bestaand[tabel]:
            op.drop_constraint(constraint, tabel, schema="meetings", type_="check")


def downgrade() -> None:
    # Schema only: deze migratie schreef geen vergaderdata en veranderde geen
    # bestaande waarde. De kolommen houden wat ze hebben; ze worden alleen niet
    # meer tegen een lijst gecontroleerd.
    op.create_check_constraint("ck_meeting_attendances_status",
                               "meeting_attendances",
                               "status IN ('present','excused')", schema="meetings")
    op.create_check_constraint("ck_meeting_files_purpose", "meeting_files",
                               "purpose IN ('attachment','sent_pdf')",
                               schema="meetings")
    op.create_check_constraint(
        "ck_meeting_sections_kind", "meeting_sections",
        "kind IN ('EVALUATION','UPCOMING','MEMBERS','IDEAS','MISC','CUSTOM')",
        schema="meetings")
    for naam, _codes, _lengte, kolom in LIJSTEN:
        _schema, tabel, kolomnaam = kolom.split(".")
        op.drop_constraint(f"fk_{tabel}_{kolomnaam}_code", tabel,
                           schema="meetings", type_="foreignkey")
        op.drop_table(f"{naam}_labels", schema="meetings")
        op.drop_table(f"{naam}_codes", schema="meetings")
