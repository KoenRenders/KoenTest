"""CR-11 phase 1 (#1391): the quick wins on meetings and the newsletter.

W4: the meetings list has "Instellingen" in its header instead of
"Vergaderkring", and no second link to the circle under the list; the page
behind it is titled "Instellingen".
W6: a meeting row shows its status once, as the badge from the code list.
W7: a button that opens a step ends in "…"; the last button of the newsletter
names its consequence ("Verstuur naar N abonnees"); the card "Zo vertrekt hij"
is on the send page, not in the editor.

W13 (the reports in Raakje's panel) is covered in `test_nieuwsbrief_raakje.py`.

Proven red against master `eee37a9d` (this file on an export of it): every test
failed on the old markup: two links to the circle, "agenda verstuurd" beside
the badge, "Verstuur agenda" and "Versturen (1)", and the card in the editor.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.meetings.api import MeetingStatus, create_meeting
from app.domains.newsletter import service as nb
from app.domains.newsletter.models import Audience, Subscriber, SubscriberStatus
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client) -> None:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    csrf_token_for(value)


def test_w4_the_settings_are_linked_once_in_the_header(client, db_session):
    _login(client)

    html = client.get("/admin/vergaderingen").text

    links = re.findall(r'href="/admin/vergaderingen/kring"', html)
    assert len(links) == 1, f"one link to the circle page, found {len(links)}"
    assert re.search(r'href="/admin/vergaderingen/kring"[^>]*>\s*(<[^>]+>\s*)*Instellingen', html)
    assert "Beheer de kring" not in html and "Vergaderkring" not in html

    page = client.get("/admin/vergaderingen/kring").text
    assert re.search(r"<h1[^>]*>\s*Instellingen\s*</h1>", page), "the page is titled Instellingen"
    assert "In de kring" in page, "the circle stays as a section"


def test_w6_a_meeting_row_shows_its_status_once(client, db_session):
    meeting = create_meeting(db_session, meeting_date=date.today() - timedelta(days=3))
    meeting.status = MeetingStatus.SENT
    meeting.agenda_sent_at = datetime.now(timezone.utc) - timedelta(days=5)
    meeting.report_sent_at = datetime.now(timezone.utc)
    db_session.commit()
    _login(client)

    html = client.get("/admin/vergaderingen").text

    row = re.search(rf'<a href="/admin/vergaderingen/{meeting.id}".*?</a>', html, re.S)
    assert row, "the meeting's row is in the list"
    text = row.group(0).lower()
    assert text.count("verslag verstuurd") == 1, "the status once, as the badge"
    assert "agenda verstuurd" not in text


def test_w7_the_meeting_buttons_that_open_a_step_end_in_an_ellipsis(client, db_session):
    meeting = create_meeting(db_session, meeting_date=date.today() + timedelta(days=7))
    db_session.commit()
    _login(client)

    html = client.get(f"/admin/vergaderingen/{meeting.id}").text

    assert "Agenda versturen…" in html and "Verslag versturen…" in html
    assert "Verstuur agenda<" not in html and "Verstuur verslag<" not in html


def test_w7_the_last_newsletter_button_names_its_consequence(client, db_session):
    for n in range(2):
        db_session.add(
            Subscriber(
                email=f"lezer{n}@example.org",
                status=SubscriberStatus.CONFIRMED,
                source="admin",
                unsubscribe_token=f"w7-{n}",
            )
        )
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    nb.update_draft(
        db_session,
        letter,
        subject="Het najaar",
        body_html="<div>Tot binnenkort.</div>",
        audience=Audience.NON_MEMBERS,
    )
    _login(client)

    step = client.get(f"/admin/nieuwsbrieven/{letter.id}/versturen").text
    editor = client.get(f"/admin/nieuwsbrieven/{letter.id}").text

    assert "Verstuur naar 2 abonnees" in step
    assert "Versturen (" not in step
    assert "Zo vertrekt hij" in step, "the card is where the letter leaves"
    assert "Zo vertrekt hij" not in editor, "and no longer in the editor"
    assert "Versturen…" in editor, "the editor's button opens the step"
