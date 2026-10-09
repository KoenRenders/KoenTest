"""A meeting without a date says why it is refused (#1831).

The meeting form (new and edit, one template) already answers a date that is
none the way a page with one form does: the form again, "Vul een geldige datum
in." in the banner above it. One shape never got that far: an EMPTY date. The
routes required the field, the framework takes an empty text field for a
missing one, and the answer was a bare JSON 422.

Both doors — a new meeting and an existing one — in three shapes: no field, an
empty field, and text that is no date. Each is read as the browser gets it: an
HTML page (a 200; the form is a plain post the shell boosts), the sentence in
the banner, the form again, and nothing written.

Red proof: the routes' `meeting_date` back to `Form(...)` → the "no field" and
"empty" cases of both doors fail on the bare 422.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.meetings.api import Meeting
from tests.conftest import SEEDED_ADMIN_EMAIL

SENTENCE = "Vul een geldige datum in."
SHAPES = pytest.mark.parametrize(
    "given",
    [{}, {"meeting_date": ""}, {"meeting_date": "morgen"}],
    ids=["no date field", "an empty date", "text that is no date"],
)


def _board(client) -> dict[str, str]:
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return {"X-CSRF-Token": csrf_token_for(session)}


def _banner(html: str) -> str:
    found = re.search(r'<div class="[^"]*bg-red-50[^"]*" role="alert">(.*?)</div>', html, re.S)
    assert found, "the answer carries no banner"
    return found.group(1).strip()


@SHAPES
def test_a_new_meeting_without_a_date_says_so(client, db_session, given):
    headers = _board(client)
    before = db_session.query(Meeting).count()

    answer = client.post(
        "/admin/vergaderingen",
        data={"location": "Zaal", **given},
        headers=headers,
        follow_redirects=False,
    )

    assert answer.status_code == 200, answer.text[:200]
    assert answer.headers["content-type"].startswith("text/html")
    assert _banner(answer.text) == SENTENCE
    assert 'action="/admin/vergaderingen"' in answer.text
    db_session.expire_all()
    assert db_session.query(Meeting).count() == before


@SHAPES
def test_an_existing_meeting_keeps_its_date_and_says_so(client, db_session, given):
    headers = _board(client)
    made = client.post(
        "/admin/vergaderingen",
        data={"meeting_date": "2027-03-04", "location": "Zaal"},
        headers=headers,
        follow_redirects=False,
    )
    assert made.status_code == 303
    meeting_id = int(made.headers["location"].rsplit("/", 1)[1])

    answer = client.post(
        f"/admin/vergaderingen/{meeting_id}/bewerken",
        data={"location": "Elders", **given},
        headers=headers,
        follow_redirects=False,
    )

    assert answer.status_code == 200, answer.text[:200]
    assert _banner(answer.text) == SENTENCE
    assert f'action="/admin/vergaderingen/{meeting_id}/bewerken"' in answer.text
    db_session.expire_all()
    meeting = db_session.get(Meeting, meeting_id)
    assert meeting.meeting_date == date(2027, 3, 4)
    assert meeting.location == "Zaal", "the refused change was written all the same"
