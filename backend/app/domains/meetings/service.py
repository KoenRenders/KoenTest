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

from app.domains.meetings.codes import SECTION_KIND
from app.domains.meetings.models import (
    Attendance,
    CARRY_OVER_SECTIONS,
    FilePurpose,
    Meeting,
    MeetingAttendance,
    MeetingExtraRecipient,
    MeetingFile,
    MeetingItem,
    MeetingSection,
    MeetingStatus,
    STANDARD_SECTIONS,
    SectionKind,
)
from app.i18n import _
from app.kernel.codes import code_label


class MeetingError(Exception):
    """A meeting rule refuses. The message is shown to the admin as-is."""


# What a standard section is called on screen and in the PDF. One place, so a
# rename is one line and not a data migration over every meeting ever held.
# Hoe ver de agenda vooruit kijkt bij het samenstellen. Drie maanden, want dat is
# wat het bestuur nodig heeft om te handelen: een flyer maken, helpers zoeken, de
# activiteit op de sociale media en in de nieuwsbrief zetten (Koen, 16 september
# 2026). Wat verder ligt, staat niet in de weg maar is één klik weg via de kiezer
# — die toont wél alles, ook de zaal die een jaar vooruit vastligt.
UPCOMING_MONTHS = 3


def section_label(section: MeetingSection) -> str:
    """The heading of a section: its own title when custom, its kind otherwise.

    The words come from the `section_kind` label table (CR-12 fase 3); the
    dictionary that held them here is gone.
    """
    if section.kind == SectionKind.CUSTOM:
        return section.title or _("Nieuwe sectie")
    return code_label(SECTION_KIND.name, section.kind)


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
                      location=location, status=MeetingStatus.AGENDA)
    db.add(meeting)
    db.flush()
    _seed_sections(db, meeting)
    generate_agenda(db, meeting, previous=previous)
    db.commit()
    return meeting


def update_meeting(db: Session, meeting: Meeting, *, meeting_date: date,
                   start_time: Optional[time] = None,
                   location: Optional[str] = None) -> Meeting:
    """Verplaats of hernoem een vergadering — en stel de agenda opnieuw samen.

    Een vergadering een week opschuiven gebeurt (Koen, 14 september 2026), en dan
    klopt de agenda niet meer: activiteiten van die week horen ineens bij de
    evaluatie in plaats van bij wat komt. Daarom volgt bij een datumwijziging een
    nieuwe samenstelling — maar **alleen van wat gegenereerd is**: elk punt waar
    iemand op getypt heeft blijft staan, op zijn plaats. Werk kwijtraken door een
    datum te corrigeren zou de correctie duurder maken dan de fout.

    Enkel uur of locatie wijzigen raakt de agenda niet: die twee bepalen geen
    venster.
    """
    _refuse_when_sent(meeting)
    verschoven = meeting.meeting_date != meeting_date
    meeting.meeting_date = meeting_date
    meeting.start_time = start_time
    meeting.location = location
    db.flush()
    if verschoven:
        generate_agenda(db, meeting)
    db.commit()
    return meeting


def _seed_sections(db: Session, meeting: Meeting) -> dict[SectionKind, MeetingSection]:
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

    # EERST alle gegenereerde punten van de twee activiteitensecties weg, DAN pas
    # opnieuw vullen. Dat is geen stijlkwestie: verschuift de vergadering, dan
    # wisselt een activiteit van sectie — en wie sectie per sectie opruimt-en-vult,
    # ziet bij de evaluatie het oude punt nog in "volgende" staan, slaat het over,
    # en ruimt het daarna op. Het punt verdwijnt dan helemaal.
    evaluation = by_kind.get(SectionKind.EVALUATION)
    upcoming = by_kind.get(SectionKind.UPCOMING)
    for sectie in (evaluation, upcoming):
        if sectie is not None:
            _replace_generated(db, sectie)

    # Evaluation: what ran or started since the previous meeting.
    if evaluation is not None:
        _add_activities(db, meeting, evaluation,
                        activities_active_between(db, since, meeting.meeting_date))

    # Upcoming: wat binnen de agendeerhorizon valt (§3.14, herzien 16 sep 2026).
    if upcoming is not None:
        _add_activities(db, meeting, upcoming,
                        [span for span in activities_from(db, meeting.meeting_date)
                         if span.start <= _horizon(meeting.meeting_date)])

    # Members: who joined since the previous meeting.
    members = by_kind.get(SectionKind.MEMBERS)
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
    ideas = by_kind.get(SectionKind.IDEAS)
    if ideas is not None and previous is not None:
        _carry_over(db, previous, meeting, by_kind)

    db.flush()


