"""The person search shows the address the mails would go to (#1353).

Koen, building the meeting circle on PROD: two persons share a first and a last
name, each with a different address, and "Iemand toevoegen" showed only the name.
Which one you picked showed only once they were in the circle — and taking them
out leaves an ended relation behind.

`mdm.search_persons` now returns each person with `_email_of`, the address the
circle itself mails, or None. Both screens that use it show it: the circle's
"Iemand toevoegen" and the organiser picker of an activity (CR-10).

Proven red against master `a4e84c84`, this file copied onto an export of it: all
three failed — `'Person' object has no attribute 'email'`, and both screens showed
the name without an address.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.mdm.api import ContactDetail, Member, MemberPerson, Person, search_persons
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _person(db, first: str, last: str, email: str | None, *, member: bool = True) -> Person:
    person = Person(
        first_name=first, last_name=last, date_of_birth=date(1980, 1, 1), gender_code="M"
    )
    db.add(person)
    db.flush()
    if email:
        db.add(
            ContactDetail(
                person_id=person.id, contact_type_code="EMAIL", value=email, is_primary=True
            )
        )
    if member:
        household = Member()
        db.add(household)
        db.flush()
        db.add(MemberPerson(member_id=household.id, person_id=person.id, relation_type="HOOFDLID"))
    db.flush()
    return person


@pytest.fixture
def namesakes(db_session):
    return (
        _person(db_session, "Lieve", "Tweelingnaam", "lieve.een@example.org"),
        _person(db_session, "Lieve", "Tweelingnaam", "lieve.twee@example.org"),
        _person(db_session, "Lieve", "Zonderadres", None),
    )


def test_each_result_carries_its_own_address(db_session, namesakes):
    one, two, none = namesakes

    found = {m.id: m.email for m in search_persons(db_session, "lieve")}

    assert found[one.id] == "lieve.een@example.org"
    assert found[two.id] == "lieve.twee@example.org"
    assert found[none.id] is None


def _row_of(html: str, person_id: int) -> str:
    """The result form that adds this person — its markup up to the next form."""
    start = html.index(f'name="person_id" value="{person_id}"')
    end = html.find("</form>", start)
    return html[start:end]


def test_the_circle_search_shows_the_address_beside_the_right_person(client, namesakes):
    one, two, none = namesakes
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    html = client.get("/admin/vergaderingen/kring", params={"q": "lieve"}).text

    assert "lieve.een@example.org" in _row_of(html, one.id)
    assert "lieve.twee@example.org" in _row_of(html, two.id)
    assert "geen e-mailadres" in _row_of(html, none.id)
