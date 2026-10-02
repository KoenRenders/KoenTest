"""An activity's status (draft or published) and its target audience (#1428).

Koen, 1 October 2026: the board makes next year's programme in the app now
(copying, #1397), so an activity needs a draft that stays off the site, and the
spreadsheet's "P" column, who an activity is for.

A draft is in no public place — the agenda, its own page, registering, the
public participant list, the public chatbot, the newsletter — and the board
sees it everywhere it works: its list, its record page, a meeting. Every
activity that existed is published; the audience starts empty.

Proven red against master `cbe40e28` (this file on an export of it): the module
does not even import there — `ActivityStatus` does not exist, so no draft can be
made. A new notion has no older behaviour to assert against.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text as sql

from app.domains.activities.api import (
    Activity,
    ActivityDate,
    ActivityProduct,
    ActivityStatus,
    ActivitySubRegistration,
    activities_from,
)
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, form_guard_fields

pytestmark = pytest.mark.ui_serverrendered

SOON = date.today() + timedelta(days=30)


def _activity(db, name: str, status: ActivityStatus = ActivityStatus.DRAFT) -> Activity:
    activity = Activity(name=name, status=status)
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=SOON))
    component = ActivitySubRegistration(
        activity_id=activity.id, name="Deelname", registration_type_code="INDIVIDUAL"
    )
    db.add(component)
    db.flush()
    db.add(ActivityProduct(component_id=component.id, name="Ticket", is_free=True))
    db.commit()
    return activity


def _board(client) -> str:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def test_a_draft_is_off_the_site_until_it_is_published(client, db_session):
    draft = _activity(db_session, "Bouwen in concept")
    activity_id = draft.id

    assert "Bouwen in concept" not in client.get("/activiteiten").text
    assert client.get(f"/activiteiten/{activity_id}").status_code == 404
    assert "Bouwen in concept" not in client.get("/").text
    assert all(a["id"] != activity_id for a in client.get("/api/v1/activities?scope=all").json())

    csrf = _board(client)
    answer = client.post(
        f"/admin/activiteiten/{activity_id}/status",
        data={"status": "published"},
        headers={"X-CSRF-Token": csrf},
    )
    assert answer.status_code == 204 and answer.headers.get("HX-Refresh") == "true"
    client.cookies.clear()

    assert "Bouwen in concept" in client.get("/activiteiten").text
    assert client.get(f"/activiteiten/{activity_id}").status_code == 200


def test_a_draft_takes_no_registration_from_the_site(client, db_session):
    draft = _activity(db_session, "Inschrijven op concept")
    component = draft.sub_registrations[0]

    page = client.get(f"/activiteiten/{draft.id}/inschrijven/{component.id}")
    assert page.status_code == 404
    participants = client.get(
        f"/api/v1/activities/{draft.id}/public-registrations?component_id={component.id}"
    )
    assert participants.status_code == 404
    answer = client.post(
        f"/api/v1/activities/{draft.id}/register",
        json={
            "component_id": component.id,
            "contact_name": "Iemand",
            "contact_email": "iemand@example.org",
            "phone": "0470000000",
            "items": [{"product_id": component.products[0].id, "quantity": 1}],
            **form_guard_fields(),
        },
    )
    assert answer.status_code in (400, 404), answer.text
    assert "Deze activiteit staat nog niet open." in answer.text or answer.status_code == 404


def test_the_public_chatbot_and_the_newsletter_do_not_know_a_draft_a_meeting_does(db_session):
    from app.domains.chatbot.tools import get_activities, get_activity_detail

    draft = _activity(db_session, "Concept voor Raakje")
    published = _activity(db_session, "Gepubliceerd voor Raakje", ActivityStatus.PUBLISHED)

    names = [a["name"] for a in get_activities(db_session)["activities"]]
    assert "Gepubliceerd voor Raakje" in names and "Concept voor Raakje" not in names
    assert "error" in get_activity_detail(db_session, draft.id)

    letter = {s.activity.id for s in activities_from(db_session, date.today(), published_only=True)}
    meeting = {s.activity.id for s in activities_from(db_session, date.today())}
    assert published.id in letter and draft.id not in letter
    assert {draft.id, published.id} <= meeting, "the board's meeting discusses drafts too"


def test_an_activity_written_without_a_status_is_published_and_has_no_audience(db_session):
    """What the migration does to every activity that existed: the column's
    default is `published`, and the audience stays empty — nothing is guessed."""
    db_session.execute(
        sql(
            "INSERT INTO activities.activities (name, tenant_id, created_at, updated_at) "
            "VALUES ('Van vroeger', 2, now(), now())"
        )
    )
    row = db_session.execute(
        sql("SELECT status, target_audience FROM activities.activities WHERE name = 'Van vroeger'")
    ).one()
    assert (row.status, row.target_audience) == ("published", None)
    labels = db_session.execute(
        sql(
            "SELECT code, value FROM activities.target_audience_labels "
            "WHERE language = 'nl' ORDER BY code"
        )
    ).all()
    assert dict(labels) == {
        "adults": "Volwassenen",
        "children": "Kinderen",
        # #1451: `families` "Gezinnen" became `everyone` "Iedereen".
        "everyone": "Iedereen",
        "men": "Mannen",
        "teens": "Tieners",
        "women": "Vrouwen",
    }


def test_the_copy_step_makes_a_draft_by_default_and_published_on_request(client, db_session):
    source = _activity(db_session, "Kerstherberg", ActivityStatus.PUBLISHED)
    csrf = _board(client)

    def copy(**extra):
        answer = client.post(
            f"/admin/activiteiten/{source.id}/kopieren",
            data={"start_date": (SOON + timedelta(days=364)).isoformat(), **extra},
            headers={"X-CSRF-Token": csrf},
        )
        assert answer.status_code == 204, answer.text[:300]
        db_session.expire_all()
        return db_session.get(Activity, int(answer.headers["HX-Redirect"].rsplit("/", 1)[1]))

    assert copy().status is ActivityStatus.DRAFT
    assert copy(status="published").status is ActivityStatus.PUBLISHED


def test_the_board_sees_the_draft_and_sets_its_audience(client, db_session):
    draft = _activity(db_session, "Wandelen in concept")
    csrf = _board(client)

    cards = client.get("/admin/activiteiten").text
    card = cards[cards.index("Wandelen in concept") :][:1500]
    assert ">Concept<" in card, "the draft carries its badge on the card"

    header = client.get(f"/admin/activiteiten/{draft.id}").text
    assert ">Concept<" in header and ">Publiceren<" in header

    def save(audience: str):
        return client.post(
            f"/admin/activiteiten/{draft.id}",
            data={"name": "Wandelen in concept", "target_audience": audience},
            headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
        )

    save("women")
    db_session.expire_all()
    assert db_session.get(Activity, draft.id).target_audience == "women"
    cards = client.get("/admin/activiteiten").text
    assert ">Vrouwen<" in cards[cards.index("Wandelen in concept") :][:1500]

    refused = save("aliens")
    assert "Onbekend doelpubliek." in refused.text
    db_session.expire_all()
    assert db_session.get(Activity, draft.id).target_audience == "women"


def _header_and_card(client, activity_id: int) -> tuple[str, str]:
    """The title line and the "Status" row of the Publicatie card, as HTML."""
    page = client.get(f"/admin/activiteiten/{activity_id}").text
    header = page[page.index("<h1") : page.index("</h1>")]
    card = page[page.index(">Publicatie<") :]
    row = card[card.index(">Status<") : card.index(">Toegang<")]
    return header, row


def test_a_draft_says_one_status_in_its_header_and_its_card(client, db_session):
    """Found on the 390 px screenshot after part A: a draft read "Concept" and
    "actief" side by side, and "Status: actief" in the Publicatie card — which
    reads as published. "actief" means "not cancelled"; for a draft it goes, and
    the card shows the publication status.

    Red before this change: `">actief<" not in header` failed on the draft.
    """
    draft = _activity(db_session, "Concept met één status")
    published = _activity(db_session, "Gepubliceerd met status", ActivityStatus.PUBLISHED)
    _board(client)

    header, row = _header_and_card(client, draft.id)
    assert ">Concept<" in header and ">actief<" not in header, header
    assert ">Concept<" in row and ">actief<" not in row, row

    header, row = _header_and_card(client, published.id)
    assert ">actief<" in header and ">Concept<" not in header, header
    assert ">Gepubliceerd<" in row, row

    published.is_cancelled = True
    db_session.commit()
    header, row = _header_and_card(client, published.id)
    assert ">geannuleerd<" in header and ">actief<" not in header, header
    assert ">Gepubliceerd<" in row and ">geannuleerd<" in row, row