def _add_activities(db: Session, meeting: Meeting, section: MeetingSection,
                    spans) -> None:
    """Zet deze activiteiten in de sectie, zonder iets te verdubbelen.

    Overslaan wat er al staat is niet netjesheid maar noodzaak: bij het opnieuw
    samenstellen (na een datumwijziging) blijft een punt mét notities staan, en
    zonder deze controle zou er een tweede, leeg punt voor dezelfde activiteit
    naast komen te staan.
    """
    aanwezig = {item.activity_id for item in
                db.query(MeetingItem)
                .filter(MeetingItem.meeting_id == meeting.id).all()
                if item.activity_id}
    for position, span in enumerate(spans):
        if span.activity.id in aanwezig:
            continue
        db.add(MeetingItem(meeting_id=meeting.id, section_id=section.id,
                           position=position, activity_id=span.activity.id,
                           sort_key=span.start))
        aanwezig.add(span.activity.id)
    db.flush()


def _horizon(vanaf: date) -> date:
    """Dezelfde dag, `UPCOMING_MONTHS` maanden later.

    In maanden en niet in dagen: "drie maanden vooruit" is hoe het bestuur denkt,
    en 90 dagen verschuift met de lengte van de maanden mee.
    """
    maand = vanaf.month - 1 + UPCOMING_MONTHS
    jaar = vanaf.year + maand // 12
    maand = maand % 12 + 1
    dag = min(vanaf.day, [31, 29 if jaar % 4 == 0 and (jaar % 100 != 0 or jaar % 400 == 0)
                          else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][maand - 1])
    return date(jaar, maand, dag)


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
    if meeting.status == MeetingStatus.AGENDA:
        meeting.status = MeetingStatus.REPORT


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
    if activity_id is not None and _al_op_de_agenda(db, meeting, activity_id):
        # De kiezer biedt zo'n activiteit niet aan, maar dat is een scherm en geen
        # grendel: een dubbele klik, een openstaande kiezer in een tweede tabblad
        # of een herhaalde post levert anders twee identieke punten op — en die
        # staan dan allebei in het verslag.
        raise MeetingError(_("Die activiteit staat al op deze agenda."))
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


def _al_op_de_agenda(db: Session, meeting: Meeting, activity_id: int) -> bool:
    return db.query(MeetingItem).filter(
        MeetingItem.meeting_id == meeting.id,
        MeetingItem.activity_id == activity_id).first() is not None


def update_item(db: Session, meeting: Meeting, item_id: int, *,
                notes: Optional[str] = None,
                title: Optional[str] = None) -> MeetingItem:
    """Write the minutes on one point. `None` means "left alone", not "cleared"."""
    _refuse_when_sent(meeting)
    item = _item_of(db, meeting, item_id)
    if notes is not None:
        # De notities komen uit een WYSIWYG-editor en gaan als HTML naar het
        # scherm én de PDF. Ontsmetten bij het OPSLAAN en niet bij het tonen: dan
        # is er één plek, en staat er nooit iets in de databank dat we bij het
        # renderen nog moeten wantrouwen. Dezelfde filter als de CMS-inhoud.
        from app.domains.cms.api import sanitize_cms_html

        item.notes = sanitize_cms_html(notes) or ""
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
    misc = next((s for s in sections_of(db, meeting) if s.kind == SectionKind.MISC), None)
    position = (misc.position - 1) if misc is not None else 100
    section = MeetingSection(meeting_id=meeting.id, kind=SectionKind.CUSTOM,
                             title=title, position=position)
    db.add(section)
    if misc is not None:
        # Keep Varia last even after several custom sections: push it along.
        misc.position = position + 10
    _touch(db, meeting)
    db.commit()
    return section


