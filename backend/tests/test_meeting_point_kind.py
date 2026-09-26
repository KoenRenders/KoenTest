"""What the kind of a meeting point decides (CR-12 phase 4).

A point comes from an activity, from a new member, or from nobody (a free
point). The kind is stored nowhere — it follows from which source the row has
— so it is not a code list but two flags on the document item. Three things
hang on it:

- the source chip: "activiteit" or "lid", and "vrij punt" when there is no source;
- the steward choice, which only a member point offers;
- the newsletter, which never gets a member point (names and addresses).

These tests describe master's behaviour (v2.6.0, where the kind was the
string "activity" / "member" / "free") and were run there first, green. They
were written because swapping the two flags on the activity point broke no
existing test: the kind was nowhere covered.

Broken on purpose to check that these tests can go red: the activity point
built with `is_activity=False, is_member=True` → the chip test and the
newsletter test fall over.
"""
import re
from datetime import date

import pytest
from sqlalchemy import text

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.meetings.api import (
    MeetingItem,
    add_item,
    create_meeting,
    report_points_of,
    sections_of,
)
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family

pytestmark = pytest.mark.ui_serverrendered


@pytest.fixture
def meeting_with_three_kinds(db_session):
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    # By stored code, so the same test runs on master, where the kind was a
    # plain string, and here, where it is a `SectionKind` member.
    sections = {getattr(s.kind, "value", s.kind): s for s in sections_of(db_session, meeting)}

    activity = Activity(name="Proefactiviteit", location="Zaal")
    db_session.add(activity)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=activity.id, start_date=date(2026, 10, 5)))
    db_session.flush()
    activity_point = add_item(db_session, meeting, sections["UPCOMING"],
                              activity_id=activity.id)
    free_point = add_item(db_session, meeting, sections["MISC"],
                          title="Een vrij punt")
    member_point = _member_point(db_session, meeting, sections["MEMBERS"])
    db_session.flush()
    return meeting, {"activity": activity_point.id, "free": free_point.id,
                     "member": member_point.id}


def _member_point(db, meeting, section):
    member, _person = create_test_family(db, email="punt@example.org")
    item = MeetingItem(meeting_id=meeting.id, section_id=section.id, position=0,
                       member_id=member.id)
    db.add(item)
    db.flush()
    return item


def _chip(block: str):
    """The word of the source chip: the text after its icon, up to `</a>`."""
    m = re.search(r"</svg>\s*([^<]+?)\s*</a>", block)
    return m.group(1) if m else None


def _steward_form(block: str) -> bool:
    return bool(re.search(r'<form[^>]*hx-trigger="change"', block))


def _block(html: str, item_id: int) -> str:
    start = html.index(f'id="vg-punt-{item_id}"')
    end = html.find('id="vg-punt-', start + 1)
    return html[start:end if end != -1 else len(html)]


def test_the_source_chip_and_the_steward_choice_follow_the_kind(
        client, db_session, meeting_with_three_kinds):
    meeting, ids = meeting_with_three_kinds
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    html = client.get(f"/admin/vergaderingen/{meeting.id}").text

    activity, member, free = (_block(html, ids[k]) for k in ("activity", "member", "free"))
    assert _chip(activity) == "activiteit"
    assert _chip(member) == "lid"
    assert "vrij punt" in free and _chip(free) is None
    # The steward choice saves on `change`; the notes form of every point posts
    # to the same URL but on `trix-blur`, so the trigger is what tells them apart.
    assert _steward_form(member), "a member point offers the steward"
    assert not _steward_form(activity) and not _steward_form(free)


def test_the_newsletter_never_gets_a_member_point(db_session, meeting_with_three_kinds):
    meeting, ids = meeting_with_three_kinds
    db_session.execute(text("UPDATE meetings.meetings SET status = 'sent' WHERE id = :i"),
                       {"i": meeting.id})
    db_session.expire_all()

    points = {p.item.id for p in report_points_of(db_session, [meeting.id])}
    assert ids["activity"] in points and ids["free"] in points
    assert ids["member"] not in points
