"""An organiser's fallback contact is the member's main one (#1695).

Found while building #1694: `member_contacts` took, per contact type, the first
row the query returned — without an order and without looking at the main
contact. For a member with two addresses it was not defined which one the
poster printed, and it could differ between two renders.

Now: the member's main contact of the type; without one, the oldest row (lowest
id). One rule, in `member_contacts`, so the poster, the record and the grey
value of #1694 keep reading the same answer.

On made-up data.

Broken on purpose (7 October 2026): the `order_by` taken out → the main-contact
tests are red (the older row comes first) and the oldest-row test is red too,
because that test writes the row with the higher id first; only `is_primary`
left in the order → the oldest-row test alone is red; only the id left → the
main-contact tests are red.
"""

from __future__ import annotations

import html as html_lib
import re
from datetime import date

import pytest

from app.domains.activities.api import (
    add_organiser,
    member_contacts,
    organisers_for,
    update_organiser,
)
from app.domains.activities.models import Activity
from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.designstudio import service as designstudio
from app.domains.mdm.api import CONTACT, ContactDetail, Member, MemberPerson, Person
from app.kernel.codes import code_of
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _contact(db, person_id, kind, value, *, main=False):
    row = ContactDetail(person_id=person_id, contact_type_code=kind, value=value, is_primary=main)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def organiser(db_session):
    """An activity with one organiser, a member without any contact yet."""
    person = Person(
        date_of_birth=date(1980, 1, 1), gender_code="M", first_name="Twee", last_name="Adressen"
    )
    db_session.add(person)
    db_session.flush()
    household = Member()
    db_session.add(household)
    db_session.flush()
    db_session.add(
        MemberPerson(member_id=household.id, person_id=person.id, relation_type="HOOFDLID")
    )
    activity = Activity(name="Quiz met twee adressen")
    db_session.add(activity)
    db_session.flush()
    row = add_organiser(db_session, activity.id, person.id)
    update_organiser(db_session, activity.id, row.id, {"is_contact": True})
    db_session.flush()
    return activity.id, row.id, person.id


def _fallback(db, activity_id) -> tuple[str, str]:
    [seen] = organisers_for(db, activity_id)
    return seen.email, seen.mobile


def test_the_main_contact_wins_also_when_it_was_added_second(db_session, organiser):
    """Red on master: the first row, "oud@example.com" and 0470000001."""
    activity_id, _row, person_id = organiser
    _contact(db_session, person_id, "EMAIL", "oud@example.com")
    _contact(db_session, person_id, "EMAIL", "hoofd@example.com", main=True)
    _contact(db_session, person_id, "MOBILE", "0470000001")
    _contact(db_session, person_id, "MOBILE", "0470000002", main=True)
    db_session.commit()
    assert _fallback(db_session, activity_id) == ("hoofd@example.com", "0470000002")


def test_the_poster_and_the_grey_field_read_that_same_main_contact(client, db_session, organiser):
    activity_id, row_id, person_id = organiser
    _contact(db_session, person_id, "EMAIL", "oud@example.com")
    _contact(db_session, person_id, "EMAIL", "hoofd@example.com", main=True)
    _contact(db_session, person_id, "MOBILE", "0470000001")
    _contact(db_session, person_id, "MOBILE", "0470000002", main=True)
    db_session.commit()
    [printed] = designstudio._organisers(db_session, activity_id)
    assert (printed.email, printed.mobile) == ("hoofd@example.com", "0470 00 00 02")

    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    page = client.get(f"/admin/activiteiten/{activity_id}?bewerken=1").text
    for field, value in (("email_override", printed.email), ("mobile_override", printed.mobile)):
        [tag] = re.findall(rf'<input[^>]*\bid="o-{row_id}-{field}"[^>]*>', page)
        assert f'placeholder="{html_lib.escape(value)}"' in tag


def test_without_a_main_contact_the_oldest_row_is_taken_every_time(db_session, organiser):
    """The row with the HIGHER id is written first, so in the table the lower
    id stands behind it and a query without an order returns the higher one.
    The rule is the lowest id, not the place in the table."""
    activity_id, _row, person_id = organiser
    newer = ContactDetail(
        id=9_000_000,
        person_id=person_id,
        contact_type_code="EMAIL",
        value="tweede@example.com",
        is_primary=False,
    )
    db_session.add(newer)
    db_session.commit()
    oldest = _contact(db_session, person_id, "EMAIL", "eerste@example.com")
    db_session.commit()
    assert oldest.id < newer.id

    answers = set()
    for _attempt in range(5):
        db_session.expire_all()
        answers.add(_fallback(db_session, activity_id)[0])
    assert answers == {"eerste@example.com"}
    own = member_contacts(db_session, [person_id])
    assert own[(person_id, code_of(CONTACT.EMAIL))] == "eerste@example.com"


def test_a_main_row_without_a_value_does_not_hide_the_one_that_has_one(db_session, organiser):
    activity_id, _row, person_id = organiser
    _contact(db_session, person_id, "MOBILE", "", main=True)
    _contact(db_session, person_id, "MOBILE", "0470000005")
    db_session.commit()
    assert _fallback(db_session, activity_id)[1] == "0470000005"


def test_an_own_value_of_the_activity_still_wins(db_session, organiser):
    activity_id, row_id, person_id = organiser
    _contact(db_session, person_id, "EMAIL", "oud@example.com")
    _contact(db_session, person_id, "EMAIL", "hoofd@example.com", main=True)
    update_organiser(db_session, activity_id, row_id, {"email_override": "quiz@example.com"})
    db_session.commit()
    [seen] = organisers_for(db_session, activity_id)
    assert seen.email == "quiz@example.com"
    assert seen.member_email == "hoofd@example.com", "the grey value stays the member's main one"