def set_attendance(db: Session, meeting: Meeting, *, person_id: Optional[int] = None,
                   guest_id: Optional[int] = None,
                   status: Optional[str] = None) -> None:
    """Tick someone present, excused, or neither — iemand uit de kring of een gast.

    `None` als status verwijdert de rij in plaats van een derde toestand te
    bewaren: "niet aangevinkt" is de afwezigheid van een antwoord, en een rij die
    dat zegt zou in de pas moeten blijven met de kring.
    """
    _refuse_when_sent(meeting)
    if status is not None and status not in tuple(Attendance):
        raise MeetingError(_("Onbekende aanwezigheid."))
    if (person_id is None) == (guest_id is None):
        raise MeetingError(_("Geef één persoon of één gast op."))
    vraag = db.query(MeetingAttendance).filter(
        MeetingAttendance.meeting_id == meeting.id)
    vraag = (vraag.filter(MeetingAttendance.person_id == person_id) if person_id
             else vraag.filter(MeetingAttendance.guest_id == guest_id))
    row = vraag.first()
    if status is None:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(MeetingAttendance(meeting_id=meeting.id, person_id=person_id,
                                 guest_id=guest_id, status=status))
    else:
        row.status = status
    _touch(db, meeting)
    db.commit()


def attendance_of(db: Session, meeting: Meeting) -> dict[str, Attendance]:
    """Per deelnemer: present of excused. Wie er niet in staat, is niet aangevinkt.

    De sleutel is een string (`p12` of `g3`) en geen id: personen en gasten
    worden apart genummerd, dus alleen een id zou de twee door elkaar halen.

    De waarde is het LID sinds CR-12 fase 3, want Python vertakt erop. Het
    scherm krijgt de code — zie `admin_ui._document_view`, waar dat op de
    grens gebeurt.
    """
    uit = {}
    for row in (db.query(MeetingAttendance)
                .filter(MeetingAttendance.meeting_id == meeting.id).all()):
        sleutel = f"p{row.person_id}" if row.person_id else f"g{row.guest_id}"
        uit[sleutel] = row.status
    return uit


# ── Files ────────────────────────────────────────────────────────────────────

def add_file(db: Session, meeting: Meeting, *, filename: str, content_type: str,
             data: bytes, on_agenda_mail: bool = True,
             on_report_mail: bool = True, purpose: FilePurpose = FilePurpose.ATTACHMENT,
             commit: bool = True) -> MeetingFile:
    """Store an attachment with the meeting (bytes and all, see models.py).

    `commit=False` for the caller that is building a larger transaction — the
    send, which archives the PDF and stamps the sent moment as one step.
    """
    if not data:
        raise MeetingError(_("Het bestand is leeg."))
    record = MeetingFile(meeting_id=meeting.id, purpose=purpose,
                         filename=filename[:255],
                         content_type=content_type or "application/octet-stream",
                         byte_size=len(data), data=data,
                         on_agenda_mail=on_agenda_mail,
                         on_report_mail=on_report_mail)
    db.add(record)
    if commit:
        db.commit()
    else:
        db.flush()
    return record


def set_file_mailing(db: Session, meeting: Meeting, file_id: int, *,
                     mail: str) -> None:
    """Zet aan of uit of deze bijlage met de agenda- dan wel de verslagmail meegaat.

    Gevraagd door Koen op 14 september: het gebeurt dat er één bijlage bij de
    agenda hoort (een draaiboek vooraf) en een ándere bij het verslag. Het model
    kon dat al — `on_agenda_mail` en `on_report_mail` staan er sinds de eerste
    migratie — maar het scherm bood de keuze niet aan, dus stond alles altijd op
    beide.

    Een schakelaar en geen waarde: het scherm toont de huidige stand, en één klik
    keert ze om. Zo hoeft het scherm geen toestand mee te sturen die intussen
    verouderd kan zijn.
    """
    record = db.get(MeetingFile, file_id)
    if record is None or record.meeting_id != meeting.id:
        return
    if record.purpose == FilePurpose.SENT_PDF:
        raise MeetingError(_("Een verstuurde PDF verandert niet meer."))
    if mail == "agenda":
        record.on_agenda_mail = not record.on_agenda_mail
    elif mail == "report":
        record.on_report_mail = not record.on_report_mail
    else:
        raise MeetingError(_("Onbekende mail."))
    db.commit()


