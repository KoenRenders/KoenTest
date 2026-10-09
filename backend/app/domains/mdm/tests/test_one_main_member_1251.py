"""A household has one main member — refused at every entrance (#1251).

Found while recording the creation of a household (CR-13 phase 4c, P2): the
board's "Nieuw lid" took two main members in one new household, and each got the
household's address. No screen offers it — the form leaves the main member out
of the choice for every person after the first — so it took a hand-made request;
but adding a person took it as well, and changing a person's relation dropped
the request in silence: a 200, the card again, no word.

One rule now, `mdm.household_service.require_one_main_member`, asked at the
three entrances that give a person a place in a household. Each refuses with the
same sentence and writes nothing.

**What the refusals are measured at:** the answers of the routes. "Nieuw lid"
answers its form again as an HTML 422 with the sentence in it, which the kit
swaps into the page. Adding a person and saving a person's card answer a JSON
422 — on the Leden screen that shows as the general toast, not as the sentence
(the message line on those forms is not built). Not a browser test.

Proven red on the code before the rule: all three entrance tests fail — two
households with two main members are made, and the card is saved with a 200.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Member, MemberPerson, Person, PostalCode, RelationType
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

ONE = "Een gezin heeft één hoofdlid."


def _person(n: int, first_name: str, **more) -> dict:
    fields = {
        "first_name": first_name,
        "last_name": "Proef",
        "date_of_birth": "1980-03-04",
        "gender_code": "F",
        "email": "",
        "phone": "",
        "mobile": "",
    }
    return {f"m{n}_{name}": value for name, value in (fields | more).items()}


NEW = {"street": "Proefstraat", "house_number": "12", "bus_number": "", "postal_code": "2399"}
NEW |= _person(0, "Hanne", email="hanne-main-1251@example.com", mobile="0470 00 00 01")
NEW |= _person(1, "Bram", gender_code="M")


@pytest.fixture
def headers(client, db_session):
    db_session.add(PostalCode(postal_code="2399", municipality="Proefdorp"))
    db_session.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


@pytest.fixture
def household(client, db_session, headers) -> tuple[int, int, int]:
    """A household of a main member and a partner, made through the screen: its
    id, the main member's and the partner's."""
    made = client.post("/admin/leden", data=NEW, headers=headers)
    assert made.status_code == 204, made.text
    household_id = int(made.headers["HX-Redirect"].rsplit("/", 1)[-1])
    links = _links(db_session, household_id)
    return household_id, links[0].person_id, links[1].person_id


def _links(db, household_id: int) -> list[MemberPerson]:
    db.expire_all()
    return (
        db.query(MemberPerson)
        .filter(MemberPerson.member_id == household_id)
        .order_by(MemberPerson.id)
        .all()
    )


def _main_members(db, household_id: int) -> int:
    links = _links(db, household_id)
    return sum(link.relation_type is RelationType.PRIMARY_MEMBER for link in links)


def test_a_new_household_with_two_main_members_is_refused(client, db_session, headers):
    answer = client.post(
        "/admin/leden", data=NEW | {"m1_relation_type": "HOOFDLID"}, headers=headers
    )

    assert answer.status_code == 422
    assert "text/html" in answer.headers["content-type"]
    assert ONE in answer.text
    assert db_session.query(Member).count() == 0, "a refused household was made"
    assert db_session.query(Person).filter(Person.last_name == "Proef").count() == 0


def test_adding_a_second_main_member_is_refused(client, db_session, headers, household):
    household_id, _main, _partner = household
    person = {name[3:]: value for name, value in _person(9, "Tweede").items()}

    answer = client.post(
        f"/admin/leden/gezin/{household_id}/personen",
        data=person | {"relation_type": "HOOFDLID"},
        headers=headers,
    )

    assert (answer.status_code, answer.json()) == (422, {"detail": ONE})
    assert len(_links(db_session, household_id)) == 2, "the refused person was added"
    assert _main_members(db_session, household_id) == 1


def test_making_the_partner_a_main_member_is_refused_and_saves_nothing(
    client, db_session, headers, household
):
    """The card's save commits in steps, so the rule is asked before the first:
    the name sent with the refused relation is not written either."""
    household_id, _main, partner = household
    card = {name[3:]: value for name, value in _person(9, "Anders", gender_code="M").items()}

    answer = client.post(
        f"/admin/leden/gezin/{household_id}/persoon/{partner}",
        data=card | {"relation_type": "HOOFDLID"},
        headers=headers,
    )

    assert (answer.status_code, answer.json()) == (422, {"detail": ONE})
    db_session.expire_all()
    assert db_session.get(Person, partner).first_name == "Bram", "half the card was saved"
    assert _main_members(db_session, household_id) == 1


def test_the_main_member_saves_his_own_card_as_before(client, db_session, headers, household):
    """His card sends the relation he has: that is no second main member."""
    household_id, main, _partner = household
    card = {name[3:]: value for name, value in _person(9, "Hanneke").items()}

    answer = client.post(
        f"/admin/leden/gezin/{household_id}/persoon/{main}",
        data=card | {"relation_type": "HOOFDLID", "mobile": "0470 00 00 01"},
        headers=headers,
    )

    assert answer.status_code == 200, answer.text
    db_session.expire_all()
    assert db_session.get(Person, main).first_name == "Hanneke"
    assert _main_members(db_session, household_id) == 1


def test_the_partner_becomes_a_child_as_before(client, db_session, headers, household):
    household_id, _main, partner = household
    card = {name[3:]: value for name, value in _person(9, "Bram", gender_code="M").items()}

    answer = client.post(
        f"/admin/leden/gezin/{household_id}/persoon/{partner}",
        data=card | {"relation_type": "KIND"},
        headers=headers,
    )

    assert answer.status_code == 200, answer.text
    relations = [link.relation_type.value for link in _links(db_session, household_id)]
    assert relations == ["HOOFDLID", "KIND"]
