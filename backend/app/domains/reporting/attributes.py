"""The attributes of the `reporting` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="reporting.export_log.exported_at",
        columns=("reporting.export_log.exported_at",),
        label=None,
        name_en="Exported at",
        help="The exported at of the export log.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="reporting.export_log.actor",
        columns=("reporting.export_log.actor",),
        label=None,
        name_en="Actor",
        help="The actor of the export log.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="reporting.export_log.kind",
        columns=("reporting.export_log.kind",),
        label=None,
        name_en="Kind",
        help="The kind of the export log, a code of its code list.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="reporting.export_log.saved_report_id",
        columns=("reporting.export_log.saved_report_id",),
        label=None,
        name_en="Saved report id",
        help="The saved report id of the export log.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="reporting.export_log.subject",
        columns=("reporting.export_log.subject",),
        label=None,
        name_en="Subject",
        help="The subject of the export log.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="reporting.export_log.filters",
        columns=("reporting.export_log.filters",),
        label=None,
        name_en="Filters",
        help="The filters of the export log.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="reporting.export_log.row_count",
        columns=("reporting.export_log.row_count",),
        label=None,
        name_en="Row count",
        help="The row count of the export log.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="reporting.saved_report.name",
        columns=("reporting.saved_reports.name",),
        label=None,
        name_en="Name",
        help="The name of the saved report.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="reporting.saved_report.description",
        columns=("reporting.saved_reports.description",),
        label=None,
        name_en="Description",
        help="The description of the saved report.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="reporting.saved_report.owner_email",
        columns=("reporting.saved_reports.owner_email",),
        label=None,
        name_en="Owner email",
        help="The owner email of the saved report.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="reporting.saved_report.selection",
        columns=("reporting.saved_reports.selection",),
        label=None,
        name_en="Selection",
        help="The selection of the saved report.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="reporting.saved_report.is_shared",
        columns=("reporting.saved_reports.is_shared",),
        label=None,
        name_en="Is shared",
        help="The is shared of the saved report.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
    Attribute(
        key="reporting.saved_report.builtin_key",
        columns=("reporting.saved_reports.builtin_key",),
        label=None,
        name_en="Builtin key",
        help="The builtin key of the saved report.",
        ai_exposure=AiExposure.INTERNAL,  # K9
    ),
    Attribute(
        key="reporting.saved_report.last_run_at",
        columns=("reporting.saved_reports.last_run_at",),
        label=None,
        name_en="Last run at",
        help="The last run at of the saved report.",
        ai_exposure=AiExposure.INTERNAL,  # K8
    ),
)