def file_is_sent(meeting: Meeting, record: MeetingFile) -> bool:
    """Is dit bestand al écht de deur uit?

    Niet "hoort deze vergadering bij een verstuurde mail", maar: ging dít bestand
    mee? Een bijlage die alleen bij het verslag hoort, is niet verstuurd wanneer
    enkel de agenda vertrok — en die moet je dus nog kunnen weghalen. De eerste
    versie keek naar de vergadering in plaats van naar het bestand, en sloot
    daarmee te veel af (Koen, 15 september 2026).

    Sinds #258/126 is dit een **stempel** en geen afleiding meer. De afleiding
    ("de agenda is weg én dit bestand stond aangevinkt") gaf het verkeerde
    antwoord voor precies het geval dat het vaakst voorkomt: een bijlage die je
    ná de agendamail uploadt voor bij het verslag. Die staat standaard ook voor
    de agenda aangevinkt, las dus als "verstuurd", en was daarna niet meer te
    verwijderen of om te zetten — terwijl ze nooit iemand bereikt had. Een
    stempel kan dat niet: hij wordt gezet op het moment dat het bestand écht
    meegaat, in dezelfde transactie als de verzending.
    """
    if record.purpose == FilePurpose.SENT_PDF:
        return True
    return record.sent_with_agenda_at is not None or record.sent_with_report_at is not None


def sent_with_label(record: MeetingFile) -> str:
    """Waarmee is deze bijlage vertrokken? Leeg wanneer ze nog niet weg is.

    Het antwoord hoort op het scherm, ook — juist — bij een afgesloten
    vergadering: daar zijn de aanvinkvakjes weg en bleef er anders alleen het
    woord "verstuurd" over, dat niet zegt of de ontvanger het bij de agenda of
    bij het verslag in zijn mailbox vond (Koen, 16 september 2026).
    """
    met_agenda = record.sent_with_agenda_at is not None
    met_verslag = record.sent_with_report_at is not None
    if met_agenda and met_verslag:
        return _("met agenda en verslag")
    if met_agenda:
        return _("met de agenda")
    if met_verslag:
        return _("met het verslag")
    return ""


def delete_file(db: Session, meeting: Meeting, file_id: int) -> None:
    """Remove an attachment — refused once this file has actually gone out.

    Wat verstuurd is, blijft opvraagbaar: een bestuurslid dat de mail openslaat,
    moet de bijlage nog kunnen ophalen. Een gearchiveerde PDF verdwijnt nooit.
    Bewezen door een test die verstuurt, probeert te verwijderen, en de benoemde
    weigering controleert.
    """
    record = db.get(MeetingFile, file_id)
    if record is None or record.meeting_id != meeting.id:
        return
    if record.purpose == FilePurpose.SENT_PDF:
        raise MeetingError(_("Een verstuurde PDF blijft bewaard."))
    if file_is_sent(meeting, record):
        raise MeetingError(
            _("Deze bijlage is al meegestuurd — ze blijft bewaard."))
    db.delete(record)
    db.commit()


def files_of(db: Session, meeting: Meeting,
             purpose: Optional[FilePurpose] = FilePurpose.ATTACHMENT) -> list[MeetingFile]:
    query = db.query(MeetingFile).filter(MeetingFile.meeting_id == meeting.id)
    if purpose is not None:
        query = query.filter(MeetingFile.purpose == purpose)
    return query.order_by(MeetingFile.id.asc()).all()


