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

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base
from app.kernel.tenancy import TenantMixin
from app.soft_delete import SoftDeleteMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


SUBSCRIBER_PENDING = "pending"
SUBSCRIBER_CONFIRMED = "confirmed"
SUBSCRIBER_UNSUBSCRIBED = "unsubscribed"
SUBSCRIBER_STATUSES = (SUBSCRIBER_PENDING, SUBSCRIBER_CONFIRMED, SUBSCRIBER_UNSUBSCRIBED)

SOURCE_PUBLIC_FORM = "public_form"
SOURCE_IMPORT = "import"
SOURCE_ADMIN = "admin"
SUBSCRIBER_SOURCES = (SOURCE_PUBLIC_FORM, SOURCE_IMPORT, SOURCE_ADMIN)

AUDIENCE_MEMBERS = "members"
AUDIENCE_NON_MEMBERS = "non_members"
AUDIENCE_BOTH = "both"
AUDIENCES = (AUDIENCE_MEMBERS, AUDIENCE_NON_MEMBERS, AUDIENCE_BOTH)

LETTER_DRAFT = "draft"
LETTER_SENDING = "sending"
LETTER_SENT = "sent"
LETTER_STATUSES = (LETTER_DRAFT, LETTER_SENDING, LETTER_SENT)

REPLY_TO_ASSOCIATION = "association"
REPLY_TO_SENDER = "sender"
REPLY_TO_MODES = (REPLY_TO_ASSOCIATION, REPLY_TO_SENDER)

DELIVERY_MEMBER = "member"
DELIVERY_SUBSCRIBER = "subscriber"
DELIVERY_KINDS = (DELIVERY_MEMBER, DELIVERY_SUBSCRIBER)

DELIVERY_QUEUED = "queued"
DELIVERY_SENT = "sent"
DELIVERY_FAILED = "failed"
DELIVERY_SKIPPED = "skipped"
DELIVERY_STATUSES = (DELIVERY_QUEUED, DELIVERY_SENT, DELIVERY_FAILED, DELIVERY_SKIPPED)

# What an erased address becomes in the archive.
ERASED_ADDRESS = "verwijderd adres"

MESSAGE_AUTHOR = "author"
MESSAGE_RAAKJE = "raakje"
MESSAGE_ROLES = (MESSAGE_AUTHOR, MESSAGE_RAAKJE)


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
    status = Column(String(20), nullable=False, default=SUBSCRIBER_PENDING)
    source = Column(String(20), nullable=False)
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
    body_html = Column(Text, nullable=False, default="")
    # Empty in a draft on purpose: there is no default audience (CR-05 §3.2).
    audience = Column(String(20), nullable=True)
    status = Column(String(10), nullable=False, default=LETTER_DRAFT)
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
    reply_to_mode = Column(String(20), nullable=True)
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
    kind = Column(String(20), nullable=False)
    subscriber_id = Column(Integer, ForeignKey("newsletter.subscribers.id",
                                               ondelete="SET NULL"),
                           nullable=True)
    status = Column(String(10), nullable=False, default=DELIVERY_QUEUED, index=True)
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
    role = Column(String(10), nullable=False)
    text = Column(Text, nullable=False, default="")
    # Raakje's proposal: the operations, the marks, and whether it was applied.
    proposal = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)

    newsletter = relationship("Newsletter", back_populates="messages")
