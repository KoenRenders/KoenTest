"""A refused meeting form comes back with what was typed, in every field (#1860).

Follow-up of #1831. A form refused for its date came back with the sentence in
its banner and with the suggestion — the previous meeting's time and place on a
new one, the stored values on an existing one — instead of what had just been
typed. One change serves both doors (new and edit, one template).

One route case per door: a time and a place are posted with a date that is no
date, and the answered form is read back. The suggestion differs from the typed
values on purpose, so a form that shows the suggestion cannot pass.

Red proof (14 October 2026, each put back): `typed=` taken out of the refused
answer of `meeting_create` -> the new-meeting case fails on the previous meeting's
time; the same on `meeting_edit_save` -> the edit case fails on the stored time.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.meetings.api import Meeting
from tests.conftest import SEEDED_ADMIN_EMAIL

TYPED = {"meeting_date": "morgen", "start_time": "19:30", "location": "Gemeentezaal"}


def _board(client) -> dict[str, str]:
    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    return {"X-CSRF-Token": csrf_token_for(session)}


def _value_of(html: str, field_id: str) -> str | None:
    tag = re.search(rf'<input[^>]*id="{field_id}"[^>]*>', html)
    assert tag, f"the answered form has no field {field_id}"
    value = re.search(r'value="([^"]*)"', tag.group(0))
    return value.group(1) if value else None


def _made(client, headers, day: date, time: str, place: str) -> int:
    made = client.post(
        "/admin/vergaderingen",
        data={"meeting_date": day.isoformat(), "start_time": time, "location": place},
        headers=headers,
        follow_redirects=False,
    )
    assert made.status_code == 303, made.text[:200]
    return int(made.headers["location"].rsplit("/", 1)[1])


def test_a_refused_new_meeting_comes_back_with_what_was_typed(client, db_session):
    headers = _board(client)
    previous = _made(client, headers, date.today() - timedelta(days=30), "10:15", "Oude plek")
    # "Previous" is the last meeting whose report went out (`previous_meeting`).
    db_session.get(Meeting, previous).report_sent_at = datetime.now(timezone.utc)
    db_session.commit()

    suggested = client.get("/admin/vergaderingen/nieuw").text
    assert _value_of(suggested, "vg-uur") == "10:15", "the suggestion is not the previous meeting's"

    answer = client.post(
        "/admin/vergaderingen", data=TYPED, headers=headers, follow_redirects=False
    )

    assert answer.status_code == 200, answer.text[:200]
    assert "Vul een geldige datum in." in answer.text
    assert _value_of(answer.text, "vg-uur") == "19:30"
    assert _value_of(answer.text, "vg-locatie") == "Gemeentezaal"
    assert _value_of(answer.text, "vg-datum") == "morgen"


def test_a_refused_edit_comes_back_with_what_was_typed(client, db_session):
    headers = _board(client)
    meeting_id = _made(client, headers, date(2027, 3, 4), "18:00", "Zaal")

    answer = client.post(
        f"/admin/vergaderingen/{meeting_id}/bewerken",
        data=TYPED,
        headers=headers,
        follow_redirects=False,
    )

    assert answer.status_code == 200, answer.text[:200]
    assert "Vul een geldige datum in." in answer.text
    assert _value_of(answer.text, "vg-uur") == "19:30"
    assert _value_of(answer.text, "vg-locatie") == "Gemeentezaal"
    assert _value_of(answer.text, "vg-datum") == "morgen"