def get_file(db: Session, meeting_id: int, file_id: int) -> Optional[MeetingFile]:
    record = db.get(MeetingFile, file_id)
    return record if record is not None and record.meeting_id == meeting_id else None


# ── Recipients ───────────────────────────────────────────────────────────────

def add_extra_recipient(db: Session, meeting: Meeting, email: str,
                        name: Optional[str] = None) -> None:
    """Nodig een gast uit voor deze ene vergadering: naam en adres.

    Hij krijgt de mails én hij staat in de aanwezigheidslijst — wie mee aan tafel
    zit, hoort in het verslag, ook als hij geen lid en geen persoon in de
    administratie is.
    """
    email = (email or "").strip()
    if "@" not in email:
        raise MeetingError(_("Dat is geen e-mailadres."))
    exists = (db.query(MeetingExtraRecipient)
              .filter(MeetingExtraRecipient.meeting_id == meeting.id,
                      func.lower(MeetingExtraRecipient.email) == email.lower())
              .first())
    if exists is None:
        db.add(MeetingExtraRecipient(meeting_id=meeting.id, email=email,
                                     name=(name or "").strip() or None))
        db.commit()


def extra_recipients_of(db: Session, meeting: Meeting) -> list[MeetingExtraRecipient]:
    """De losse adressen van deze vergadering, in de volgorde van toevoegen."""
    return (db.query(MeetingExtraRecipient)
            .filter(MeetingExtraRecipient.meeting_id == meeting.id)
            .order_by(MeetingExtraRecipient.id.asc()).all())


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


def mail_signature(db: Session) -> str:
    """De ondertekening onder de vergadermails, zoals deze afdeling hem voert."""
    from app.kernel.tenant_config import tenant_meeting_signature

    return tenant_meeting_signature(db)


def set_mail_signature(db: Session, text: str) -> None:
    """Bewaar de ondertekening. Leeg wissen mag: dan eindigt de mail zonder groet."""
    from app.kernel.tenant_config import set_setting

    set_setting(db, "meeting_mail_signature", (text or "").strip() or None)
    db.commit()


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
    for extra in extra_recipients_of(db, meeting):
        if extra.email not in emails:
            emails.append(extra.email)
            names.append(extra.name or extra.email)
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
    meegestuurd = []
    for record in files_of(db, meeting):
        wanted = record.on_agenda_mail if kind == "agenda" else record.on_report_mail
        if wanted:
            attachments.append((record.filename, record.content_type, record.data))
            meegestuurd.append(record)

    send_with_attachments(to_emails=recipients.emails, subject=subject,
                          body_html=body_html, attachments=attachments,
                          reply_to=reply_to, email_type="meeting")

    # Archiveren en stempelen in ÉÉN commit: anders kan een crash ertussen een
    # bewaarde PDF achterlaten bij een vergadering die "niet verstuurd" heet.
    add_file(db, meeting, filename=pdf_filename, content_type="application/pdf",
             data=pdf, purpose=FilePurpose.SENT_PDF, commit=False)
    now = datetime.now(timezone.utc)
    # Per bijlage vastleggen dát ze mee was, en met wélke mail. Zonder dit stempel
    # blijft er van een afgesloten vergadering alleen een aanvinkvakje over, en dat
    # zegt wat iemand van plan was — niet wat de ontvanger gekregen heeft.
    for record in meegestuurd:
        if kind == "agenda":
            record.sent_with_agenda_at = now
        else:
            record.sent_with_report_at = now
    if kind == "agenda":
        meeting.agenda_sent_at = now
        _touch(db, meeting)
    else:
        meeting.report_sent_at = now
        meeting.status = MeetingStatus.SENT
    db.commit()


def reopen(db: Session, meeting: Meeting) -> None:
    """Reopen a sent report for the correction that comes the day after.

    The earlier PDF stays archived; resending adds a second one. History never
    loses a version that went out.
    """
    if meeting.status != MeetingStatus.SENT:
        return
    meeting.status = MeetingStatus.REPORT
    db.commit()


