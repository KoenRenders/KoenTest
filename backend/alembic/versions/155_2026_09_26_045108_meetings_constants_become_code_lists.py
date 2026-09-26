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


# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that are handed a
# timestamp cannot collide. The sequence number leads the FILE NAME, for
# reading and sorting — alembic does not look at it.
revision = '155_2026_09_26_045108'
down_revision = '154_2026_09_26_014501'
branch_labels = None
depends_on = None

LISTS = (
    ("section_kind", SECTION_KIND_CODES, 20, "meetings.meeting_sections.kind"),
    ("attendance", ATTENDANCE_CODES, 10, "meetings.meeting_attendances.status"),
    ("file_purpose", FILE_PURPOSE_CODES, 20, "meetings.meeting_files.purpose"),
)

#: The CHECK constraints that say the same as the new foreign keys.
CHECKS = (("meeting_attendances", "ck_meeting_attendances_status"),
          ("meeting_files", "ck_meeting_files_purpose"),
          ("meeting_sections", "ck_meeting_sections_kind"))


def upgrade() -> None:
    for name, codes, length, column in LISTS:
        create_code_list(op, schema="meetings", name=name, codes=codes,
                         fk_from=(column,), code_length=length)

    existing = {}
    for table, _c in CHECKS:
        existing[table] = {c["name"] for c in
                           sa.inspect(op.get_bind()).get_check_constraints(
                               table, schema="meetings")}
    for table, constraint in CHECKS:
        if constraint in existing[table]:
            op.drop_constraint(constraint, table, schema="meetings", type_="check")


def downgrade() -> None:
    # Schema only: this migration wrote no meeting data and changed no existing
    # value. The columns keep what they hold; they are just no longer checked
    # against a list.
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
    for name, _codes, _length, column in LISTS:
        _schema, table, column_name = column.split(".")
        op.drop_constraint(f"fk_{table}_{column_name}_code", table,
                           schema="meetings", type_="foreignkey")
        op.drop_table(f"{name}_labels", schema="meetings")
        op.drop_table(f"{name}_codes", schema="meetings")
