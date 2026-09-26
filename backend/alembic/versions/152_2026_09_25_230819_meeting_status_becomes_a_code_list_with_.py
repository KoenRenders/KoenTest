"""meeting status becomes a code list with a foreign key

CR-12 phase 0, the pilot. The meeting document has three states, and they were
three module constants, a dictionary of Dutch words inside the screen, and a
``String(10)`` column that would accept anything at all.

This list is deliberately the first: three codes, one screen, one badge. Small
enough that a mistake is visible, real enough to prove the four things every
later phase leans on — that ``EnumColumn`` stores the **code** and not the
member name, that a ``Mapped[]`` column can sit beside legacy ``Column()`` ones
in the same model, that the Jinja filter renders the same Dutch words the
screen showed yesterday, and that the gates go red on a violation. §B10 names
that round trip the one spike the money domain should not go ahead of, because
``sa.Enum`` stores the member name by default and that mistake corrupts data
without raising anything.

No data changes here. The three codes are exactly the three values the column
already holds; the helper counts the rows before it adds the foreign key and
aborts, naming any value it does not know, rather than leaving Postgres to
phrase the failure.

**The ``CHECK`` constraint goes.** Migration 122 wrote
``CHECK (status IN ('agenda','report','sent'))`` on the same column. Keeping it
next to the foreign key would be two places holding one fact — the shape
``CLAUDE.md`` calls the bug — and the expensive half is the second one: a fourth
status would be a row in the code table *and* a migration to rewrite the check,
so "a new value is a row" would quietly stop being true. The foreign key says
the same thing and says it against a table that can grow. It also allows what
the check cannot: a retired code keeps a valid target for the rows that still
carry it (§F2).
"""
from alembic import op
import sqlalchemy as sa

from app.domains.meetings.codes import MEETING_STATUS_CODES
from app.kernel.codes import create_code_list


# De id is een tijdstempel en geen volgnummer (#951). Twee CLI's die tegelijk
# "het volgende nummer" kiezen, kiezen hetzelfde; twee die een tijdstempel
# krijgen, kunnen niet botsen. Het volgnummer staat vooraan in de BESTANDSNAAM,
# voor de leesbaarheid en de sortering — alembic kijkt daar niet naar.
revision = '152_2026_09_25_230819'
down_revision = '151_2026_09_25_230812'
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_code_list(op, schema="meetings", name="meeting_status",
                     codes=MEETING_STATUS_CODES,
                     fk_from=("meetings.meetings.status",),
                     code_length=10)
    # Only after the FK: until then the check is the column's only guard.
    op.drop_constraint("ck_meetings_status", "meetings", schema="meetings",
                       type_="check")


def downgrade() -> None:
    # Schema only, and that is the whole story: this migration wrote no meeting
    # data and changed no existing value, so there is nothing about the meetings
    # themselves to restore. The column keeps every value it has; it merely
    # stops being checked against a list.
    op.create_check_constraint("ck_meetings_status", "meetings",
                               "status IN ('agenda','report','sent')",
                               schema="meetings")
    op.drop_constraint("fk_meetings_status_code", "meetings",
                       schema="meetings", type_="foreignkey")
    op.drop_table("meeting_status_labels", schema="meetings")
    op.drop_table("meeting_status_codes", schema="meetings")