def _refuse_when_sent(meeting: Meeting) -> None:
    if meeting.status == MeetingStatus.SENT:
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
    # De notities als (ontsmette) HTML uit de WYSIWYG-editor.
    notes: str
    kind: str                      # "activity" | "member" | "free"
    source_url: Optional[str]      # where the source chip goes
    is_full: bool
    steward_person_id: Optional[int]
    # De naam erbij, niet alleen het id: het verslag drukt "wijkmeester: Ivo
    # Verwimp" af, en een scherm dat zelf namen gaat opzoeken is een tweede plek
    # waar dezelfde vraag beantwoord wordt.
    steward_name: str = ""
    # The activity behind an activity point (#984). The newsletter's drafting
    # fetches the activity data through it, so the model never has to detect an
    # activity in the note's prose (CR-05 §3.15).
    activity_id: Optional[int] = None


@dataclass(frozen=True)
class DocumentSection:
    id: int
    kind: SectionKind
    label: str
    subtitle: str
    items: list[DocumentItem]
    can_add: bool

    # CR-12 §B4.7: een sjabloon vergelijkt geen code. Deze drie zijn wat de
    # sjablonen echt wilden weten; ze stonden er als `section.kind == "MEMBERS"`
    # en werden stil onwaar toen `kind` een enum werd — zonder dat er iets
    # brak, want een `{% if %}` die niet klopt toont gewoon niets.
    @property
    def is_members(self) -> bool:
        return self.kind is SectionKind.MEMBERS

    @property
    def is_custom(self) -> bool:
        return self.kind is SectionKind.CUSTOM

    @property
    def is_ideas(self) -> bool:
        return self.kind is SectionKind.IDEAS


def document_of(db: Session, meeting: Meeting) -> list[DocumentSection]:
    """The meeting as sections of points, in reading order."""
    from app.domains.activities.api import Activity, registration_counts

    sections = sections_of(db, meeting)
    all_items = {s.id: items_of(db, s) for s in sections}

    activity_ids = [i.activity_id for items in all_items.values() for i in items
                    if i.activity_id]
    activities = {}
    counts = {}
    times = {}
    if activity_ids:
        activities = {a.id: a for a in
                      db.query(Activity).filter(Activity.id.in_(activity_ids)).all()}
        counts = registration_counts(db, activity_ids)
        times = _start_times(db, activity_ids)

    member_ids = [i.member_id for items in all_items.values() for i in items
                  if i.member_id]
    member_labels = _member_labels(db, member_ids)
    steward_names = _person_names(db, [i.noted_steward_person_id
                                       for items in all_items.values() for i in items
                                       if i.noted_steward_person_id])

    out = []
    for section in sections:
        items = [_present(item, activities, counts, member_labels, times,
                          steward_names)
                 for item in all_items[section.id]]
        out.append(DocumentSection(
            id=section.id, kind=section.kind, label=section_label(section),
            subtitle=_subtitle_for(section.kind), items=items,
            can_add=meeting.status != MeetingStatus.SENT))
    return out


def _subtitle_for(kind: str) -> str:
    """One line under a generated heading saying where its content comes from —
    so a board member can tell a query from something somebody typed."""
    if kind == SectionKind.EVALUATION:
        return _("Activiteiten sinds de vorige vergadering, lopende inbegrepen.")
    if kind == SectionKind.UPCOMING:
        return _("Alles wat gepland staat. Laat weg wat nu niets te bespreken heeft.")
    if kind == SectionKind.MEMBERS:
        return _("Nieuwe leden sinds de vorige vergadering, uit het ledenbestand.")
    if kind == SectionKind.IDEAS:
        return _("Overgenomen van de vorige vergadering.")
    return ""


