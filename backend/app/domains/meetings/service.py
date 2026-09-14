"""Meeting rules: generate the agenda, take the minutes, send the mails (CR-09).

The transaction boundary lives here, like everywhere else (#635): the service
commits, the screen does not. Everything this module needs from another domain
comes through that domain's facade — `activities.api` for the programme,
`mdm.api` for the circle and the new members, `membership.api` for the year
totals, `mail.api` for sending.

Two rules in here are guards, and both are proven by a test that actually
commits the violation:

- **A file of a sent meeting cannot be deleted.** Derived from the meeting's own
  sent timestamps, so "this meeting has been sent" stays one fact in one place.
- **Sending never locks the document.** Only the sent *report* does, and
  "Heropen verslag" walks that back — every send archives its own PDF, so the
  history keeps every version that ever went out.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.meetings.models import (
    ATTENDANCE_STATUSES,
    CARRY_OVER_SECTIONS,
    FILE_ATTACHMENT,
    FILE_SENT_PDF,
    SECTION_CUSTOM,
    SECTION_EVALUATION,
    SECTION_IDEAS,
    SECTION_MEMBERS,
    SECTION_MISC,
    SECTION_UPCOMING,
    STANDARD_SECTIONS,
    STATUS_AGENDA,
    STATUS_REPORT,
    STATUS_SENT,
    Meeting,
    MeetingAttendance,
    MeetingExtraRecipient,
    MeetingFile,
    MeetingItem,
    MeetingSection,
)
from app.i18n import _


class MeetingError(Exception):
    """A meeting rule refuses. The message is shown to the admin as-is."""


# What a standard section is called on screen and in the PDF. One place, so a
# rename is one line and not a data migration over every meeting ever held.
SECTION_LABELS = {
    SECTION_EVALUATION: "Evaluatie voorbije activiteiten",
    SECTION_UPCOMING: "Volgende activiteiten",
    SECTION_MEMBERS: "Leden",
    SECTION_IDEAS: "Programma-ideeën",
    SECTION_MISC: "Varia",
}


def section_label(section: MeetingSection) -> str:
    """The heading of a section: its own title when custom, its kind otherwise."""
    if section.kind == SECTION_CUSTOM:
        return section.title or _("Nieuwe sectie")
    return _(SECTION_LABELS.get(section.kind, section.kind))


# ── Reading ──────────────────────────────────────────────────────────────────

def list_meetings(db: Session, limit: int = 50) -> list[Meeting]:
    """The meetings, newest first — the list screen."""
    return (db.query(Meeting)
            .order_by(Meeting.meeting_date.desc(), Meeting.id.desc())
            .limit(limit).all())


def get_meeting(db: Session, meeting_id: int) -> Optional[Meeting]:
    return db.get(Meeting, meeting_id)


def previous_meeting(db: Session, before: date,
                     exclude_id: Optional[int] = None) -> Optional[Meeting]:
    """The meeting whose report went out before this date.

    "Previous" is the last meeting that was actually *held and sent*, not merely
    the previous row: a draft agenda for next month must not become the boundary
    of this month's evaluation window.
    """
    query = (db.query(Meeting)
             .filter(Meeting.meeting_date < before,
                     Meeting.report_sent_at.isnot(None)))
    if exclude_id is not None:
        query = query.filter(Meeting.id != exclude_id)
    return query.order_by(Meeting.meeting_date.desc(), Meeting.id.desc()).first()


def sections_of(db: Session, meeting: Meeting) -> list[MeetingSection]:
    return (db.query(MeetingSection)
            .filter(MeetingSection.meeting_id == meeting.id)
            .order_by(MeetingSection.position.asc(), MeetingSection.id.asc())
            .all())


def items_of(db: Session, section: MeetingSection) -> list[MeetingItem]:
    """The items of one section, chronologically (CR-09 §3.19).

    Items with a date sort on it — so an activity added during the meeting slides
    into its place, also *between* existing points — and free items follow at the
    end in the order they were typed.
    """
    return (db.query(MeetingItem)
            .filter(MeetingItem.section_id == section.id)
            .order_by(MeetingItem.sort_key.asc().nullslast(),
                      MeetingItem.position.asc(), MeetingItem.id.asc())
            .all())


# ── Generating the agenda ────────────────────────────────────────────────────

def create_meeting(db: Session, *, meeting_date: date,
                   start_time: Optional[time] = None,
                   location: Optional[str] = None) -> Meeting:
    """A new meeting with its agenda already filled in.

    Time and location are prefilled from the previous meeting when the caller
    leaves them out: a board meets at the same hour in the same room, and typing
    that twelve times a year is work the portal can do.
    """
    previous = previous_meeting(db, meeting_date)
    if start_time is None and previous is not None:
        start_time = previous.start_time
    if not location and previous is not None:
        location = previous.location

    meeting = Meeting(meeting_date=meeting_date, start_time=start_time,
                      location=location, status=STATUS_AGENDA)
    db.add(meeting)
    db.flush()
    _seed_sections(db, meeting)
    generate_agenda(db, meeting, previous=previous)
    db.commit()
    return meeting


def _seed_sections(db: Session, meeting: Meeting) -> dict[str, MeetingSection]:
    """The five standard sections, in their fixed order. Misc is last (§3.17)."""
    sections = {}
    for position, kind in enumerate(STANDARD_SECTIONS):
        section = MeetingSection(meeting_id=meeting.id, kind=kind,
                                 position=position * 10)
        db.add(section)
        sections[kind] = section
    db.flush()
    return sections


def generate_agenda(db: Session, meeting: Meeting,
                    previous: Optional[Meeting] = None) -> None:
    """Fill the generated sections from the data the portal already holds.

    Deterministic throughout — queries and carry-over, no LLM anywhere (§3.1).
    Only *generated* items are replaced: anything typed (a free item, a note) is
    left alone, so regenerating after a change in the programme never eats work.
    """
    from app.domains.activities.api import activities_active_between, activities_from
    from app.domains.mdm.api import new_members_between

    if previous is None:
        previous = previous_meeting(db, meeting.meeting_date, exclude_id=meeting.id)
    since = previous.meeting_date if previous else meeting.meeting_date - timedelta(days=31)
    by_kind = {s.kind: s for s in sections_of(db, meeting)}

    # Evaluation: what ran or started since the previous meeting.
    evaluation = by_kind.get(SECTION_EVALUATION)
    if evaluation is not None:
        _replace_generated(db, evaluation)
        for position, span in enumerate(
                activities_active_between(db, since, meeting.meeting_date)):
            db.add(MeetingItem(meeting_id=meeting.id, section_id=evaluation.id,
                               position=position, activity_id=span.activity.id,
                               sort_key=span.start))

    # Upcoming: the whole planned programme, however far ahead.
    upcoming = by_kind.get(SECTION_UPCOMING)
    if upcoming is not None:
        _replace_generated(db, upcoming)
        for position, span in enumerate(activities_from(db, meeting.meeting_date)):
            db.add(MeetingItem(meeting_id=meeting.id, section_id=upcoming.id,
                               position=position, activity_id=span.activity.id,
                               sort_key=span.start))

    # Members: who joined since the previous meeting.
    members = by_kind.get(SECTION_MEMBERS)
    if members is not None:
        _replace_generated(db, members)
        window_end = meeting.meeting_date + timedelta(days=1)
        for position, new_member in enumerate(
                new_members_between(db, _as_dt(since), _as_dt(window_end))):
            db.add(MeetingItem(
                meeting_id=meeting.id, section_id=members.id, position=position,
                member_id=new_member["member_id"],
                noted_steward_person_id=new_member["steward_person_id"]))

    # Ideas: carried over from the previous meeting, text and all.
    ideas = by_kind.get(SECTION_IDEAS)
    if ideas is not None and previous is not None:
        _carry_over(db, previous, meeting, by_kind)

    db.flush()


def _replace_generated(db: Session, section: MeetingSection) -> None:
    """Drop this section's generated items; keep everything that was typed.

    A generated item is one that references a subject and carries no notes: it
    was put there by the agenda build and nobody has written on it yet. An item
    with notes is somebody's work and survives a regeneration.
    """
    for item in items_of(db, section):
        referenced = item.activity_id is not None or item.member_id is not None
        if referenced and not (item.notes or "").strip():
            db.delete(item)
    db.flush()


def _carry_over(db: Session, previous: Meeting, meeting: Meeting,
                by_kind: dict[str, MeetingSection]) -> None:
    """Copy the previous meeting's ideas and misc items into this agenda.

    Only those two sections carry over (§3.6): everything else is regenerated
    from live data, so copying it would create a second, ageing truth.
    """
    already = {item.carried_over_from for item in
               db.query(MeetingItem).filter(MeetingItem.meeting_id == meeting.id).all()}
    for section in sections_of(db, previous):
        if section.kind not in CARRY_OVER_SECTIONS:
            continue
        target = by_kind.get(section.kind)
        if target is None:
            continue
        for item in items_of(db, section):
            if item.id in already:
                continue
            db.add(MeetingItem(meeting_id=meeting.id, section_id=target.id,
                               position=item.position, title=item.title,
                               notes=item.notes, carried_over_from=item.id))


def _as_dt(day: date) -> datetime:
    """Midnight UTC of that day — `Member.created_at` is a timestamp."""
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


# ── Editing the document ─────────────────────────────────────────────────────

def _touch(db: Session, meeting: Meeting) -> None:
    """Any edit after the agenda went out means the minutes have started.

    Not a button: taking attendance or typing a note *is* entering the report
    phase (§3.23). A sent meeting stays sent until it is explicitly reopened.
    """
    if meeting.status == STATUS_AGENDA:
        meeting.status = STATUS_REPORT


def add_item(db: Session, meeting: Meeting, section: MeetingSection, *,
             title: Optional[str] = None, activity_id: Optional[int] = None,
             notes: Optional[str] = None) -> MeetingItem:
    """Add a point — linked to an activity, or free.

    A linked point gets the activity's start date as its sort key, so it lands
    chronologically between the points that are already there; a free point has
    no date and joins the tail.
    """
    _refuse_when_sent(meeting)
    if activity_id is None and not (title or "").strip():
        raise MeetingError(_("Kies een activiteit of typ een titel voor het punt."))
    sort_key = None
    if activity_id is not None:
        from app.domains.activities.api import Activity, ActivityDate

        sort_key = (db.query(func.min(ActivityDate.start_date))
                    .filter(ActivityDate.activity_id == activity_id).scalar())
        if db.get(Activity, activity_id) is None:
            raise MeetingError(_("Die activiteit bestaat niet."))
    last = (db.query(func.max(MeetingItem.position))
            .filter(MeetingItem.section_id == section.id).scalar() or 0)
    item = MeetingItem(meeting_id=meeting.id, section_id=section.id,
                       position=last + 1, title=title, notes=notes,
                       activity_id=activity_id, sort_key=sort_key)
    db.add(item)
    _touch(db, meeting)
    db.commit()
    return item


def update_item(db: Session, meeting: Meeting, item_id: int, *,
                notes: Optional[str] = None,
                title: Optional[str] = None) -> MeetingItem:
    """Write the minutes on one point. `None` means "left alone", not "cleared"."""
    _refuse_when_sent(meeting)
    item = _item_of(db, meeting, item_id)
    if notes is not None:
        item.notes = notes
    if title is not None:
        item.title = title
    _touch(db, meeting)
    db.commit()
    return item


def set_noted_steward(db: Session, meeting: Meeting, item_id: int,
                      person_id: Optional[int]) -> MeetingItem:
    """Note which steward a new member gets — or take the note back out.

    Its own function and not a keyword on `update_item`, because there the
    "leave alone" and "clear" cases collapse into the same `None`: choosing the
    empty option in the dropdown would then be silently ignored, and the wrong
    name would keep standing in the report.

    What is stored is *minutes*: the assignment itself is made in the national
    administration and returns through the MDM import (§3.9).
    """
    _refuse_when_sent(meeting)
    item = _item_of(db, meeting, item_id)
    item.noted_steward_person_id = person_id
    _touch(db, meeting)
    db.commit()
    return item


def _item_of(db: Session, meeting: Meeting, item_id: int) -> MeetingItem:
    item = db.get(MeetingItem, item_id)
    if item is None or item.meeting_id != meeting.id:
        raise MeetingError(_("Dat punt hoort niet bij deze vergadering."))
    return item


def delete_item(db: Session, meeting: Meeting, item_id: int) -> None:
    """Leave a point off this agenda — a far-out activity with nothing to say."""
    _refuse_when_sent(meeting)
    item = db.get(MeetingItem, item_id)
    if item is not None and item.meeting_id == meeting.id:
        db.delete(item)
        _touch(db, meeting)
        db.commit()


def add_section(db: Session, meeting: Meeting, title: str) -> MeetingSection:
    """A named block for a big topic — inserted before Varia, which stays last."""
    _refuse_when_sent(meeting)
    title = (title or "").strip()
    if not title:
        raise MeetingError(_("Geef de sectie een naam."))
    misc = next((s for s in sections_of(db, meeting) if s.kind == SECTION_MISC), None)
    position = (misc.position - 1) if misc is not None else 100
    section = MeetingSection(meeting_id=meeting.id, kind=SECTION_CUSTOM,
                             title=title, position=position)
    db.add(section)
    if misc is not None:
        # Keep Varia last even after several custom sections: push it along.
        misc.position = position + 10
    _touch(db, meeting)
    db.commit()
    return section


def set_attendance(db: Session, meeting: Meeting, person_id: int,
                   status: Optional[str]) -> None:
    """Tick someone present, excused, or neither.

    `None` removes the row rather than storing a third state: "not ticked" is
    the absence of an answer, and a row saying so would have to be kept in step
    with the circle.
    """
    _refuse_when_sent(meeting)
    if status is not None and status not in ATTENDANCE_STATUSES:
        raise MeetingError(_("Onbekende aanwezigheid."))
    row = (db.query(MeetingAttendance)
           .filter(MeetingAttendance.meeting_id == meeting.id,
                   MeetingAttendance.person_id == person_id).first())
    if status is None:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(MeetingAttendance(meeting_id=meeting.id, person_id=person_id,
                                 status=status))
    else:
        row.status = status
    _touch(db, meeting)
    db.commit()


def attendance_of(db: Session, meeting: Meeting) -> dict[int, str]:
    """Per person id: present or excused. Everyone else is simply not ticked."""
    return {row.person_id: row.status for row in
            db.query(MeetingAttendance)
            .filter(MeetingAttendance.meeting_id == meeting.id).all()}


# ── Files ────────────────────────────────────────────────────────────────────

def add_file(db: Session, meeting: Meeting, *, filename: str, content_type: str,
             data: bytes, on_agenda_mail: bool = True,
             on_report_mail: bool = True,
             purpose: str = FILE_ATTACHMENT) -> MeetingFile:
    """Store an attachment with the meeting (bytes and all, see models.py)."""
    if not data:
        raise MeetingError(_("Het bestand is leeg."))
    record = MeetingFile(meeting_id=meeting.id, purpose=purpose,
                         filename=filename[:255],
                         content_type=content_type or "application/octet-stream",
                         byte_size=len(data), data=data,
                         on_agenda_mail=on_agenda_mail,
                         on_report_mail=on_report_mail)
    db.add(record)
    db.commit()
    return record


def delete_file(db: Session, meeting: Meeting, file_id: int) -> None:
    """Remove an attachment — refused once the meeting has been sent.

    The guard reads the meeting's own sent timestamps: what went out with a mail
    stays retrievable, and an archived PDF is never removable at all. Proven by
    a test that sends, tries the delete, and asserts this refusal.
    """
    record = db.get(MeetingFile, file_id)
    if record is None or record.meeting_id != meeting.id:
        return
    if record.purpose == FILE_SENT_PDF:
        raise MeetingError(_("Een verstuurde PDF blijft bewaard."))
    if meeting.agenda_sent_at is not None or meeting.report_sent_at is not None:
        raise MeetingError(
            _("Deze vergadering is al verstuurd — de bijlage blijft bewaard."))
    db.delete(record)
    db.commit()


def files_of(db: Session, meeting: Meeting,
             purpose: Optional[str] = FILE_ATTACHMENT) -> list[MeetingFile]:
    query = db.query(MeetingFile).filter(MeetingFile.meeting_id == meeting.id)
    if purpose is not None:
        query = query.filter(MeetingFile.purpose == purpose)
    return query.order_by(MeetingFile.id.asc()).all()


def get_file(db: Session, meeting_id: int, file_id: int) -> Optional[MeetingFile]:
    record = db.get(MeetingFile, file_id)
    return record if record is not None and record.meeting_id == meeting_id else None


# ── Recipients ───────────────────────────────────────────────────────────────

def add_extra_recipient(db: Session, meeting: Meeting, email: str) -> None:
    """A one-off address for this meeting only — the guest speaker case."""
    email = (email or "").strip()
    if "@" not in email:
        raise MeetingError(_("Dat is geen e-mailadres."))
    exists = (db.query(MeetingExtraRecipient)
              .filter(MeetingExtraRecipient.meeting_id == meeting.id,
                      func.lower(MeetingExtraRecipient.email) == email.lower())
              .first())
    if exists is None:
        db.add(MeetingExtraRecipient(meeting_id=meeting.id, email=email))
        db.commit()


def remove_extra_recipient(db: Session, meeting: Meeting, recipient_id: int) -> None:
    row = db.get(MeetingExtraRecipient, recipient_id)
    if row is not None and row.meeting_id == meeting.id:
        db.delete(row)
        db.commit()


@dataclass(frozen=True)
class Recipients:
    """Who this mail goes to, and who has no address to send to."""

    emails: list[str]
    names: list[str]
    without_email: list[str]


def recipients_for(db: Session, meeting: Meeting) -> Recipients:
    """The circle plus this meeting's one-off addresses.

    Someone in the circle without an e-mail address is *named*, not silently
    skipped: a missing address is something the secretary must see before
    sending, not after.
    """
    from app.domains.mdm.api import organization_circle

    emails, names, missing = [], [], []
    for entry in organization_circle(db, on_day=meeting.meeting_date):
        name = f"{entry.person.first_name} {entry.person.last_name}".strip()
        if entry.email:
            emails.append(entry.email)
            names.append(name)
        else:
            missing.append(name)
    for extra in (db.query(MeetingExtraRecipient)
                  .filter(MeetingExtraRecipient.meeting_id == meeting.id)
                  .order_by(MeetingExtraRecipient.id.asc()).all()):
        if extra.email not in emails:
            emails.append(extra.email)
            names.append(extra.email)
    return Recipients(emails=emails, names=names, without_email=missing)


# ── Sending ──────────────────────────────────────────────────────────────────

def send_meeting_mail(db: Session, meeting: Meeting, *, kind: str, subject: str,
                      body_html: str, reply_to: Optional[str],
                      pdf: bytes, pdf_filename: str) -> None:
    """Mail the agenda or the report: one mail, the whole circle in To.

    Deliberately the opposite of the newsletter's per-recipient campaign path
    (§3.13) — the circle knows each other and replies all. The PDF handed in here
    was regenerated by the caller moments ago, is archived as it goes out, and the
    sent moment is stamped in the same transaction: what was sent and the fact
    that it was sent can never disagree.
    """
    from app.domains.mail.api import send_with_attachments

    if kind not in ("agenda", "report"):
        raise MeetingError(_("Onbekend soort mail."))
    recipients = recipients_for(db, meeting)
    if not recipients.emails:
        raise MeetingError(_("Er is niemand met een e-mailadres om naar te versturen."))

    attachments = [(pdf_filename, "application/pdf", pdf)]
    for record in files_of(db, meeting):
        wanted = record.on_agenda_mail if kind == "agenda" else record.on_report_mail
        if wanted:
            attachments.append((record.filename, record.content_type, record.data))

    send_with_attachments(to_emails=recipients.emails, subject=subject,
                          body_html=body_html, attachments=attachments,
                          reply_to=reply_to, email_type="meeting")

    add_file(db, meeting, filename=pdf_filename, content_type="application/pdf",
             data=pdf, purpose=FILE_SENT_PDF)
    now = datetime.now(timezone.utc)
    if kind == "agenda":
        meeting.agenda_sent_at = now
        _touch(db, meeting)
    else:
        meeting.report_sent_at = now
        meeting.status = STATUS_SENT
    db.commit()


def reopen(db: Session, meeting: Meeting) -> None:
    """Reopen a sent report for the correction that comes the day after.

    The earlier PDF stays archived; resending adds a second one. History never
    loses a version that went out.
    """
    if meeting.status != STATUS_SENT:
        return
    meeting.status = STATUS_REPORT
    db.commit()


def _refuse_when_sent(meeting: Meeting) -> None:
    if meeting.status == STATUS_SENT:
        raise MeetingError(
            _("Het verslag is verstuurd. Heropen het eerst om nog te wijzigen."))


# ── The members header ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class MemberStanding:
    """What the members section says in its header, for one moment in the year."""

    year: int
    total: int
    renewal_running: bool
    renewal_year: Optional[int]
    renewed: Optional[int]
    to_renew: Optional[int]


def member_standing(db: Session, today: Optional[date] = None) -> MemberStanding:
    """The membership count, following the renewal cycle (§3.20).

    The working year is the calendar year. Before the renewal start date the
    header is simply this year's total; from that date through 31 December it
    also carries how far the renewal has come (it should be done by early
    December); from 1 January the new year's count is the whole story, because
    renewals and new members both land in it.
    """
    from app.domains.membership.api import (members_with_membership_for_year,
                                            renewal_open, renewal_years)

    if today is None:
        today = date.today()
    total = len(members_with_membership_for_year(db, today.year))
    if not renewal_open(today):
        return MemberStanding(year=today.year, total=total, renewal_running=False,
                              renewal_year=None, renewed=None, to_renew=None)
    reference, target = renewal_years(today)
    if target == today.year:
        # The campaign is about the year we are already counting: its progress is
        # the total itself, so showing it twice would only invite comparison.
        return MemberStanding(year=today.year, total=total, renewal_running=False,
                              renewal_year=None, renewed=None, to_renew=None)
    return MemberStanding(
        year=today.year, total=total, renewal_running=True, renewal_year=target,
        renewed=len(members_with_membership_for_year(db, target)),
        to_renew=len(members_with_membership_for_year(db, reference)))


# ── The document, ready to show ──────────────────────────────────────────────
# Built here and not in the screen: the same structure feeds the HTML page and
# the PDF, and a second builder is how the two start disagreeing about what a
# meeting says.

@dataclass(frozen=True)
class DocumentItem:
    """One point, with everything both the screen and the PDF need."""

    id: int
    label: str
    meta: str
    notes: str
    kind: str                      # "activity" | "member" | "free"
    source_url: Optional[str]      # where the source chip goes
    is_full: bool
    steward_person_id: Optional[int]


@dataclass(frozen=True)
class DocumentSection:
    id: int
    kind: str
    label: str
    subtitle: str
    items: list[DocumentItem]
    can_add: bool


def document_of(db: Session, meeting: Meeting) -> list[DocumentSection]:
    """The meeting as sections of points, in reading order."""
    from app.domains.activities.api import Activity, registration_counts

    sections = sections_of(db, meeting)
    all_items = {s.id: items_of(db, s) for s in sections}

    activity_ids = [i.activity_id for items in all_items.values() for i in items
                    if i.activity_id]
    activities = {}
    counts = {}
    if activity_ids:
        activities = {a.id: a for a in
                      db.query(Activity).filter(Activity.id.in_(activity_ids)).all()}
        counts = registration_counts(db, activity_ids)

    member_ids = [i.member_id for items in all_items.values() for i in items
                  if i.member_id]
    member_labels = _member_labels(db, member_ids)

    out = []
    for section in sections:
        items = [_present(item, activities, counts, member_labels)
                 for item in all_items[section.id]]
        out.append(DocumentSection(
            id=section.id, kind=section.kind, label=section_label(section),
            subtitle=_subtitle_for(section.kind), items=items,
            can_add=meeting.status != STATUS_SENT))
    return out


def _subtitle_for(kind: str) -> str:
    """One line under a generated heading saying where its content comes from —
    so a board member can tell a query from something somebody typed."""
    if kind == SECTION_EVALUATION:
        return _("Activiteiten sinds de vorige vergadering, lopende inbegrepen.")
    if kind == SECTION_UPCOMING:
        return _("Alles wat gepland staat. Laat weg wat nu niets te bespreken heeft.")
    if kind == SECTION_MEMBERS:
        return _("Nieuwe leden sinds de vorige vergadering, uit het ledenbestand.")
    if kind == SECTION_IDEAS:
        return _("Overgenomen van de vorige vergadering.")
    return ""


def _present(item: MeetingItem, activities: dict, counts: dict,
             member_labels: dict) -> DocumentItem:
    """One stored item as it reads on screen.

    An activity point renders **name | date time location · N ingeschreven** and
    carries no price: an activity can have several (the barbecue has four), so one
    price field would lie — they live one click away, through the source chip.
    """
    from app.domains.meetings.pdf import short_date

    if item.activity_id and item.activity_id in activities:
        activity = activities[item.activity_id]
        booked, capacity = counts.get(activity.id, (0, None))
        parts = []
        if item.sort_key:
            parts.append(short_date(item.sort_key))
        if activity.location:
            parts.append(activity.location)
        if booked or capacity:
            shown = f"{booked}/{capacity}" if capacity else str(booked)
            parts.append(_("%s ingeschreven") % shown)
        return DocumentItem(
            id=item.id, label=activity.name, meta=" · ".join(parts),
            notes=item.notes or "", kind="activity",
            source_url=f"/admin/activiteiten/{activity.id}",
            is_full=bool(capacity and booked >= capacity),
            steward_person_id=None)

    if item.member_id:
        label, address = member_labels.get(item.member_id, (_("Nieuw lid"), ""))
        return DocumentItem(
            id=item.id, label=label, meta=address, notes=item.notes or "",
            kind="member", source_url=f"/admin/leden/gezin/{item.member_id}",
            is_full=False, steward_person_id=item.noted_steward_person_id)

    return DocumentItem(id=item.id, label=item.title or _("Punt"), meta="",
                        notes=item.notes or "", kind="free", source_url=None,
                        is_full=False, steward_person_id=None)


def _member_labels(db: Session, member_ids: list[int]) -> dict[int, tuple[str, str]]:
    """Per member id: *head member – partner* and the address.

    A household has no name of its own (§3.20), so the label is built from the
    person relations — the same shape the board writes in its report.
    """
    from app.domains.mdm.api import Member, MemberPerson, Person

    if not member_ids:
        return {}
    rows = (db.query(MemberPerson, Person)
            .join(Person, Person.id == MemberPerson.person_id)
            .filter(MemberPerson.member_id.in_(member_ids)).all())
    people: dict[int, list] = {}
    for link, person in rows:
        people.setdefault(link.member_id, []).append((link.relation_type, person))

    out = {}
    for member_id in member_ids:
        entries = people.get(member_id, [])
        head = next((p for relation, p in entries if relation == "HOOFDLID"), None)
        partner = next((p for relation, p in entries if relation == "PARTNER"), None)
        if head is None and entries:
            head = entries[0][1]
        names = [f"{p.first_name} {p.last_name}".strip()
                 for p in (head, partner) if p is not None]
        out[member_id] = (" – ".join(names) or _("Nieuw lid"),
                          _address_line(head))
    return out


def _address_line(person) -> str:
    """`Lindestraat 12` — street and number, as the report writes it."""
    address = getattr(person, "address", None)
    if address is None:
        return ""
    return " ".join(part for part in [address.street, address.house_number]
                    if part).strip()


def addable_activities(db: Session, meeting: Meeting, query: str = "") -> list:
    """Activities that could still be added to this agenda.

    The picker behind "Punt toevoegen" during the meeting (§3.19): everything
    planned that is not already a point here — which is how a venue booked a year
    ahead, or something created after the agenda went out, still gets discussed.
    """
    from app.domains.activities.api import activities_from

    present = {item.activity_id for item in
               db.query(MeetingItem).filter(MeetingItem.meeting_id == meeting.id).all()
               if item.activity_id}
    query = (query or "").strip().lower()
    out = []
    for span in activities_from(db, meeting.meeting_date):
        if span.activity.id in present:
            continue
        if query and query not in span.activity.name.lower():
            continue
        out.append(span)
    return out
