from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, Text

from app.database import Base
from app.kernel.tenancy import TenantMixin


# Toegestane types — houd in sync met de CHECK in migratie 062 en met de
# `email_type`-waarden die de mailfuncties in app/domains/mail/service.py meegeven.
EMAIL_TYPES = (
    "membership_confirmation",
    "activity_confirmation",
    "idea_ack",
    "idea_board",
    "magic_link",
    "member_contact_notice",
    "form_confirmation",
    "other",
)

# Statussen: 'sent' = SMTP aanvaardde de mail; 'failed' = een uitzondering bij het
# versturen; 'skipped' = niet verstuurd omdat GMAIL_USER/-PASSWORD ontbreekt.
EMAIL_STATUSES = ("sent", "failed", "skipped")


class EmailLog(TenantMixin, Base):
    """Centrale log van élke uitgaande e-mail (#328).

    Geschreven vanuit het ene choke point ``_send`` in app/domains/mail/service.py, zodat
    alle mailstromen (lidmaatschap, activiteit, idee, login, formulier) automatisch
    gelogd worden zonder de routers aan te raken. Bewust **geen** FK naar Person/
    Member — losgekoppeld; ``recipient`` is gewoon het adres."""

    __tablename__ = "email_log"
    __table_args__ = {"schema": "mail"}

    id = Column(Integer, primary_key=True, index=True)
    recipient = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=False)
    email_type = Column(String(40), nullable=False, default="other")
    # Volledige inhoud bewaard (afgesproken met Koen) — persoonsgegevens, dus
    # admin-only + bewaartermijn via EMAIL_LOG_RETENTION_DAYS.
    body = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="sent")
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
