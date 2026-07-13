"""Mail-contract (fase 1, #399): e-mail aanvragen via een event.

Componenten die geen directe afhankelijkheid op het mail-component willen,
publiceren ``MailRequested`` (synchroon, in-transactie — event-ladder trede 1);
het mail-component is de abonnee en verstuurt + logt. De directe facade
(``app.domains.mail.api``) blijft bestaan voor de rijkere, opgemaakte mails.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.kernel.events import KernelEvent


@dataclass(frozen=True)
class MailRequested(KernelEvent):
    to_email: str
    subject: str
    body_html: str
    email_type: str = "other"
    cc: Optional[str] = None
