"""Lid worden with an account, and with an address that is known (CR-22 S8, #1713; T11).

Two things the public Lid worden did not do:

- **an account that signs up became a second person.** An account is a person
  in master data; signing up made another one beside it, with the same
  address. Now the signed-in account becomes the main member itself (R9, F7).
- **a known address made a second household.** Whoever is not signed in and
  gives, for the main member, an address that already belongs to a person is
  refused: "Dit e-mailadres is al gekend. Log je eerst aan om lid te worden."
  (Q28) — an account's address, and also the address of a household from an
  earlier try whose payment never came (Q40). He signs in, which proves the
  address, and pays from Mijn gezin.

This file was `test_public_sign_up_outside_the_address_rule_1704.py`: slice S1
left this one door outside the address rule, with a test that this slice turns
round. The exception is gone (`new_contact_detail` has no way to skip the rule
any more) and the test below asserts the opposite of what it did.

On made-up data, through the real doors: the JSON route and the page.

Broken on purpose (8 October 2026), each red for its own reason: the known
address let through → a second household; the account not taken over → a
second person; the page not handing over who is signed in → a refusal for the
account's own address; the adopted person given a second copy of his address →
two rows; an account taken over for an address that is not his → somebody
else's person becomes the main member.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domains.auth.api import SESSION_COOKIE, create_access_token, make_session_value
from app.domains.mdm.api import (
    ContactDetail,
    EmailAddressInUse,
    Member,
    MemberPerson,
    Person,
    PersonHistory,
    new_contact_detail,
)
from app.domains.membership.api import Membership, create_family_with_members
from app.domains.membership.schemas_family import FamilyCreate
from tests.conftest import seed_postal_code, signup_fields

pytestmark = pytest.mark.ui_serverrendered

KNOWN = "Dit e-mailadres is al gekend. Log je eerst aan om lid te worden."
ADDRESS = "bekend@example.com"


def _payload(email: str, **main) -> dict:
    member = {
        "last_name": "Proef",
        "first_name": "Opnieuw",
        "email": email,
        "mobile": "0470000001",
        "date_of_birth": "1980-01-01",
        "gender_code": "M",
        "relation_type": "HOOFDLID",
    }
    return {
        "street": "Dorpsplein",
        "house_number": "40",
        "postal_code": "2400",
        "payment_method": "transfer",
        "members": [member | main],
    }


def _account(db, email=ADDRESS, mobile="0470000001"):
    """A person without a household, as "Account aanmaken" makes one: a name,
    a confirmed address and a mobile number — no birth date, no gender."""
    person = Person(first_name="Acco", last_name="Unt")
    db.add(person)
    db.flush()
    db.add(new_contact_detail(db, person, "EMAIL", email, is_primary=True))
    db.add(new_contact_detail(db, person, "MOBILE", mobile, is_primary=True))
    db.commit()
    return person


def _earlier_household(db, email=ADDRESS):
    """What a first try leaves behind once its payment is gone: a household
    whose main member holds the address, without a membership."""
    person = Person(
        date_of_birth=date(1980, 1, 1), gender_code="M", first_name="Eerder", last_name="Proef"
    )
    db.add(person)
    db.flush()
    household = Member()
    db.add(household)
    db.flush()
    db.add(MemberPerson(member_id=household.id, person_id=person.id, relation_type="HOOFDLID"))
    db.flush()
    db.add(new_contact_detail(db, person, "EMAIL", email, is_primary=True))
    db.commit()
    return person


def _counts(db) -> tuple[int, int, int]:
    db.expire_all()
    return db.query(Person).count(), db.query(Member).count(), db.query(Membership).count()


def _bearer(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(data={'sub': email})}"}


# ── a known address, not signed in (Q28, Q40) ────────────────────────────────


@pytest.mark.parametrize("holder", [_account, _earlier_household])
def test_a_known_address_is_refused_and_makes_nothing(client, db_session, holder):
    """Turned round from S1's `…is_outside_the_rule_until_s8`, which expected
    201 and a second household here."""
    seed_postal_code(db_session)
    holder(db_session)
    before = _counts(db_session)
    answer = client.post("/api/v1/families", json=_payload(ADDRESS))
    assert answer.status_code == 409, answer.text
    assert answer.json()["detail"] == KNOWN
    assert _counts(db_session) == before, "something was made for a refused sign-up"


def test_the_page_says_it_in_its_banner_and_keeps_the_form(client, db_session):
    _earlier_household(db_session)
    before = _counts(db_session)
    answer = client.post("/lid-worden", data=signup_fields(db_session, emails=(ADDRESS,)))
    assert KNOWN in answer.text
    assert _counts(db_session) == before


# ── an account that signs up (R9, F7) ────────────────────────────────────────


def test_a_signed_in_account_becomes_the_main_member_itself(client, db_session):
    """Red when the account is not taken over: a second person, and since the
    address rule holds here now, a refusal for his own address."""
    seed_postal_code(db_session)
    account = _account(db_session)
    persons, households, memberships = _counts(db_session)

    answer = client.post(
        "/api/v1/families",
        json=_payload(ADDRESS, first_name="Acco", last_name="Unt-Lid", date_of_birth="1975-03-04"),
        headers=_bearer(ADDRESS),
    )
    assert answer.status_code == 201, answer.text
    assert _counts(db_session) == (persons, households + 1, memberships + 1)

    person = db_session.get(Person, account.id)
    [link] = person.member_persons
    assert link.relation_type.value == "HOOFDLID"
    assert (person.last_name, person.date_of_birth, person.gender_code) == (
        "Unt-Lid",
        date(1975, 3, 4),
        "M",
    )
    assert person.address is not None and person.address.street == "Dorpsplein"
    emails = [c for c in person.contact_details if c.contact_type_code == "EMAIL"]
    mobiles = [c for c in person.contact_details if c.contact_type_code == "MOBILE"]
    assert [c.value for c in emails] == [ADDRESS], "his address was made a second time"
    assert len(mobiles) == 1, "the number he already had was made a second time"
    actions = [h.action for h in db_session.query(PersonHistory).filter_by(person_id=person.id)]
    assert "family_registered" in actions, "taking over the person left no history"


def test_the_page_hands_over_who_is_signed_in(client, db_session):
    """The door a person uses. Red when the route does not pass the session:
    the account's own address is then somebody's address, and refused."""
    account = _account(db_session, mobile="0470000000")
    persons, households, _memberships = _counts(db_session)
    client.cookies.set(SESSION_COOKIE, make_session_value(ADDRESS))
    answer = client.post("/lid-worden", data=signup_fields(db_session, emails=(ADDRESS,)))
    assert answer.status_code == 200 and KNOWN not in answer.text, answer.text[:300]
    assert _counts(db_session)[:2] == (persons, households + 1)
    assert db_session.get(Person, account.id).member_persons


def test_a_number_that_differs_is_added_beside_the_one_he_confirmed(client, db_session):
    """The row that counts stays his; the form's value does not replace it."""
    seed_postal_code(db_session)
    account = _account(db_session, mobile="0470000009")
    answer = client.post(
        "/api/v1/families", json=_payload(ADDRESS, mobile="0470000001"), headers=_bearer(ADDRESS)
    )
    assert answer.status_code == 201, answer.text
    db_session.expire_all()
    mobiles = {
        c.value: c.is_primary
        for c in db_session.get(Person, account.id).contact_details
        if c.contact_type_code == "MOBILE"
    }
    assert mobiles == {"0470000009": True, "0470000001": False}


