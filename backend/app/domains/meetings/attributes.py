"""The attributes of the `meetings` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="meetings.meeting.meeting_date",
        columns=("meetings.meetings.meeting_date",),
        label=None,
        name_en="Meeting date",
        help="The meeting date of the meeting.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="meetings.meeting.start_time",
        columns=("meetings.meetings.start_time",),
        label=None,
        name_en="Start time",
        help="The start time of the meeting.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="meetings.meeting.location",
        columns=("meetings.meetings.location",),
        label=None,
        name_en="Location",
        help="The location of the meeting.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="meetings.meeting.status",
        columns=("meetings.meetings.status",),
        label=None,
        name_en="Status",
        help="The status of the meeting.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="meetings.meeting.agenda_sent_at",
        columns=("meetings.meetings.agenda_sent_at",),
        label=None,
        name_en="Agenda sent at",
        help="The agenda sent at of the meeting.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="meetings.meeting.report_sent_at",
        columns=("meetings.meetings.report_sent_at",),
        label=None,
        name_en="Report sent at",
        help="The report sent at of the meeting.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="meetings.meeting_attendance.person_id",
        columns=("meetings.meeting_attendances.person_id",),
        label=None,
        name_en="Person id",
        help="The person id of the meeting attendance.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="meetings.meeting_attendance.status",
        columns=("meetings.meeting_attendances.status",),
        label=None,
        name_en="Status",
        help="The status of the meeting attendance, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="meetings.meeting_extra_recipient.name",
        columns=("meetings.meeting_extra_recipients.name",),
        label=None,
        name_en="Name",
        help="The name of the meeting extra recipient.",
        ai_exposure=AiExposure.TOKENISED,  # K2
    ),
    Attribute(
        key="meetings.meeting_extra_recipient.email",
        columns=("meetings.meeting_extra_recipients.email",),
        label=None,
        name_en="Email",
        help="The email of the meeting extra recipient.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="meetings.meeting_file.purpose",
        columns=("meetings.meeting_files.purpose",),
        label=None,
        name_en="Purpose",
        help="The purpose of the meeting file, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="meetings.meeting_file.filename",
        columns=("meetings.meeting_files.filename",),
        label=None,
        name_en="Filename",
        help="The filename of the meeting file.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="meetings.meeting_file.content_type",
        columns=("meetings.meeting_files.content_type",),
        label=None,
        name_en="Content type",
        help="The content type of the meeting file.",
        ai_exposure=AiExposure.INTERNAL,  # K7
    ),
    Attribute(
        key="meetings.meeting_file.byte_size",
        columns=("meetings.meeting_files.byte_size",),
        label=None,
        name_en="Byte size",
        help="The byte size of the meeting file.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="meetings.meeting_file.data",
        columns=("meetings.meeting_files.data",),
        label=None,
        name_en="Data",
        help="The data of the meeting file.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="meetings.meeting_file.on_agenda_mail",
        columns=("meetings.meeting_files.on_agenda_mail",),
        label=None,
        name_en="On agenda mail",
        help="The on agenda mail of the meeting file.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="meetings.meeting_file.on_report_mail",
        columns=("meetings.meeting_files.on_report_mail",),
        label=None,
        name_en="On report mail",
        help="The on report mail of the meeting file.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="meetings.meeting_file.sent_with_agenda_at",
        columns=("meetings.meeting_files.sent_with_agenda_at",),
        label=None,
        name_en="Sent with agenda at",
        help="The sent with agenda at of the meeting file.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="meetings.meeting_file.sent_with_report_at",
        columns=("meetings.meeting_files.sent_with_report_at",),
        label=None,
        name_en="Sent with report at",
        help="The sent with report at of the meeting file.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="meetings.meeting_item.position",
        columns=("meetings.meeting_items.position",),
        label=None,
        name_en="Position",
        help="The position of the meeting item.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="meetings.meeting_item.title",
        columns=("meetings.meeting_items.title",),
        label=None,
        name_en="Title",
        help="The title of the meeting item.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="meetings.meeting_item.notes_document",
        columns=("meetings.meeting_items.notes_document",),
        label=None,
        name_en="Notes",
        help="The notes of the meeting item, as a document of the page editor.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="meetings.meeting_item.activity_id",
        columns=("meetings.meeting_items.activity_id",),
        label=None,
        name_en="Activity id",
        help="The activity id of the meeting item.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="meetings.meeting_item.activity_date_id",
        columns=("meetings.meeting_items.activity_date_id",),
        label=None,
        name_en="Activity date id",
        help="The activity date id of the meeting item.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="meetings.meeting_item.member_id",
        columns=("meetings.meeting_items.member_id",),
        label=None,
        name_en="Member id",
        help="The member id of the meeting item.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="meetings.meeting_item.noted_steward_person_id",
        columns=("meetings.meeting_items.noted_steward_person_id",),
        label=None,
        name_en="Noted steward person id",
        help="The noted steward person id of the meeting item.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="meetings.meeting_item.sort_key",
        columns=("meetings.meeting_items.sort_key",),
        label=None,
        name_en="Sort key",
        help="The sort key of the meeting item.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="meetings.meeting_section.kind",
        columns=("meetings.meeting_sections.kind",),
        label=None,
        name_en="Kind",
        help="The kind of the meeting section, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="meetings.meeting_section.title",
        columns=("meetings.meeting_sections.title",),
        label=None,
        name_en="Title",
        help="The title of the meeting section.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="meetings.meeting_section.position",
        columns=("meetings.meeting_sections.position",),
        label=None,
        name_en="Position",
        help="The position of the meeting section.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
)