def _start_times(db: Session, activity_ids: list[int]) -> dict[int, object]:
    """Het beginuur van de eerste datumrij per activiteit, of None.

    Het uur hoort op de regel: het bestuur schrijft "maandag 10 augustus 20u
    Miloheem", en zonder uur moet je voor elke activiteit het detailscherm open.
    Uit de eerste datumrij, dezelfde rij waaruit de sorteerdatum komt — anders
    zouden datum en uur bij een reeks uit verschillende rijen kunnen komen.
    """
    from app.domains.activities.api import ActivityDate

    rijen = (db.query(ActivityDate)
             .filter(ActivityDate.activity_id.in_(activity_ids))
             .order_by(ActivityDate.activity_id.asc(),
                       ActivityDate.start_date.asc(), ActivityDate.id.asc())
             .all())
    eerste: dict[int, object] = {}
    for rij in rijen:
        eerste.setdefault(rij.activity_id, rij.start_time)
    return eerste


def _person_names(db: Session, person_ids: list[int]) -> dict[int, str]:
    """Per persoon-id de naam. Leeg wanneer er niets te zoeken valt."""
    from app.domains.mdm.api import Person

    ids = [p for p in person_ids if p]
    if not ids:
        return {}
    return {p.id: f"{p.first_name} {p.last_name}".strip()
            for p in db.query(Person).filter(Person.id.in_(ids)).all()}


def _present(item: MeetingItem, activities: dict, counts: dict,
             member_labels: dict, times: Optional[dict] = None,
             steward_names: Optional[dict] = None) -> DocumentItem:
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
            datum = short_date(item.sort_key)
            from app.domains.meetings.pdf import clock

            uur = clock((times or {}).get(activity.id))
            parts.append(f"{datum} {uur}".strip())
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
            steward_person_id=None, activity_id=activity.id)

    if item.member_id:
        label, address = member_labels.get(item.member_id, (_("Nieuw lid"), ""))
        naam = (steward_names or {}).get(item.noted_steward_person_id or 0, "")
        return DocumentItem(
            id=item.id, label=label, meta=address, notes=item.notes or "",
            kind="member", source_url=f"/admin/leden/gezin/{item.member_id}",
            is_full=False, steward_person_id=item.noted_steward_person_id,
            steward_name=naam)

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


# Hoe ver de kiezer terugkijkt onder "Evaluatie". Een jaar, omdat de reden om
# handmatig toe te voegen juist is dat iets niet automatisch opgepikt werd — en
# het zoekveld maakt een lange lijst hanteerbaar.
@dataclass(frozen=True)
class ReportPoint:
    """A point of a sent report, as the newsletter's drafting reads it (#984)."""

    meeting_id: int
    meeting_date: date
    section: str
    item: DocumentItem


def sent_reports(db: Session, limit: int = 24) -> list[Meeting]:
    """The reports that went out, newest first — what the newsletter composer
    may tick as a whole (Koen, 17 September 2026)."""
    return (db.query(Meeting)
            .filter(Meeting.status == MeetingStatus.SENT)
            .order_by(Meeting.meeting_date.desc(), Meeting.id.desc())
            .limit(limit).all())


def report_points_of(db: Session, meeting_ids) -> list[ReportPoint]:
    """The points of these sent reports, newest meeting first.

    Member points are left out on purpose: a new household is not newsletter
    material, and it would put names and addresses within reach of the model.
    A meeting that is not (or no longer) sent contributes nothing.
    """
    wanted = {int(i) for i in (meeting_ids or [])}
    points: list[ReportPoint] = []
    for meeting in sent_reports(db, limit=200):
        if meeting.id not in wanted:
            continue
        for section in document_of(db, meeting):
            for item in section.items:
                if item.kind == "member":
                    continue
                points.append(ReportPoint(meeting_id=meeting.id,
                                          meeting_date=meeting.meeting_date,
                                          section=section.label, item=item))
    return points


EVALUATION_LOOKBACK = timedelta(days=365)


