"""The code lists the meetings domain owns (CR-12).

`meeting_status` is the **pilot** of CR-12: three codes, one screen, one badge,
migrated end to end in phase 0 before the money domain is touched. It is small
enough that a mistake is visible and real enough to prove the four things the
rest of the change rests on — that `EnumColumn` writes the code and not the
member name, that a `Mapped[]` column can sit next to legacy `Column()` ones,
that the Jinja filter renders the same Dutch words the screen showed before,
and that the gates fail on a violation rather than staying green.

Phase 3 added the other three: `section_kind`, `attendance` and
`file_purpose`. All four were module constants; the tone mapping of the status
moved to `register_tones` with the pilot.
"""
from app.domains.meetings.models import (
    Attendance,
    AttendanceCode,
    AttendanceLabel,
    FilePurpose,
    FilePurposeCode,
    FilePurposeLabel,
    MeetingStatus,
    MeetingStatusCode,
    MeetingStatusLabel,
    SectionKind,
    SectionKindCode,
    SectionKindLabel,
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


SECTION_KIND_CODES = (
    CodeSeed(code="EVALUATION", nl="Evaluatie voorbije activiteiten",
             en="Evaluation of past activities", sort_order=10),
    CodeSeed(code="UPCOMING", nl="Volgende activiteiten",
             en="Upcoming activities", sort_order=20),
    CodeSeed(code="MEMBERS", nl="Leden", en="Members", sort_order=30),
    CodeSeed(code="IDEAS", nl="Programma-ideeën", en="Programme ideas",
             sort_order=40),
    CodeSeed(code="MISC", nl="Varia", en="Miscellaneous", sort_order=50),
    CodeSeed(code="CUSTOM", nl="Eigen rubriek", en="Custom section",
             sort_order=60),
)

SECTION_KIND = CodeList(
    name="section_kind",
    schema="meetings",
    codes=SectionKindCode,
    labels=SectionKindLabel,
    enum=SectionKind,
    fk_from=("meetings.meeting_sections.kind",),
)

ATTENDANCE_CODES = (
    CodeSeed(code="present", nl="Aanwezig", en="Present", sort_order=10),
    CodeSeed(code="excused", nl="Verontschuldigd", en="Excused", sort_order=20),
)

ATTENDANCE = CodeList(
    name="attendance",
    schema="meetings",
    codes=AttendanceCode,
    labels=AttendanceLabel,
    enum=Attendance,
    fk_from=("meetings.meeting_attendances.status",),
)

FILE_PURPOSE_CODES = (
    CodeSeed(code="attachment", nl="Bijlage", en="Attachment", sort_order=10),
    CodeSeed(code="sent_pdf", nl="Verstuurd verslag (pdf)",
             en="Sent report (PDF)", sort_order=20),
)

FILE_PURPOSE = CodeList(
    name="file_purpose",
    schema="meetings",
    codes=FilePurposeCode,
    labels=FilePurposeLabel,
    enum=FilePurpose,
    fk_from=("meetings.meeting_files.purpose",),
)