def test_an_account_is_not_taken_over_for_an_address_that_is_not_his(client, db_session):
    """Signed in as an account, signing up somebody else: a free address makes
    a new person and leaves the account alone; a known one is refused."""
    seed_postal_code(db_session)
    account = _account(db_session)
    _earlier_household(db_session, email="ander@example.com")
    persons, households, _m = _counts(db_session)

    refused = client.post(
        "/api/v1/families", json=_payload("ander@example.com"), headers=_bearer(ADDRESS)
    )
    assert refused.status_code == 409 and refused.json()["detail"] == KNOWN

    made = client.post(
        "/api/v1/families", json=_payload("vrij@example.com"), headers=_bearer(ADDRESS)
    )
    assert made.status_code == 201, made.text
    assert _counts(db_session)[:2] == (persons + 1, households + 1)
    assert not db_session.get(Person, account.id).member_persons, "the account was taken over"


# ── the rule has no door left open ───────────────────────────────────────────


def test_the_boards_door_answers_with_master_datas_own_rule(db_session):
    """The board types somebody else's data: no "log je eerst aan" there, the
    rule of master data itself. It was the only door asking it in S1; now
    every door does."""
    seed_postal_code(db_session)
    _earlier_household(db_session)
    with pytest.raises(EmailAddressInUse):
        create_family_with_members(
            db_session,
            FamilyCreate(**_payload(ADDRESS)),
            actor="bestuur@example.com",
            source="admin_manual",
            membership_active=True,
        )
    db_session.expire_all()
    assert db_session.query(ContactDetail).filter_by(value=ADDRESS).count() == 1
