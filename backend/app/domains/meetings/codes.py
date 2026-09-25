"""The code lists the meetings domain owns (CR-12).

`meeting_status` is the **pilot** of CR-12: three codes, one screen, one badge,
migrated end to end in phase 0 before the money domain is touched. It is small
enough that a mistake is visible and real enough to prove the four things the
rest of the change rests on — that `EnumColumn` writes the code and not the
member name, that a `Mapped[]` column can sit next to legacy `Column()` ones,
that the Jinja filter renders the same Dutch words the screen showed before,
and that the gates fail on a violation rather than staying green.

The other three lists of this domain (`section_kind`, `attendance`,
`file_purpose`) follow in phase 3, together with newsletter and design studio.
"""
from app.domains.meetings.models import (
    MeetingStatus,
    MeetingStatusCode,
    MeetingStatusLabel,
)
from app.kernel.codes import CodeList, CodeSeed

MEETING_STATUS_CODES = (
    CodeSeed(code="agenda", nl="Agenda", en="Agenda", sort_order=10),
    CodeSeed(code="report", nl="Verslag (bezig)", en="Report (in progress)",
             sort_order=20),
    CodeSeed(code="sent", nl="Verslag verstuurd", en="Report sent", sort_order=30),
)

MEETING_STATUS = CodeList(
    name="meeting_status",
    schema="meetings",
    codes=MeetingStatusCode,
    labels=MeetingStatusLabel,
    enum=MeetingStatus,
    fk_from=("meetings.meetings.status",),
)
