"""The title of a free agenda point can be changed on the meeting screen (#1359).

Koen, 29 September 2026: a typo in a free point meant deleting it, adding it again
and retyping its notes. `update_item` could take a title and the route passed one
on, but no template offered a field. A free point now has a pencil that opens the
title in place; a point linked to an activity or a household has none, its name
comes from the source. An empty title is refused in the service, with the reason in
the point.

Proven red against master `ae660424`, this file copied onto an export of it: all
four failed — the title was stored untrimmed, the screen had no field, an empty
title was accepted, and a linked point's title could be changed.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.meetings.api import (
    MeetingError,
    SectionKind,
    add_item,
    create_meeting,
    document_of,
    sections_of,
    update_item,
)
from app.domains.meetings.models import MeetingItem
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

MEETING_DAY = date(2026, 10, 1)


def _login(client) -> dict:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _misc(db, meeting):
    return next(s for s in sections_of(db, meeting) if s.kind is SectionKind.MISC)


def _free_point(db, meeting, title: str = "Tentn opbouwen", notes: str = "<p>Jan</p>"):
    item = add_item(db, meeting, _misc(db, meeting), title=title)
    update_item(db, meeting, item.id, notes=notes)
    return item


def _point_html(html: str, item_id: int) -> str:
    """The markup of one point, up to the next point or the end."""
    start = html.index(f'id="vg-punt-{item_id}"')
    nxt = html.find('id="vg-punt-', start + 10)
    return html[start : nxt if nxt != -1 else len(html)]


def test_the_new_title_shows_on_screen_and_in_the_pdf(client, db_session):
    from app.domains.meetings.admin_ui import _pdf_context
    from app.ui import templates

    headers = _login(client)
    meeting = create_meeting(db_session, meeting_date=MEETING_DAY)
    item = _free_point(db_session, meeting)

    answer = client.post(
        f"/admin/vergaderingen/{meeting.id}/punt/{item.id}",
        data={"title": "  Tenten opbouwen  "},
        headers=headers,
    )

    assert answer.status_code == 200, answer.text[:200]
    assert "Tenten opbouwen" in answer.text, "the point comes back with its new title"
    db_session.expire_all()
    stored = db_session.get(MeetingItem, item.id)
    assert stored.title == "Tenten opbouwen", "trimmed"
    assert stored.notes == "<p>Jan</p>", "the notes are left alone"
    pdf = templates.env.get_template("meeting_pdf.html").render(
        **_pdf_context(db_session, meeting, kind="agenda")
    )
    assert "Tenten opbouwen" in pdf and "Tentn opbouwen" not in pdf


def test_the_screen_offers_the_title_field_on_a_free_point(client, db_session):
    _login(client)
    meeting = create_meeting(db_session, meeting_date=MEETING_DAY)
    item = _free_point(db_session, meeting)

    point = _point_html(client.get(f"/admin/vergaderingen/{meeting.id}").text, item.id)

    assert re.search(r'name="title"[^>]*value="Tentn opbouwen"', point), "the field is there"
    assert 'aria-label="Titel van het punt wijzigen"' in point


def test_an_empty_title_is_refused_with_the_reason_in_the_point(client, db_session):
    headers = _login(client)
    meeting = create_meeting(db_session, meeting_date=MEETING_DAY)
    item = _free_point(db_session, meeting)

    answer = client.post(
        f"/admin/vergaderingen/{meeting.id}/punt/{item.id}",
        data={"title": "   "},
        headers=headers,
    )

    assert answer.status_code == 200
    assert "Een vrij punt heeft een titel nodig." in answer.text
    assert answer.text.lstrip().find('id="vg-punt-') != -1, "the point, not the whole document"
    assert 'id="vg-document"' not in answer.text
    db_session.expire_all()
    assert db_session.get(MeetingItem, item.id).title == "Tentn opbouwen"


def test_an_activity_point_has_no_title_field(client, db_session):
    _login(client)
    activity = Activity(name="Quizavond", location="Miloheem")
    db_session.add(activity)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=activity.id, start_date=date(2026, 10, 17)))
    db_session.flush()
    meeting = create_meeting(db_session, meeting_date=MEETING_DAY)
    point = next(
        i
        for s in document_of(db_session, meeting)
        if s.kind is SectionKind.UPCOMING
        for i in s.items
        if i.label == "Quizavond"
    )

    html = _point_html(client.get(f"/admin/vergaderingen/{meeting.id}").text, point.id)
    assert 'name="title"' not in html, "a linked point takes its name from the source"
    with pytest.raises(MeetingError):
        update_item(db_session, meeting, point.id, title="Iets anders")
