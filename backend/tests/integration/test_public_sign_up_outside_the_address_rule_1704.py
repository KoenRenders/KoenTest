"""The public Lid worden stays outside the address rule until slice S8 (CR-22 Q40, #1704).

Koen, 7 October 2026. The rule of CR-22 — an e-mail address belongs to one
person outside a household — meets a flow the document had not seen: the
public sign-up makes household, person and address BEFORE the payment, and
someone whose payment failed may try again with the same address
(`test_payment_security.py::test_membership_dedup_allows_after_failed_payment`).
With the rule on that door he would be refused: the address already belongs to
the person of his first try.

So in S1 that ONE door does not ask the rule. It is an exception with an end:
slice S8 (#1713) gives the retry its own answer — no second household; sign in
and resume the payment — and then **turns the first test of this file round**:
the same request is refused with "Dit e-mailadres is al gekend. Log je eerst aan
om lid te worden.".

The board's door for the same act is NOT excepted, and the second test holds
that: the exception is one door wide.

Broken on purpose (7 October 2026): `email_rule=False` out of the public route
→ the first test answers 422; `enforce_rule=email_rule` out of
`create_family_with_members` → the second test makes the household.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domains.mdm.api import (
    ContactDetail,
    EmailAddressInUse,
    Member,
    MemberPerson,
    Person,
    new_contact_detail,
)
from app.domains.membership.api import create_family_with_members
from app.domains.membership.schemas_family import FamilyCreate
from tests.conftest import seed_postal_code

pytestmark = pytest.mark.ui_agnostisch

TAKEN = "eerder@example.com"


def _payload(email: str) -> dict:
    return {
        "street": "Dorpsplein",
        "house_number": "40",
        "postal_code": "2400",
        "payment_method": "transfer",
        "members": [
            {
                "last_name": "Proef",
                "first_name": "Opnieuw",
                "email": email,
                "mobile": "0470000001",
                "date_of_birth": "1980-01-01",
                "gender_code": "M",
                "relation_type": "HOOFDLID",
            }
        ],
    }


@pytest.fixture
def an_earlier_household(db_session):
    """A household whose main member holds TAKEN and has no membership this
    year — what a first try leaves behind once its payment is gone."""
    seed_postal_code(db_session)
    person = Person(
        date_of_birth=date(1980, 1, 1), gender_code="M", first_name="Eerder", last_name="Proef"
    )
    db_session.add(person)
    db_session.flush()
    household = Member()
    db_session.add(household)
    db_session.flush()
    db_session.add(
        MemberPerson(member_id=household.id, person_id=person.id, relation_type="HOOFDLID")
    )
    db_session.flush()
    db_session.add(new_contact_detail(db_session, person, "EMAIL", TAKEN, is_primary=True))
    db_session.commit()


def _holders(db) -> int:
    db.expire_all()
    return db.query(ContactDetail).filter(ContactDetail.value == TAKEN).count()


def test_the_public_sign_up_door_is_outside_the_rule_until_s8(
    client, db_session, an_earlier_household
):
    """S8 (#1713) turns this round: then the answer is the refusal of Q28."""
    answer = client.post("/api/v1/families", json=_payload(TAKEN))
    assert answer.status_code == 201, answer.text
    assert _holders(db_session) == 2, "the second household of today's retry"


def test_the_boards_door_for_the_same_act_does_ask_the_rule(db_session, an_earlier_household):
    """The exception is one door wide: the same write path as the board's
    "lid aanmaken" calls it (`create_family_by_admin`), with its defaults."""
    with pytest.raises(EmailAddressInUse):
        create_family_with_members(
            db_session,
            FamilyCreate(**_payload(TAKEN)),
            actor="bestuur@example.com",
            source="admin_manual",
            membership_active=True,
        )
    assert _holders(db_session) == 1
