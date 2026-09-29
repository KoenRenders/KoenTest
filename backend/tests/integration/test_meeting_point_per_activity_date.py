"""A meeting point is about one date of an activity (#1335).

Koen, entering the meeting of 3 September on PROD: *"We evalueren altijd de voorbije
rit"*, and later *"een activiteit met verschillende data moet je verschillende keren
kunnen selecteren"* — the guide of every coming ride is discussed separately. So the
agenda gets one point per date, the picker offers every date, and a point shows the
begin and end of its date, the same on the screen and in the PDF.

**Proven red** against master `08beaa85` (points per activity, no date), this file
copied onto an export of it with `moment` stubbed so the module loads:
- the evaluation held one point, "5 september 14u", where two rides fell in the window;
- the upcoming section held none: the activity started in the window, so all of it
  sat under evaluation, the three coming rides included;
- the picker returned activities (`'ActivitySpan' object has no attribute 'name'`)
  and offered nothing for the ride beyond the horizon;
- the screen did not show the weekend's end.
`moment` itself did not exist; its cases are new.
"""

from __future__ import annotations

from datetime import date, time

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.meetings.api import (
    MeetingError,
    SectionKind,
    add_item,
    addable_activities,
    create_meeting,
    document_of,
    sections_of,
    update_item,
    update_meeting,
)
from app.domains.meetings.models import MeetingItem
from app.domains.meetings.pdf import moment
from tests.conftest import SEEDED_ADMIN_EMAIL

#: The meeting of these tests. Without a previous meeting the evaluation window is
#: the 31 days before it, [31 August, 1 October); the horizon is 1 January 2027.
MEETING_DAY = date(2026, 10, 1)


def _activity(db, name: str, *rows: tuple) -> Activity:
    """An activity with these date rows: (start, end, start_time, end_time)."""
    activity = Activity(name=name, location="Miloheem")
    db.add(activity)
    db.flush()
    for start, end, start_time, end_time in rows:
        db.add(
            ActivityDate(
                activity_id=activity.id,
                start_date=start,
                end_date=end,
                start_time=start_time,
                end_time=end_time,
            )
        )
    db.flush()
    return activity


def _ride(day: date) -> tuple:
    return (day, None, time(14, 0), time(17, 0))


@pytest.fixture
def monthly_ride(db_session):
    """Two rides in the evaluation window, three within the horizon, one beyond."""
    return _activity(
        db_session,
        "Fietsen (maandelijks)",
        _ride(date(2026, 9, 5)),
        _ride(date(2026, 9, 19)),
        _ride(date(2026, 10, 3)),
        _ride(date(2026, 11, 7)),
        _ride(date(2026, 12, 5)),
        _ride(date(2027, 1, 9)),
    )


def _section(db, meeting, kind: SectionKind):
    return next(s for s in document_of(db, meeting) if s.kind is kind)


def _points(db, meeting, kind: SectionKind, name: str) -> list:
    """The points of one activity: the test database carries seeded activities."""
    return [i for i in _section(db, meeting, kind).items if i.label == name]


def _offered(db, meeting, section, name: str) -> list:
    return [o for o in addable_activities(db, meeting, section_id=section.id) if o.name == name]


def _stored_section(db, meeting, kind: SectionKind):
    return next(s for s in sections_of(db, meeting) if s.kind is kind)


def test_every_ride_in_the_window_is_its_own_evaluation_point(db_session, monthly_ride):
    meeting = create_meeting(db_session, meeting_date=MEETING_DAY)

    evaluation = _points(db_session, meeting, SectionKind.EVALUATION, monthly_ride.name)
    assert [i.meta.split(" · ")[0] for i in evaluation] == [
        "zaterdag 5 september 2026 14u – 17u",
        "zaterdag 19 september 2026 14u – 17u",
    ], "one point per ride that fell since the previous meeting"


def test_every_ride_within_the_horizon_is_its_own_upcoming_point(db_session, monthly_ride):
    meeting = create_meeting(db_session, meeting_date=MEETING_DAY)

    upcoming = _points(db_session, meeting, SectionKind.UPCOMING, monthly_ride.name)
    assert [i.meta.split(" · ")[0] for i in upcoming] == [
        "zaterdag 3 oktober 2026 14u – 17u",
        "zaterdag 7 november 2026 14u – 17u",
        "zaterdag 5 december 2026 14u – 17u",
    ], "the ride of 9 January lies beyond the horizon and stays off"


