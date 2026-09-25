"""Meetings: agenda and report as one document (CR-09, #258).

Schema ``meetings``. The board runs the association through a monthly meeting:
an agenda goes out the evening before, is filled in during the meeting, and
returns as the report the evening after. This domain holds that document.

Three shapes decide everything here:

- **The report is data, not a blob.** Sections and items are rows, so the next
  agenda can be *generated* (upcoming activities + carried-over ideas) instead of
  copied, and the newsletter side can select items instead of parsing prose.
- **Items reference, they never copy.** An activity item carries
  ``activity_id`` and renders name, date and location fresh through it; that is
  also why the chronological order inside a section derives from the activity
  date. What was *sent* is frozen in the archived PDF, not by freezing the rows.
- **Files live here, not in media** (CR-09 §4). The media domain serves
  publicly by design; board documents stored there would depend forever on a
  confidentiality flag being set at every upload — that fails open. A meetings
  table with an admin-only download route fails closed.
"""
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.kernel.codes import EnumColumn
from app.kernel.tenancy import TenantMixin
from app.soft_delete import SoftDeleteMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class MeetingStatus(Enum):
    """Status of the one document. The pilot list of CR-12 (phase 0).

    `agenda` → `report` happens implicitly (taking attendance or typing a note
    is entering the report phase, CR-09 §3.23); `sent` is the only hard moment,
    and "Heropen verslag" walks it back.

    **Plain `Enum`, not `str, Enum`** — deliberately, and this list is where the
    codebase proves it first. With a `str` subclass, `meeting.status == "sent"`
    stays a valid comparison that happens to be true, so the old module
    constants could survive next to the enum and nobody would notice the two
    drifting apart. Plain, that comparison is silently *false*, which is why the
    loose-string gate is an AST walk and not a type check (§B4.8).

    Member names are English; the values are the codes as stored, unchanged
    (§B4.3) — here the two happen to coincide.
    """

    AGENDA = "agenda"
    REPORT = "report"
    SENT = "sent"


class MeetingStatusCode(Base):
    """Which meeting statuses exist — the target of the foreign key."""

    __tablename__ = "meeting_status_codes"
    __table_args__ = {"schema": "meetings"}

    code = Column(String(10), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class MeetingStatusLabel(Base):
    """The word a screen shows for a meeting status, per language."""

    __tablename__ = "meeting_status_labels"
    __table_args__ = {"schema": "meetings"}

    code = Column(String(10), ForeignKey("meetings.meeting_status_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)

# The five standard sections, in their fixed order, plus the custom kind.
# MISC is always last (CR-09 §3.17) — a custom section inserts before it.
SECTION_EVALUATION = "EVALUATION"
SECTION_UPCOMING = "UPCOMING"
SECTION_MEMBERS = "MEMBERS"
SECTION_IDEAS = "IDEAS"
SECTION_MISC = "MISC"
SECTION_CUSTOM = "CUSTOM"
STANDARD_SECTIONS = (SECTION_EVALUATION, SECTION_UPCOMING, SECTION_MEMBERS,
                     SECTION_IDEAS, SECTION_MISC)
SECTION_KINDS = STANDARD_SECTIONS + (SECTION_CUSTOM,)

# Which sections carry their items over to the next agenda (CR-09 §3.6): only
# the ideas and the miscellaneous ones. Everything else is regenerated from the
# activities and the member data, so carrying it over would duplicate it.
CARRY_OVER_SECTIONS = (SECTION_IDEAS, SECTION_MISC)

ATTENDANCE_PRESENT = "present"
ATTENDANCE_EXCUSED = "excused"
ATTENDANCE_STATUSES = (ATTENDANCE_PRESENT, ATTENDANCE_EXCUSED)

FILE_ATTACHMENT = "attachment"
FILE_SENT_PDF = "sent_pdf"
FILE_PURPOSES = (FILE_ATTACHMENT, FILE_SENT_PDF)


class Meeting(TenantMixin, SoftDeleteMixin, Base):
    """One meeting: its agenda, its report, and what was sent when."""

    __tablename__ = "meetings"
    __table_args__ = {"schema": "meetings"}

    id = Column(Integer, primary_key=True, index=True)
    meeting_date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=True)
    location = Column(String(255), nullable=True)
    # The one `Mapped[]` column in this model, on purpose: SQLAlchemy 2.0
    # declarative style next to 688 legacy `Column()` attributes, which is
    # supported and is what lets mypy see this attribute's type at all
    # (§B4.8). `EnumColumn` stores `member.value`, never the member name.
    status: Mapped[MeetingStatus] = mapped_column(
        EnumColumn(MeetingStatus, length=10), nullable=False,
        default=MeetingStatus.AGENDA)
    # Sending stamps these; they are also the guard the file rules read, so
    # "this meeting has been sent" stays one fact in one place (CR-09 §4).
    agenda_sent_at = Column(DateTime(timezone=True), nullable=True)
    report_sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)

    sections = relationship("MeetingSection", back_populates="meeting",
                            cascade="all, delete-orphan",
                            order_by="MeetingSection.position")
    items = relationship("MeetingItem", back_populates="meeting",
                         cascade="all, delete-orphan")
    attendances = relationship("MeetingAttendance", back_populates="meeting",
                               cascade="all, delete-orphan")
    files = relationship("MeetingFile", back_populates="meeting",
                         cascade="all, delete-orphan")
    extra_recipients = relationship("MeetingExtraRecipient", back_populates="meeting",
                                    cascade="all, delete-orphan")


class MeetingSection(TenantMixin, SoftDeleteMixin, Base):
    """A heading in the document: one of the five standard kinds, or a custom one.

    Sections are rows and not an enum on the item, because the secretary can add
    a named block ("Jaarplanning 2027") to agenda a big topic — while preparing
    the agenda *and* during the meeting (CR-09 §3.17).
    """

    __tablename__ = "meeting_sections"
    __table_args__ = {"schema": "meetings"}

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.meetings.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    kind = Column(String(20), nullable=False)
    # Only a custom section carries its own title; a standard one is labelled
    # from its kind, so renaming that label later is one place, not N rows.
    title = Column(String(255), nullable=True)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)

    meeting = relationship("Meeting", back_populates="sections")
    items = relationship("MeetingItem", back_populates="section",
                         cascade="all, delete-orphan",
                         order_by="MeetingItem.position")


