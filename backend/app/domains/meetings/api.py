"""Public facade of the meetings domain (CR-09, #258).

Everything another module may use lives here. Two audiences, deliberately:

- **The screens of this domain** (`admin_ui.py`) reach their own service only
  through this facade, like every UI module does.
- **The newsletter chain** (CR-05) reads meeting reports through it — the
  compose screen lets the composer *select* which report items come along, and
  that selection is the PII gate. Nothing else of a report ever leaves here.

The ORM classes are exported for other domains' services, not for screens; the
layer gate holds that line.
"""
from app.domains.meetings.models import (  # noqa: F401
    ATTENDANCE_EXCUSED,
    ATTENDANCE_PRESENT,
    FILE_ATTACHMENT,
    FILE_SENT_PDF,
    SECTION_CUSTOM,
    SECTION_EVALUATION,
    SECTION_IDEAS,
    SECTION_MEMBERS,
    SECTION_MISC,
    SECTION_UPCOMING,
    STATUS_AGENDA,
    STATUS_REPORT,
    STATUS_SENT,
    Meeting,
    MeetingAttendance,
    MeetingExtraRecipient,
    MeetingFile,
    MeetingItem,
    MeetingSection,
)
from app.domains.meetings.service import (  # noqa: F401
    DocumentItem,
    DocumentSection,
    MeetingError,
    MemberStanding,
    Recipients,
    add_extra_recipient,
    add_file,
    add_item,
    add_section,
    addable_activities,
    attendance_of,
    create_meeting,
    delete_file,
    delete_item,
    document_of,
    extra_recipients_of,
    file_is_sent,
    files_of,
    generate_agenda,
    get_file,
    get_meeting,
    items_of,
    list_meetings,
    member_standing,
    previous_meeting,
    recipients_for,
    remove_extra_recipient,
    reopen,
    section_label,
    sections_of,
    send_meeting_mail,
    set_attendance,
    set_file_mailing,
    set_noted_steward,
    update_item,
    update_meeting,
)
from app.domains.meetings.pdf import (  # noqa: F401
    clock,
    filename_for,
    long_date,
    render,
    short_date,
)

__all__ = [
    "ATTENDANCE_EXCUSED", "ATTENDANCE_PRESENT", "FILE_ATTACHMENT",
    "FILE_SENT_PDF", "SECTION_CUSTOM", "SECTION_EVALUATION", "SECTION_IDEAS",
    "SECTION_MEMBERS", "SECTION_MISC", "SECTION_UPCOMING", "STATUS_AGENDA",
    "STATUS_REPORT", "STATUS_SENT", "Meeting", "MeetingAttendance",
    "MeetingExtraRecipient", "MeetingFile", "MeetingItem", "MeetingSection",
    "DocumentItem", "DocumentSection", "MeetingError", "MemberStanding",
    "Recipients", "add_extra_recipient", "add_file", "add_item", "add_section",
    "addable_activities", "attendance_of", "create_meeting", "delete_file",
    "delete_item", "document_of", "extra_recipients_of", "file_is_sent", "files_of", "generate_agenda", "get_file",
    "get_meeting", "items_of", "list_meetings", "member_standing",
    "previous_meeting", "recipients_for", "remove_extra_recipient", "reopen",
    "section_label", "sections_of", "send_meeting_mail", "set_attendance",
    "set_file_mailing", "set_noted_steward",
    "update_item", "update_meeting", "clock", "filename_for", "long_date", "render", "short_date",
]
