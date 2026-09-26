from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.kernel.codes import EnumColumn
from app.kernel.tenancy import TenantMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class EmailType(Enum):
    """Which mail flow sent a message (CR-12 phase 4).

    Was the tuple `EMAIL_TYPES`. The meeting mails (#258) share one type for
    agenda and report — the log answers "who got what when", and the subject
    already says which of the two it was. The newsletter (#984) has two: the
    letter itself and the double-opt-in confirmation, because the log must be
    able to show that someone got the confirmation long before any letter left.
    `idea_ack` and `idea_board` have no caller any more, but older rows carry
    them, so they stay codes.
    """

    MEMBERSHIP_CONFIRMATION = "membership_confirmation"
    ACTIVITY_CONFIRMATION = "activity_confirmation"
    IDEA_ACK = "idea_ack"
    IDEA_BOARD = "idea_board"
    MAGIC_LINK = "magic_link"
    MEMBER_CONTACT_NOTICE = "member_contact_notice"
    FORM_CONFIRMATION = "form_confirmation"
    MEETING = "meeting"
    NEWSLETTER = "newsletter"
    NEWSLETTER_CONFIRMATION = "newsletter_confirmation"
    OTHER = "other"


class MailStatus(Enum):
    """What happened to one outgoing mail (CR-12 phase 4).

    `sent` = SMTP accepted it; `failed` = an exception while sending;
    `skipped` = not sent because GMAIL_USER/-PASSWORD is missing; `logged` =
    written to the log instead of sent (the development mode of migration 087).
    The last one was in the database check but in no Python tuple, so the
    status filter never offered it.
    """

    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
    LOGGED = "logged"


#: Backward names for whoever expected the tuples. They derive from the enums,
#: so there is one source.
EMAIL_TYPES = tuple(m.value for m in EmailType)
EMAIL_STATUSES = tuple(m.value for m in MailStatus)


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
    email_type: Mapped[EmailType] = mapped_column(
        EnumColumn(EmailType, length=40),
        ForeignKey("mail.email_type_codes.code"), nullable=False,
        default=EmailType.OTHER)
    # Volledige inhoud bewaard (afgesproken met Koen) — persoonsgegevens, dus
    # admin-only + bewaartermijn via EMAIL_LOG_RETENTION_DAYS.
    body = Column(Text, nullable=True)
    status: Mapped[MailStatus] = mapped_column(
        EnumColumn(MailStatus, length=20),
        ForeignKey("mail.mail_status_codes.code"), nullable=False,
        default=MailStatus.SENT)
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


class EmailTypeCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 4)."""

    __tablename__ = "email_type_codes"
    __table_args__ = {"schema": "mail"}

    code = Column(String(40), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class EmailTypeLabel(Base):
    """The word a screen shows, per language (CR-12 phase 4)."""

    __tablename__ = "email_type_labels"
    __table_args__ = {"schema": "mail"}

    code = Column(String(40), ForeignKey("mail.email_type_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class MailStatusCode(Base):
    """Which codes exist — the target of the foreign key (CR-12 phase 4)."""

    __tablename__ = "mail_status_codes"
    __table_args__ = {"schema": "mail"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class MailStatusLabel(Base):
    """The word a screen shows, per language (CR-12 phase 4)."""

    __tablename__ = "mail_status_labels"
    __table_args__ = {"schema": "mail"}

    code = Column(String(20), ForeignKey("mail.mail_status_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)
