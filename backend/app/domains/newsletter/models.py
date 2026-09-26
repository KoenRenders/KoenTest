"""Newsletter: subscribers, letters and deliveries (CR-05, #984).

Schema ``newsletter``. Three shapes decide everything here:

- **Members are derived, never stored.** A member receives the letter because
  their household holds a membership for the current working year, and that
  rule lives in the membership domain (CR-05 §3.3). Only non-members are rows
  here, because only for them is there a consent to record.
- **A subscriber can be erased for real.** No soft delete on
  ``subscribers``: the right to erasure means the row goes. Its deliveries stay
  for the archive's counts, with the address anonymised.
- **The recipient list is fixed when sending starts.** ``deliveries`` is the
  queue and the archive in one table, one row per address. A send that takes
  several days works through those rows; someone who unsubscribes in between is
  skipped when their own row comes up (CR-05 §4).
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.kernel.codes import EnumColumn
from app.kernel.tenancy import TenantMixin
from app.soft_delete import SoftDeleteMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)




# What an erased address becomes in the archive. Geen code en geen lijst:
# het is de tekst die in de plaats komt van een gewist adres (§B4.10 —
# "getallen en teksten die geen code zijn").
ERASED_ADDRESS = "verwijderd adres"


# ── De vocabularia van dit domein (CR-12 fase 3) ─────────────────────────────
#
# Acht lijsten die tot nu toe moduleconstanten waren: een tupel met de geldige
# waarden en, twintig regels verderop in een ander bestand, een woordenboek met
# de Nederlandse woorden. Nu één vorm — codetabel, labeltabel, enum — en dus
# één plek waar een nieuwe waarde bijkomt.


class SubscriberStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    UNSUBSCRIBED = "unsubscribed"


class SubscriberSource(Enum):
    """Waar een inschrijving vandaan komt — bewijs van toestemming."""

    PUBLIC_FORM = "public_form"
    IMPORT = "import"
    ADMIN = "admin"


class Audience(Enum):
    MEMBERS = "members"
    NON_MEMBERS = "non_members"
    BOTH = "both"


class LetterStatus(Enum):
    DRAFT = "draft"
    SENDING = "sending"
    SENT = "sent"


class ReplyToMode(Enum):
    ASSOCIATION = "association"
    SENDER = "sender"


class DeliveryKind(Enum):
    MEMBER = "member"
    SUBSCRIBER = "subscriber"


class DeliveryStatus(Enum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class MessageRole(Enum):
    """Wie het bericht schreef in het opstelgesprek: de auteur of Raakje."""

    AUTHOR = "author"
    RAAKJE = "raakje"


class SubscriberStatusCode(Base):
    """Welke codes bestaan — het doel van de foreign key (CR-12 fase 3)."""

    __tablename__ = "subscriber_status_codes"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class SubscriberStatusLabel(Base):
    """Het woord dat een scherm toont, per taal (CR-12 fase 3)."""

    __tablename__ = "subscriber_status_labels"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), ForeignKey("newsletter.subscriber_status_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class SubscriberSourceCode(Base):
    """Welke codes bestaan — het doel van de foreign key (CR-12 fase 3)."""

    __tablename__ = "subscriber_source_codes"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class SubscriberSourceLabel(Base):
    """Het woord dat een scherm toont, per taal (CR-12 fase 3)."""

    __tablename__ = "subscriber_source_labels"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), ForeignKey("newsletter.subscriber_source_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class AudienceCode(Base):
    """Welke codes bestaan — het doel van de foreign key (CR-12 fase 3)."""

    __tablename__ = "audience_codes"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class AudienceLabel(Base):
    """Het woord dat een scherm toont, per taal (CR-12 fase 3)."""

    __tablename__ = "audience_labels"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), ForeignKey("newsletter.audience_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class LetterStatusCode(Base):
    """Welke codes bestaan — het doel van de foreign key (CR-12 fase 3)."""

    __tablename__ = "letter_status_codes"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class LetterStatusLabel(Base):
    """Het woord dat een scherm toont, per taal (CR-12 fase 3)."""

    __tablename__ = "letter_status_labels"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), ForeignKey("newsletter.letter_status_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class ReplyToModeCode(Base):
    """Welke codes bestaan — het doel van de foreign key (CR-12 fase 3)."""

    __tablename__ = "reply_to_mode_codes"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class ReplyToModeLabel(Base):
    """Het woord dat een scherm toont, per taal (CR-12 fase 3)."""

    __tablename__ = "reply_to_mode_labels"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), ForeignKey("newsletter.reply_to_mode_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class DeliveryKindCode(Base):
    """Welke codes bestaan — het doel van de foreign key (CR-12 fase 3)."""

    __tablename__ = "delivery_kind_codes"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class DeliveryKindLabel(Base):
    """Het woord dat een scherm toont, per taal (CR-12 fase 3)."""

    __tablename__ = "delivery_kind_labels"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), ForeignKey("newsletter.delivery_kind_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class DeliveryStatusCode(Base):
    """Welke codes bestaan — het doel van de foreign key (CR-12 fase 3)."""

    __tablename__ = "delivery_status_codes"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class DeliveryStatusLabel(Base):
    """Het woord dat een scherm toont, per taal (CR-12 fase 3)."""

    __tablename__ = "delivery_status_labels"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), ForeignKey("newsletter.delivery_status_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class MessageRoleCode(Base):
    """Welke codes bestaan — het doel van de foreign key (CR-12 fase 3)."""

    __tablename__ = "message_role_codes"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class MessageRoleLabel(Base):
    """Het woord dat een scherm toont, per taal (CR-12 fase 3)."""

    __tablename__ = "message_role_labels"
    __table_args__ = {"schema": "newsletter"}

    code = Column(String(20), ForeignKey("newsletter.message_role_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class Subscriber(TenantMixin, Base):
    """A non-member who receives the newsletter (CR-05 §3.5, §3.6).

    The e-mail address plus an optional first name, and the record of what was
    agreed: through which source, when, and whether it was confirmed. Nothing
    else — family details belong to the membership flow.
    """

    __tablename__ = "subscribers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_newsletter_subscriber_email"),
        {"schema": "newsletter"},
    )

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=True)
    status: Mapped[SubscriberStatus] = mapped_column(
        EnumColumn(SubscriberStatus, length=20),
        ForeignKey("newsletter.subscriber_status_codes.code"), nullable=False,
        default=SubscriberStatus.PENDING)
    source: Mapped[SubscriberSource] = mapped_column(
        EnumColumn(SubscriberSource, length=20),
        ForeignKey("newsletter.subscriber_source_codes.code"), nullable=False)
    consented_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    unsubscribed_at = Column(DateTime(timezone=True), nullable=True)
    imported_at = Column(DateTime(timezone=True), nullable=True)
    # When the last confirmation mail left: the brake against someone typing a
    # stranger's address over and over (one mail a day per address).
    confirm_sent_at = Column(DateTime(timezone=True), nullable=True)
    confirm_token = Column(String(64), nullable=True, unique=True)
    unsubscribe_token = Column(String(64), nullable=False, unique=True)
    # Soft reference: set when the subscriber turns out to be a known person.
    # Not a foreign key — it must survive the person being deleted, and it
    # crosses into the mdm schema.
    person_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class Newsletter(TenantMixin, SoftDeleteMixin, Base):
    """One letter: its text, its audience, and how far sending has come."""

    __tablename__ = "newsletters"
    __table_args__ = {"schema": "newsletter"}

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String(500), nullable=False, default="")
    # #984: the line a mail client shows beside the subject. Empty is fine — the
    # letter then derives it from its own first sentence, so the inbox never
    # reads "Beste,".
    preview_text = Column(String(200), nullable=False, default="")
    body_html = Column(Text, nullable=False, default="")
    # Empty in a draft on purpose: there is no default audience (CR-05 §3.2).
    audience: Mapped[Optional[Audience]] = mapped_column(
        EnumColumn(Audience, length=20),
        ForeignKey("newsletter.audience_codes.code"), nullable=True)
    status: Mapped[LetterStatus] = mapped_column(
        EnumColumn(LetterStatus, length=20),
        ForeignKey("newsletter.letter_status_codes.code"), nullable=False,
        default=LetterStatus.DRAFT)
    copied_from_id = Column(Integer, ForeignKey("newsletter.newsletters.id",
                                                ondelete="SET NULL"),
                            nullable=True)
    created_by = Column(String(255), nullable=True)
    # What Raakje works from (CR-05 §3.15): the chosen activities — past and
    # coming, told apart by their date — and the ticked meeting reports. Soft
    # references into two other schemas, so JSON lists of ids and not join
    # tables with foreign keys.
    draft_activity_ids = Column(JSON, nullable=False, default=list)
    draft_meeting_ids = Column(JSON, nullable=False, default=list)
    # Frozen at send time: who sent, where replies go.
    reply_to_mode: Mapped[Optional[ReplyToMode]] = mapped_column(
        EnumColumn(ReplyToMode, length=20),
        ForeignKey("newsletter.reply_to_mode_codes.code"), nullable=True)
    reply_to_address = Column(String(255), nullable=True)
    # The public origin the links in this letter point to, frozen when sending
    # starts. The send runs in a background job, where no request tells which
    # host the association is reached on; a unit without its own domain would
    # otherwise get links to the bare platform address.
    link_base = Column(String(255), nullable=True)
    sent_by = Column(String(255), nullable=True)
    send_started_at = Column(DateTime(timezone=True), nullable=True)
    send_finished_at = Column(DateTime(timezone=True), nullable=True)
    # The next moment the queue may continue, when it paused for the day.
    paused_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)

    deliveries = relationship("Delivery", back_populates="newsletter",
                              cascade="all, delete-orphan")
    messages = relationship("DraftingMessage", back_populates="newsletter",
                            cascade="all, delete-orphan",
                            order_by="DraftingMessage.id")


class Delivery(TenantMixin, Base):
    """One address of one letter: the queue row and the archive row."""

    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("newsletter_id", "email", name="uq_newsletter_delivery_email"),
        {"schema": "newsletter"},
    )

    id = Column(Integer, primary_key=True, index=True)
    newsletter_id = Column(Integer, ForeignKey("newsletter.newsletters.id",
                                               ondelete="CASCADE"),
                           nullable=False, index=True)
    email = Column(String(255), nullable=False)
    # Decides whether an unsubscribe link goes along (CR-05 §3.4).
    kind: Mapped[DeliveryKind] = mapped_column(
        EnumColumn(DeliveryKind, length=20),
        ForeignKey("newsletter.delivery_kind_codes.code"), nullable=False)
    subscriber_id = Column(Integer, ForeignKey("newsletter.subscribers.id",
                                               ondelete="SET NULL"),
                           nullable=True)
    status: Mapped[DeliveryStatus] = mapped_column(
        EnumColumn(DeliveryStatus, length=20),
        ForeignKey("newsletter.delivery_status_codes.code"), nullable=False,
        default=DeliveryStatus.QUEUED, index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True, index=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)

    newsletter = relationship("Newsletter", back_populates="deliveries")


class DraftingMessage(TenantMixin, Base):
    """One turn in the conversation with Raakje about one draft (CR-05 §3.15).

    Kept with the draft so the author can continue the next day, and removed
    when the letter is sent: the sent letter is the record, and the AI payload
    log already holds what left the system.
    """

    __tablename__ = "drafting_messages"
    __table_args__ = {"schema": "newsletter"}

    id = Column(Integer, primary_key=True, index=True)
    newsletter_id = Column(Integer, ForeignKey("newsletter.newsletters.id",
                                               ondelete="CASCADE"),
                           nullable=False, index=True)
    role: Mapped[MessageRole] = mapped_column(
        EnumColumn(MessageRole, length=20),
        ForeignKey("newsletter.message_role_codes.code"), nullable=False)
    text = Column(Text, nullable=False, default="")
    # Raakje's proposal: the operations, the marks, and whether it was applied.
    proposal = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)

    newsletter = relationship("Newsletter", back_populates="messages")
