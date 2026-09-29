"""The note on an upcoming activity goes along to the next agenda (#1355).

Koen, 29 September 2026: an arrangement noted at a coming activity ("Jan zorgt
voor de tent") was missing from the next agenda, and the secretary retyped it. He
chose *copying*: the previous note becomes the starting value of the new point.
CR-09 decision 6 changed with it.

Matched on the activity DATE, only from "Volgende activiteiten" to "Volgende
activiteiten". A date that has passed lands under "Evaluatie" without a note.

Proven red against `541d624a` (#1354, the branch this one stands on; master does not
have #1354 yet): the same date got an empty point (`[''] == ['<p>Jan zorgt …']`).
The other four guard the edges and pass there too, so each was proven with an
added violation, run and restored:
- passing the notes to "Evaluatie" as well → the evaluation test fails;
- matching on the activity instead of the date → the other-date test fails.
The rebuild test and the dateless test guard what must not change.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from app.domains.activities.api import Activity, ActivityDate
from app.domains.meetings.api import (
    MeetingStatus,
    SectionKind,
    create_meeting,
    document_of,
    previous_meeting,
    sections_of,
    update_item,
    update_meeting,
)
from app.domains.meetings.models import MeetingItem

NOTE = "<p>Jan zorgt voor de tent</p>"


def _activity(db, name: str, *days: date) -> Activity:
    activity = Activity(name=name, location="Miloheem")
    db.add(activity)
    db.flush()
    for day in days:
        db.add(ActivityDate(activity_id=activity.id, start_date=day, start_time=time(14, 0)))
    db.flush()
    return activity


def _points(db, meeting, kind: SectionKind, name: str) -> list:
    section = next(s for s in document_of(db, meeting) if s.kind is kind)
    return [i for i in section.items if i.label == name]


def _note_upcoming(db, meeting, name: str, note: str = NOTE) -> None:
    point = _points(db, meeting, SectionKind.UPCOMING, name)[0]
    update_item(db, meeting, point.id, notes=note)


def _send(db, meeting) -> None:
    """ "Previous" is the last meeting whose report went out (`previous_meeting`)."""
    meeting.report_sent_at = datetime.now(timezone.utc)
    meeting.status = MeetingStatus.SENT
    db.flush()


def _second(db, first, day: date):
    """The next meeting — asserting it sees `first` as its previous one, so a
    test cannot pass for want of a previous meeting."""
    _send(db, first)
    assert previous_meeting(db, day).id == first.id
    return create_meeting(db, meeting_date=day)


def test_the_note_of_the_same_date_is_copied(db_session):
    _activity(db_session, "Tentenkamp", date(2026, 11, 14))
    first = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    _note_upcoming(db_session, first, "Tentenkamp")

    second = _second(db_session, first, date(2026, 11, 5))

    points = _points(db_session, second, SectionKind.UPCOMING, "Tentenkamp")
    assert [p.notes for p in points] == [NOTE], "the note comes along as a starting value"
    stored = db_session.get(MeetingItem, points[0].id)
    assert stored.carried_over_from is not None, "and says where it came from"


def test_another_date_of_the_same_activity_does_not_take_the_note(db_session):
    """A monthly ride: the note of the October ride stays with October."""
    _activity(
        db_session, "Fietsen (maandelijks)", date(2026, 10, 3), date(2026, 11, 7), date(2026, 12, 5)
    )
    first = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    _note_upcoming(db_session, first, "Fietsen (maandelijks)")

    second = _second(db_session, first, date(2026, 10, 29))

    upcoming = _points(db_session, second, SectionKind.UPCOMING, "Fietsen (maandelijks)")
    assert [p.meta.split(" · ")[0] for p in upcoming] == ["zaterdag 7 november 2026 14u"]
    assert [p.notes for p in upcoming] == [""], "November does not take October's note"


def test_a_date_that_has_passed_lands_under_evaluation_without_a_note(db_session):
    """Koen's choice: only "Volgende activiteiten" takes notes over."""
    _activity(db_session, "Quiz", date(2026, 10, 17))
    first = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    _note_upcoming(db_session, first, "Quiz")

    second = _second(db_session, first, date(2026, 11, 5))

    evaluation = _points(db_session, second, SectionKind.EVALUATION, "Quiz")
    assert [p.notes for p in evaluation] == [""], "evaluated, but without the old note"
    assert _points(db_session, second, SectionKind.UPCOMING, "Quiz") == []


def test_rebuilding_neither_doubles_nor_overwrites(db_session):
    _activity(db_session, "Tentenkamp", date(2026, 11, 14))
    first = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    _note_upcoming(db_session, first, "Tentenkamp")
    second = _second(db_session, first, date(2026, 11, 5))
    _note_upcoming(db_session, second, "Tentenkamp", "<p>Aangepast</p>")

    update_meeting(db_session, second, meeting_date=date(2026, 11, 6))

    points = _points(db_session, second, SectionKind.UPCOMING, "Tentenkamp")
    assert [p.notes for p in points] == ["<p>Aangepast</p>"], "one point, the edited note"


def test_a_point_without_a_date_takes_no_part(db_session):
    """Points from before #1335 carry no date: ignored, and no error."""
    activity = _activity(db_session, "Tentenkamp", date(2026, 11, 14))
    first = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    upcoming = next(s for s in sections_of(db_session, first) if s.kind is SectionKind.UPCOMING)
    for item in db_session.query(MeetingItem).filter_by(meeting_id=first.id).all():
        db_session.delete(item)
    db_session.add(
        MeetingItem(
            meeting_id=first.id,
            section_id=upcoming.id,
            activity_id=activity.id,
            sort_key=date(2026, 11, 14),
            notes=NOTE,
        )
    )
    db_session.flush()

    second = _second(db_session, first, date(2026, 11, 5))

    assert [p.notes for p in _points(db_session, second, SectionKind.UPCOMING, "Tentenkamp")] == [
        ""
    ]