def addable_activities(db: Session, meeting: Meeting, query: str = "",
                       section_id: Optional[int] = None) -> list:
    """Activities that could still be added to this agenda, per section.

    The picker behind "Punt toevoegen" (§3.19). **What it offers follows the
    section it opens in**, because the two activity sections look in opposite
    directions: under *Evaluatie* you want something that already happened —
    an activity that was not picked up automatically, or one taken off the agenda
    earlier — and under *Volgende activiteiten* you want what is still coming.
    Offering only the future in both (the first build did) made half the picker
    useless: a past activity could never be added back.

    In the free-form sections there is no window to follow, so everything is on
    offer; the search box is what makes that list workable.
    """
    from app.domains.activities.api import activities_active_between, activities_from

    present = {item.activity_id for item in
               db.query(MeetingItem).filter(MeetingItem.meeting_id == meeting.id).all()
               if item.activity_id}
    section = db.get(MeetingSection, section_id) if section_id else None
    kind = getattr(section, "kind", None)

    if kind == SectionKind.EVALUATION:
        # Meest recente eerst: wat je onder evaluatie zoekt, is bijna altijd van
        # de voorbije weken.
        spans = list(reversed(activities_active_between(
            db, meeting.meeting_date - EVALUATION_LOOKBACK, meeting.meeting_date)))
    elif kind == SectionKind.UPCOMING:
        spans = activities_from(db, meeting.meeting_date)
    else:
        spans = list(reversed(activities_active_between(
            db, meeting.meeting_date - EVALUATION_LOOKBACK, meeting.meeting_date)))
        spans += activities_from(db, meeting.meeting_date)

    query = (query or "").strip().lower()
    out = []
    for span in spans:
        if span.activity.id in present:
            continue
        if query and query not in span.activity.name.lower():
            continue
        out.append(span)
    # Géén afkapping (Koen, 16 september 2026). De lijst stond eerst op acht omdat
    # je er anders langs moest scrollen om bij het vrije punt te komen; dat staat
    # nu bovenaan, dus de lengte is geen hindernis meer. En ze is zelfs nuttig:
    # de secretaris loopt bij het opstellen van de agenda alles even langs en
    # beslist wat er besproken moet worden.
    return out


@dataclass(frozen=True)
class Participant:
    """Iemand die bij deze vergadering hoort: uit de kring, of een gast."""

    key: str            # `p<id>` of `g<id>` — personen en gasten tellen apart
    name: str
    person_id: Optional[int]
    guest_id: Optional[int]
    is_guest: bool
    in_circle: bool     # False = stond ooit aangevinkt maar zit niet (meer) in de kring


def participants_of(db: Session, meeting: Meeting) -> list[Participant]:
    """Wie er bij deze vergadering hoort — de kring van dát moment, plus iedereen
    die er al aangevinkt staat.

    Dat tweede deel is geen luxe. De kring is een momentopname: wie hem verlaat,
    krijgt een einddatum, en daarna zou hij uit de lijst van een oud verslag
    verdwijnen terwijl zijn aanwezigheid gewoon in de databank staat. Dan klopt
    het verslag niet meer met wat er die avond gebeurd is — en niemand die het
    leest, kan het zien. Wie er wás, blijft er dus staan.
    """
    from app.domains.mdm.api import Person, organization_circle

    aangevinkt = attendance_of(db, meeting)
    uit = []
    gezien = set()
    for entry in organization_circle(db, on_day=meeting.meeting_date):
        sleutel = f"p{entry.person.id}"
        gezien.add(sleutel)
        uit.append(Participant(
            key=sleutel,
            name=f"{entry.person.first_name} {entry.person.last_name}".strip(),
            person_id=entry.person.id, guest_id=None, is_guest=False,
            in_circle=True))

    # Personen die aangevinkt staan maar niet (meer) in de kring zitten.
    ontbrekend = [int(k[1:]) for k in aangevinkt
                  if k.startswith("p") and k not in gezien]
    if ontbrekend:
        for person in db.query(Person).filter(Person.id.in_(ontbrekend)).all():
            uit.append(Participant(
                key=f"p{person.id}",
                name=f"{person.first_name} {person.last_name}".strip(),
                person_id=person.id, guest_id=None, is_guest=False,
                in_circle=False))

    for gast in extra_recipients_of(db, meeting):
        uit.append(Participant(key=f"g{gast.id}", name=gast.name or gast.email,
                               person_id=None, guest_id=gast.id, is_guest=True,
                               in_circle=True))
    return uit
