"""Publieke facade van het mail-component (fase 1, #399).

Andere componenten importeren mail-functionaliteit uitsluitend via deze module
(grens-test: cross-domain enkel via ``.api``). De implementatie leeft in
``service.py`` en blijft intern; het EmailLog-model in ``models.py``.
"""
from app.domains.mail.service import (  # noqa: F401
    purge_old_email_logs,
    send_activity_registration_confirmation,
    send_form_confirmation,
    send_magic_link,
    send_member_contact_board_notice,
    send_registration_confirmation,
)

__all__ = [
    "purge_old_email_logs",
    "send_activity_registration_confirmation",
    "send_form_confirmation",
    "send_magic_link",
    "send_member_contact_board_notice",
    "send_registration_confirmation",
]