def test_a_point_with_notes_survives_a_new_build_and_is_not_doubled(db_session, monthly_ride):
    """Moving the meeting rebuilds the agenda; a point somebody wrote on stays, and
    its date does not get a second, empty point next to it."""
    meeting = create_meeting(db_session, meeting_date=MEETING_DAY)
    first = _points(db_session, meeting, SectionKind.UPCOMING, monthly_ride.name)[0]
    update_item(db_session, meeting, first.id, notes="<p>Gids: de voorzitter</p>")

    update_meeting(db_session, meeting, meeting_date=date(2026, 10, 2))

    ride = next(d for d in monthly_ride.dates if d.start_date == date(2026, 10, 3))
    points = db_session.query(MeetingItem).filter_by(
        meeting_id=meeting.id, activity_date_id=ride.id
    )
    assert points.count() == 1, "the ride of 3 October must stay on the agenda once"
    assert "Gids" in points.one().notes


def test_the_picker_offers_every_date_that_is_not_on_the_agenda(db_session, monthly_ride):
    meeting = create_meeting(db_session, meeting_date=MEETING_DAY)
    upcoming = _stored_section(db_session, meeting, SectionKind.UPCOMING)

    offered = _offered(db_session, meeting, upcoming, monthly_ride.name)
    assert [o.moment for o in offered] == ["zaterdag 9 januari 2027 14u – 17u"], (
        "the three rides on the agenda are not offered again; the one beyond the horizon is"
    )

    add_item(db_session, meeting, upcoming, activity_date_id=offered[0].activity_date_id)
    assert _offered(db_session, meeting, upcoming, monthly_ride.name) == []
    assert len(_points(db_session, meeting, SectionKind.UPCOMING, monthly_ride.name)) == 4

    with pytest.raises(MeetingError):
        add_item(db_session, meeting, upcoming, activity_date_id=offered[0].activity_date_id)


def test_a_point_from_before_keeps_its_look_and_hides_no_date(db_session):
    """A point without a date — every point before #1335 — shows the activity as it
    did, and the picker still offers that activity's dates beside it."""
    bbq = _activity(db_session, "Barbecue", (date(2026, 11, 14), None, time(18, 0), None))
    meeting = create_meeting(db_session, meeting_date=date(2026, 12, 1))
    misc = _stored_section(db_session, meeting, SectionKind.MISC)
    for item in db_session.query(MeetingItem).filter_by(meeting_id=meeting.id).all():
        db_session.delete(item)
    db_session.flush()
    db_session.add(
        MeetingItem(
            meeting_id=meeting.id,
            section_id=misc.id,
            activity_id=bbq.id,
            sort_key=date(2026, 11, 14),
        )
    )
    db_session.flush()

    point = _points(db_session, meeting, SectionKind.MISC, "Barbecue")[0]
    assert point.meta.startswith("14 november 18u"), point.meta
    assert [o.moment for o in _offered(db_session, meeting, misc, "Barbecue")] == [
        "zaterdag 14 november 2026 18u"
    ]


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (
            (date(2026, 5, 1), date(2026, 5, 3), time(14, 0), time(17, 0)),
            "vrijdag 1 mei 2026 14u – zondag 3 mei 2026 17u",
        ),
        (
            (date(2026, 8, 20), None, time(19, 0), time(22, 0)),
            "donderdag 20 augustus 2026 19u – 22u",
        ),
        (
            (date(2026, 8, 20), date(2026, 8, 20), time(19, 30), time(22, 0)),
            "donderdag 20 augustus 2026 19u30 – 22u",
        ),
        (
            (date(2026, 6, 1), date(2026, 9, 30), None, None),
            "maandag 1 juni 2026 – woensdag 30 september 2026",
        ),
        ((date(2026, 8, 20), None, None, None), "donderdag 20 augustus 2026"),
        ((date(2026, 8, 20), None, None, time(22, 0)), "donderdag 20 augustus 2026"),
        ((date(2026, 8, 20), None, time(19, 0), None), "donderdag 20 augustus 2026 19u"),
    ],
)
def test_the_moment_shows_what_exists_and_no_loose_dash(row, expected):
    start, end, start_time, end_time = row
    assert moment(start, start_time, end, end_time) == expected


def test_screen_and_pdf_show_the_same_moment(client, db_session):
    """One source for the moment: the screen and the PDF both read `document_of`."""
    from app.domains.meetings.admin_ui import _pdf_context
    from app.ui import templates

    _activity(
        db_session,
        "Weekend in de Ardennen",
        (date(2026, 10, 9), date(2026, 10, 11), time(14, 0), time(17, 0)),
    )
    meeting = create_meeting(db_session, meeting_date=MEETING_DAY)
    expected = "vrijdag 9 oktober 2026 14u – zondag 11 oktober 2026 17u"

    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    screen = client.get(f"/admin/vergaderingen/{meeting.id}")
    assert screen.status_code == 200
    pdf_html = templates.env.get_template("meeting_pdf.html").render(
        **_pdf_context(db_session, meeting, kind="agenda")
    )

    assert expected in screen.text, "the screen shows the weekend's begin and end"
    assert expected in pdf_html, "the PDF shows the same moment"
