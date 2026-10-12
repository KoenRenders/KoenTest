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
swaps into the page. Adding a person and saving a person's card answer the
kit's refusal for the card's own message line since #1831 (until then a JSON
422, which the screen showed as its general message). Not a browser test.

Proven red on the code before the rule: all three entrance tests fail — two
households with two main members are made, and the card is saved with a 200.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Member, MemberPerson, Person, PostalCode, RelationType
from tests.conftest import SEEDED_ADMIN_EMAIL, new_household_form, record_fields, save_record

pytestmark = pytest.mark.ui_serverrendered

ONE = "Een gezin heeft één hoofdlid."
#: #1899: the household record's one save refuses the main member's place for
#: anyone, at that person's relation, in these words.
CHOOSE = "Kies partner of kind."


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
    made = client.post("/admin/leden", data=new_household_form(NEW), headers=headers)
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
        "/admin/leden",
        data=new_household_form(NEW | {"m1_relation_type": "HOOFDLID"}),
        headers=headers,
    )

    assert answer.status_code == 422
    assert "text/html" in answer.headers["content-type"]
    # #1899: the form of Word lid offers partner and child only, and its reader
    # refuses a second main member at that person's relation.
    assert "Kies partner of kind." in answer.text
    assert db_session.query(Member).count() == 0, "a refused household was made"
    assert db_session.query(Person).filter(Person.last_name == "Proef").count() == 0


def test_adding_a_second_main_member_is_refused(client, db_session, headers, household):
    household_id, _main, _partner = household
    fields = record_fields(client, household_id)
    fields["h_order"] = [*fields["h_order"], "n9"]
    fields.update(
        {
            "h.n9.first_name": "Tweede",
            "h.n9.last_name": "Proef",
            "h.n9.date_of_birth": "1980-03-04",
            "h.n9.gender_code": "F",
            "h.n9.relation_type": "HOOFDLID",
        }
    )

    answer = save_record(client, household_id, fields, headers)

    # The refusal stands at the person's relation, not as a sentence of the banner.
    assert answer.status_code == 422 and CHOOSE in answer.text, answer.text[:300]
    assert ".relation_type" in answer.text
    assert len(_links(db_session, household_id)) == 2, "the refused person was added"
    assert _main_members(db_session, household_id) == 1


def test_making_the_partner_a_main_member_is_refused_and_saves_nothing(
    client, db_session, headers, household
):
    """One save, one transaction (#1899): the name sent with the refused relation
    is not written either."""
    household_id, _main, partner = household
    fields = record_fields(client, household_id)
    fields[f"h.{partner}.first_name"] = "Anders"
    fields[f"h.{partner}.relation_type"] = "HOOFDLID"

    answer = save_record(client, household_id, fields, headers)

    # The refusal stands at the person's relation, not as a sentence of the banner.
    assert answer.status_code == 422 and CHOOSE in answer.text, answer.text[:300]
    assert ".relation_type" in answer.text
    db_session.expire_all()
    assert db_session.get(Person, partner).first_name == "Bram", "half the card was saved"
    assert _main_members(db_session, household_id) == 1


def test_the_main_member_saves_his_own_card_as_before(client, db_session, headers, household):
    """His card carries the fixed badge and sends no relation: he keeps his place."""
    household_id, main, _partner = household
    fields = record_fields(client, household_id)
    assert f"h.{main}.relation_type" not in fields
    fields[f"h.{main}.first_name"] = "Hanneke"

    answer = save_record(client, household_id, fields, headers)

    assert answer.status_code == 200, answer.text
    db_session.expire_all()
    assert db_session.get(Person, main).first_name == "Hanneke"
    assert _main_members(db_session, household_id) == 1


def test_the_partner_becomes_a_child_as_before(client, db_session, headers, household):
    household_id, _main, partner = household
    fields = record_fields(client, household_id)
    fields[f"h.{partner}.relation_type"] = "KIND"

    answer = save_record(client, household_id, fields, headers)

    assert answer.status_code == 200, answer.text
    relations = [link.relation_type.value for link in _links(db_session, household_id)]
    assert relations == ["HOOFDLID", "KIND"]
