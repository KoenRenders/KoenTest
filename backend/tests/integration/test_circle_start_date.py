"""The start date of a circle relation: chosen, changed, and explained (#1346).

A meeting uses the circle as it stood on its own date. Until #1346 a relation
always started on the day it was added, so a meeting entered afterwards — the
first meeting on PROD — had an empty attendance list and a report that went to
nobody, and nothing on the screen said why.

**Proven red** against master `3bfd3506`: this file copied onto an export of it,
`circle_gap` stubbed to "" so the module loads. Seven of eight failed:
- the circle screen ignored `start_date`: a person added "since 1 September" was
  not in the meeting of 3 September (`'Vroeg Kringlid' in set()`);
- `/kring/{id}/start` did not exist (404, twice);
- a start after the end was stored: no `MasterDataError`, no `IntegrityError`;
- taking out someone who starts in ten days ended the relation today, before
  its start;
- nothing said why the circle of the meeting's date was empty.
The eighth, in and out on the same day, passes on master as it must: it guards
that the new rule is `<=`, not `<`.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import (
    ContactDetail,
    MasterDataError,
    Organization,
    OrganizationPerson,
    Person,
    end_circle_relation,
    organization_circle,
)
from app.domains.meetings.api import (
    circle_gap,
    create_meeting,
    participants_of,
    recipients_for,
)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

MEETING_DAY = date(2026, 9, 3)
GAP_ON_DATE = "Op de vergaderdatum zat niemand in de kring."


def _login(client) -> dict:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _empty_circle(db) -> None:
    """The test database may carry circle rows; these tests need a known circle."""
    for relation in db.query(OrganizationPerson).all():
        db.delete(relation)
    db.flush()


def _person(db, first: str, last: str) -> Person:
    person = Person(first_name=first, last_name=last)
    db.add(person)
    db.flush()
    db.add(
        ContactDetail(
            person_id=person.id,
            contact_type_code="EMAIL",
            value=f"{first.lower()}@example.org",
            is_primary=True,
        )
    )
    db.flush()
    return person


def _relation_of(db, person: Person) -> OrganizationPerson:
    return db.query(OrganizationPerson).filter_by(person_id=person.id).one()


def test_a_start_before_the_meeting_puts_the_person_in_it(client, db_session):
    """Added "since 1 September" through the screen: in the attendance list and
    among the recipients of the meeting of 3 September. Added "today": not."""
    _empty_circle(db_session)
    headers = _login(client)
    early = _person(db_session, "Vroeg", "Kringlid")
    late = _person(db_session, "Laat", "Kringlid")
    meeting = create_meeting(db_session, meeting_date=MEETING_DAY)

    for person, start in ((early, "2026-09-01"), (late, date.today().isoformat())):
        answer = client.post(
            "/admin/vergaderingen/kring",
            data={"person_id": person.id, "start_date": start},
            headers=headers,
        )
        assert answer.status_code == 200, answer.text[:200]

    names = {p.name for p in participants_of(db_session, meeting)}
    assert "Vroeg Kringlid" in names, "added since 1 September, so present on 3 September"
    assert "Laat Kringlid" not in names, "added today, so not in a meeting of September"
    assert recipients_for(db_session, meeting).emails == ["vroeg@example.org"]


def test_the_start_date_can_be_changed_afterwards(client, db_session):
    _empty_circle(db_session)
    headers = _login(client)
    person = _person(db_session, "Later", "Aangepast")
    meeting = create_meeting(db_session, meeting_date=MEETING_DAY)
    client.post("/admin/vergaderingen/kring", data={"person_id": person.id}, headers=headers)
    relation = _relation_of(db_session, person)
    assert relation.start_date == date.today(), "no start date given: today"
    assert participants_of(db_session, meeting) == []

    answer = client.post(
        f"/admin/vergaderingen/kring/{relation.id}/start",
        data={"start_date": "2026-08-15"},
        headers=headers,
    )
    assert answer.status_code == 200, answer.text[:200]
    assert _relation_of(db_session, person).start_date == date(2026, 8, 15)
    assert [p.name for p in participants_of(db_session, meeting)] == ["Later Aangepast"]
    assert 'value="2026-08-15"' in answer.text, "the screen shows the new start date"


def test_a_start_after_the_end_is_refused_with_the_reason_on_the_screen(client, db_session):
    _empty_circle(db_session)
    headers = _login(client)
    person = _person(db_session, "Weg", "Gegaan")
    organization = db_session.query(Organization).first()
    relation = OrganizationPerson(
        person_id=person.id,
        organization_id=organization.id,
        relation_type="BOARD_MEETING",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 1),
    )
    db_session.add(relation)
    db_session.flush()

    answer = client.post(
        f"/admin/vergaderingen/kring/{relation.id}/start",
        data={"start_date": "2026-07-01"},
        headers=headers,
    )
    assert answer.status_code == 200
    assert "De startdatum kan niet na de einddatum liggen (01-06-2026)." in answer.text
    db_session.expire_all()
    assert _relation_of(db_session, person).start_date == date(2026, 1, 1), "left unchanged"


def test_the_object_refuses_a_start_after_the_end(db_session):
    person = _person(db_session, "Object", "Regel")
    organization = db_session.query(Organization).first()
    db_session.add(
        OrganizationPerson(
            person_id=person.id,
            organization_id=organization.id,
            relation_type="BOARD_MEETING",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 6, 1),
        )
    )
    with pytest.raises(MasterDataError):
        db_session.flush()


def test_the_database_refuses_it_too(db_session):
    """At rest: a bulk update that bypasses the object meets the CHECK."""
    from sqlalchemy import text

    person = _person(db_session, "Databank", "Regel")
    organization = db_session.query(Organization).first()
    relation = OrganizationPerson(
        person_id=person.id,
        organization_id=organization.id,
        relation_type="BOARD_MEETING",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 1),
    )
    db_session.add(relation)
    db_session.flush()
    with pytest.raises(IntegrityError, match="ck_organization_persons_period"):
        db_session.execute(
            text("UPDATE mdm.organization_persons SET start_date = '2026-07-01' WHERE id = :id"),
            {"id": relation.id},
        )


def test_the_same_day_in_and_out_is_allowed(db_session):
    """`<=`, not `<`: added and taken out again on the same day."""
    person = _person(db_session, "Zelfde", "Dag")
    organization = db_session.query(Organization).first()
    db_session.add(
        OrganizationPerson(
            person_id=person.id,
            organization_id=organization.id,
            relation_type="BOARD_MEETING",
            start_date=date.today(),
            end_date=date.today(),
        )
    )
    db_session.flush()


def test_taking_out_someone_who_has_not_started_yet_ends_on_the_start(db_session):
    """A start in the future is possible now; ending today would precede it."""
    person = _person(db_session, "Nog", "Niet")
    organization = db_session.query(Organization).first()
    start = date.today() + timedelta(days=10)
    relation = OrganizationPerson(
        person_id=person.id,
        organization_id=organization.id,
        relation_type="BOARD_MEETING",
        start_date=start,
    )
    db_session.add(relation)
    db_session.flush()

    end_circle_relation(db_session, relation.id)

    assert _relation_of(db_session, person).end_date == start


def test_the_card_and_the_send_screen_say_why_the_circle_is_empty(client, db_session):
    """Two cases, one source: empty today, or only empty on the meeting's date."""
    _empty_circle(db_session)
    headers = _login(client)
    meeting = create_meeting(db_session, meeting_date=MEETING_DAY)

    assert circle_gap(db_session, meeting) == "De vergaderkring is nog leeg."
    page = client.get(f"/admin/vergaderingen/{meeting.id}").text
    assert "De vergaderkring is nog leeg." in page and GAP_ON_DATE not in page

    person = _person(db_session, "Vandaag", "Toegevoegd")
    client.post("/admin/vergaderingen/kring", data={"person_id": person.id}, headers=headers)
    assert organization_circle(db_session), "the circle of today has someone"

    assert circle_gap(db_session, meeting).startswith(GAP_ON_DATE)
    page = client.get(f"/admin/vergaderingen/{meeting.id}").text
    assert GAP_ON_DATE in page, "the attendance card names the meeting's date"
    send = client.get(f"/admin/vergaderingen/{meeting.id}/verstuur?kind=verslag").text
    assert GAP_ON_DATE in send, "the send screen says it before sending"
    assert "/admin/vergaderingen/kring" in send

    # And once the start date is right, the explanation is gone.
    relation = _relation_of(db_session, person)
    client.post(
        f"/admin/vergaderingen/kring/{relation.id}/start",
        data={"start_date": "2026-09-01"},
        headers=headers,
    )
    assert circle_gap(db_session, meeting) == ""
    assert GAP_ON_DATE not in client.get(f"/admin/vergaderingen/{meeting.id}/verstuur").text
