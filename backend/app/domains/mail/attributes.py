"""The attributes of the `mail` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="mail.email_log.recipient",
        columns=("mail.email_log.recipient",),
        label=None,
        name_en="Recipient",
        help="The recipient of the email log.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
    Attribute(
        key="mail.email_log.subject",
        columns=("mail.email_log.subject",),
        label=None,
        name_en="Subject",
        help="The subject of the email log.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="mail.email_log.email_type",
        columns=("mail.email_log.email_type",),
        label=None,
        name_en="Email type",
        help="The email type of the email log.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="mail.email_log.body",
        columns=("mail.email_log.body",),
        label=None,
        name_en="Body",
        help="The body of the email log.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="mail.email_log.status",
        columns=("mail.email_log.status",),
        label=None,
        name_en="Status",
        help="The status of the email log.",
        ai_exposure=AiExposure.NONE,  # K3
    ),
    Attribute(
        key="mail.email_log.error_message",
        columns=("mail.email_log.error_message",),
        label=None,
        name_en="Error message",
        help="The error message of the email log.",
        ai_exposure=AiExposure.NONE,  # K1
    ),
)