class MeetingItem(TenantMixin, SoftDeleteMixin, Base):
    """One bullet in a section — linked to a source, or free.

    A linked item renders its subject fresh through the reference (an activity's
    date can move after the agenda went out); a free item is only ``title`` plus
    ``notes``. ``sort_key`` holds the date the item sorts on, copied at generation
    so the list can be ordered in SQL, with the item's own reference remaining the
    source of truth for what is *shown*.
    """

    __tablename__ = "meeting_items"
    __table_args__ = {"schema": "meetings"}

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.meetings.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    section_id = Column(Integer, ForeignKey("meetings.meeting_sections.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    position = Column(Integer, nullable=False, default=0)
    title = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)

    # The three references, as **soft-refs**: a foreign key across schemas would
    # tie two domains' deploys together, which `test_schema_boundaries` forbids.
    # In code this domain reaches the subjects through `activities.api` /
    # `mdm.api`; a reference that no longer resolves renders as a free item
    # rather than breaking the screen.
    activity_id = Column(Integer, nullable=True, index=True)
    member_id = Column(Integer, nullable=True, index=True)
    # The steward chosen next to a new member is *minutes*: it is stored here and
    # never written into the member data. The authoritative assignment flows
    # through the national administration and returns via the MDM import (§3.9).
    noted_steward_person_id = Column(Integer, nullable=True)

    carried_over_from = Column(Integer, ForeignKey("meetings.meeting_items.id"),
                               nullable=True)
    # The date this item sorts on; NULL for a free item, which lands at the end.
    sort_key = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)

    meeting = relationship("Meeting", back_populates="items")
    section = relationship("MeetingSection", back_populates="items",
                           foreign_keys=[section_id])


class MeetingAttendance(TenantMixin, SoftDeleteMixin, Base):
    """Present or excused, ticked off the circle (CR-09 §3.7)."""

    __tablename__ = "meeting_attendances"
    __table_args__ = {"schema": "meetings"}

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.meetings.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    # Precies één van de twee is gezet: iemand uit de kring, of een gast die voor
    # deze ene vergadering uitgenodigd is. Een gast heeft bewust geen `Person`
    # (CR-09 §3.15), en toch hoort hij in de aanwezigheidslijst — wie er was, was
    # er (Koen, 15 september 2026).
    person_id = Column(Integer, nullable=True, index=True)  # soft-ref, see MeetingItem
    guest_id = Column(Integer,
                      ForeignKey("meetings.meeting_extra_recipients.id",
                                 ondelete="CASCADE"),
                      nullable=True, index=True)
    status = Column(String(10), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)

    meeting = relationship("Meeting", back_populates="attendances")


class MeetingFile(TenantMixin, SoftDeleteMixin, Base):
    """An uploaded attachment, or an archived PDF of what was sent.

    The bytes live here (BYTEA, so they ride along in the database dumps) and are
    downloaded through a meetings route behind the admin session. See the module
    docstring for why this is not a media asset.
    """

    __tablename__ = "meeting_files"
    __table_args__ = {"schema": "meetings"}

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.meetings.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    purpose = Column(String(20), nullable=False, default=FILE_ATTACHMENT)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    byte_size = Column(Integer, nullable=True)
    data = Column(LargeBinary, nullable=False)
    on_agenda_mail = Column(Boolean, nullable=False, default=True)
    on_report_mail = Column(Boolean, nullable=False, default=True)
    # De twee vlaggen hierboven zijn een VOORNEMEN; deze twee stempels zijn het
    # FEIT. Ze worden gezet op het moment dat het bestand echt in een mail zit.
    sent_with_agenda_at = Column(DateTime(timezone=True), nullable=True)
    sent_with_report_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)

    meeting = relationship("Meeting", back_populates="files")


class MeetingExtraRecipient(TenantMixin, SoftDeleteMixin, Base):
    """Een gast op deze vergadering: naam en adres, voor deze keer (CR-09 §3.15).

    Een gastspreker die één keer komt, wordt geen `Person`. Maar hij krijgt wél
    de agenda én hij zit mee aan tafel — dus hij staat in de aanwezigheidslijst
    en niet alleen in een verzendlijstje op het verstuurscherm (Koen,
    15 september 2026). Daarom draagt deze rij ook een naam.
    """

    __tablename__ = "meeting_extra_recipients"
    __table_args__ = {"schema": "meetings"}

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.meetings.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)

    meeting = relationship("Meeting", back_populates="extra_recipients")
