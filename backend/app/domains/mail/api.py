"""Publieke facade van het mail-component (fase 1, #399).

Andere componenten importeren mail-functionaliteit uitsluitend via deze module
(grens-test: cross-domain enkel via ``.api``). De implementatie leeft in
``service.py`` en blijft intern; het EmailLog-model in ``models.py``.
"""

from app.domains.mail.codes import EMAIL_TYPE, MAIL_STATUS  # noqa: F401
from app.domains.mail.models import (  # noqa: F401
    EMAIL_STATUSES,
    EMAIL_TYPES,
    EmailLog,  # noqa: F401
    EmailType,
    MailStatus,
)
from app.domains.mail.service import (  # noqa: F401  # noqa: F401
    EMAIL_LOG_SORT_KEYS,
    SendingQuotaReached,
    delete_email_log,
    email_log_url,
    list_email_log,
    purge_old_email_logs,
    send_campaign_mail,
    send_form_confirmation,
    send_magic_link,
    send_member_contact_board_notice,
    send_newsletter_confirmation,
    send_with_attachments,
)

__all__ = [
    "email_log_url",
    "EMAIL_LOG_SORT_KEYS",
    "EMAIL_STATUSES",
    "EMAIL_TYPES",
    "delete_email_log",
    "EMAIL_TYPE",
    "MAIL_STATUS",
    "EmailType",
    "MailStatus",
    "list_email_log",
    "EmailLog",
    "purge_old_email_logs",
    "send_form_confirmation",
    "send_magic_link",
    "send_member_contact_board_notice",
    "send_with_attachments",
    "send_campaign_mail",
    "send_newsletter_confirmation",
    "SendingQuotaReached",
]
