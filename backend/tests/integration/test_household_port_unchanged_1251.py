"""CR-13 phase 4c, P2 with C6-3 (#1251): a household is created through mdm's port —
what the doors answer and what is written stays.

"Create a household" is one write path for two doors: the board's "Nieuw lid"
(`POST /admin/leden`) and the public sign-up. Until this cut membership wrote
every row of it itself — the household, its persons, their links, the address
and the contact details, which are mdm's — next to the one row that is its own,
the membership. It asks mdm through the port `CreateHousehold`
(`kernel/contracts/mdm.py`) now and writes only its membership.

No behaviour changes, so the proof is **the same answer and the same rows on the
same input**: every case below was recorded on the code BEFORE the port — the
status of the door, what the screen gets when it refuses, every row of the
household and **every history row the write left**, in the order they were
written — and the code with the port must give it again, character for character
(`tests/_snapshot.py`).

**What a refusal of the board's door is measured at:** the answer of the route —
the form again as an HTML 422 with the reason in it, which is what the page
shows. The public door is called in process (`sign_up_at_the_door`): its status
and its sentence.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import (
    Address,
    AddressHistory,
    ContactDetail,
    ContactDetailHistory,
    Member,
    MemberHistory,
    MemberPerson,
    MemberPersonHistory,
    Person,
    PersonHistory,
    PostalCode,
    new_contact_detail,
)
from app.domains.membership.api import Membership, MembershipHistory
from app.domains.payment.api import PaymentRecord
from tests._snapshot import compare, fixed_ids, main_region, normalise
from tests.conftest import SEEDED_ADMIN_EMAIL, sign_up_at_the_door

pytestmark = pytest.mark.ui_serverrendered

SNAPSHOTS = Path(__file__).parent / "snapshots" / "household_port_1251"
BEFORE = "a household was created through mdm's port (CR-13 phase 4c, P2)"
HISTORIES = (
    MemberHistory,
    PersonHistory,
    MemberPersonHistory,
    AddressHistory,
    ContactDetailHistory,
    MembershipHistory,
)
MODELS = (Member, Person, MemberPerson, Address, ContactDetail, PostalCode, Membership)
MODELS += HISTORIES


@pytest.fixture
def world(client, db_session):
    """A postal code, and the board member's session."""
    with fixed_ids(db_session, MODELS):
        db_session.add(PostalCode(postal_code="2399", municipality="Proefdorp"))
        # A flush, not a commit: the board's door opens a savepoint of its own,
        # and the test session's savepoint does not survive a commit before it.
        db_session.flush()
        value = make_session_value(SEEDED_ADMIN_EMAIL)
        client.cookies.set(SESSION_COOKIE, value)
        yield {"X-CSRF-Token": csrf_token_for(value)}


def _rows(db) -> str:
    """Everything a household is made of, and every history row, in the order
    they were written."""
    db.expire_all()

    def every(model):
        return db.query(model).execution_options(include_deleted=True).order_by(model.id)

    def gone(row) -> str:
        return "yes" if row.deleted_at else "no"

    lines = []
    for household in every(Member):
        lines.append(
            f"household {household.id}: board_member={household.board_member_id} "
            f"deleted={gone(household)}"
        )
    for person in every(Person):
        lines.append(
            f"person {person.id}: {person.first_name!r} {person.last_name!r} "
            f"born={person.date_of_birth} gender={person.gender_code} deleted={gone(person)}"
        )
    for link in every(MemberPerson):
        lines.append(
            f"link {link.id}: household={link.member_id} person={link.person_id} "
            f"{link.relation_type} deleted={gone(link)}"
        )
    for address in every(Address):
        lines.append(
            f"address {address.id} of {address.person_id}: {address.street!r} "
            f"{address.house_number!r} bus={address.bus_number!r} "
            f"postal={address.postal_code_id} deleted={gone(address)}"
        )
    for contact in every(ContactDetail):
        lines.append(
            f"contact {contact.id} of {contact.person_id}: {contact.contact_type_code} "
            f"{contact.value!r} primary={contact.is_primary} deleted={gone(contact)}"
        )
    for membership in every(Membership):
        lines.append(
            f"membership {membership.id}: household={membership.member_id} "
            f"active={membership.is_active} deleted={gone(membership)}"
        )
    for record in db.query(PaymentRecord).order_by(PaymentRecord.created_at):
        lines.append(
            f"payment record: {record.payable_type} {record.payable_id} amount={record.amount} "
            f"status={record.status}"
        )
    for model in HISTORIES:
        for row in db.query(model).order_by(model.id):
            lines.append(
                f"{model.__name__} {row.id}: {row.operation} {row.action} "
                f"source={row.source} actor={row.actor}"
            )
    return "\n".join(lines)


def _record(name: str, status: int, said: str, db) -> None:
    today = date.today()
    moving = {today.isoformat(): "<TODAY>", str(today.year): "<YEAR>"}
    # A field's example address is copy, not data — and no address outside the
    # reserved domains may stand in a test file of this public repository.
    said = re.sub(r'(placeholder=")[^"]*@[^"]*', r"\1<EXAMPLE-ADDRESS>", said)
    got = normalise(f"{status}\n{said}\n--- rows ---\n{_rows(db)}", {}, moving)
    compare(SNAPSHOTS, name, got, BEFORE)


# ── the board's door ─────────────────────────────────────────────────────────

BOARD = {
    "street": "Proefstraat",
    "house_number": "12",
    "bus_number": "b",
    "postal_code": "2399",
    "m0_first_name": "Hanne",
    "m0_last_name": "Proef",
    "m0_date_of_birth": "1980-03-04",
    "m0_gender_code": "F",
    "m0_email": "hanne-1251@example.com",
    "m0_phone": "014 12 34 56",
    "m0_mobile": "0470 12 34 56",
    "m1_first_name": "Bram",
    "m1_last_name": "Proef",
    "m1_date_of_birth": "1979-05-06",
    "m1_gender_code": "M",
    "m1_email": "bram-1251@example.com",
    "m1_phone": "",
    "m1_mobile": "0471 12 34 56",
    "m2_first_name": "Lotte",
    "m2_last_name": "Proef",
    "m2_date_of_birth": "2010-07-08",
    "m2_gender_code": "F",
    "m2_email": "",
    "m2_phone": "",
    "m2_mobile": "",
    "m2_relation_type": "KIND",
}


def _board(client, headers, db, name: str, fields: dict) -> None:
    response = client.post("/admin/leden", data=fields, headers=headers)
    if response.status_code == 204:
        said = f"HX-Redirect: {response.headers.get('HX-Redirect')}"
    else:
        said = main_region(response.text)
    _record(name, response.status_code, said, db)


def test_the_board_creates_a_household_as_it_did(client, db_session, world):
    _board(client, world, db_session, "board_created", BOARD)


@pytest.mark.parametrize(
    "name, changes",
    [
        ("board_refused_unknown_postal_code", {"postal_code": "9999"}),
        ("board_refused_no_street", {"street": ""}),
        ("board_refused_no_birth_date", {"m2_date_of_birth": ""}),
        ("board_refused_no_gender", {"m1_gender_code": ""}),
        # Recorded again on purpose, after the move: a second main member was
        # taken as typed (a 204, two main members, two addresses) and is refused
        # since the repair that followed — `test_one_main_member_1251.py` holds
        # that change, red before it.
        ("board_refused_two_main_members", {"m1_relation_type": "HOOFDLID"}),
        (
            "board_refused_no_person",
            {key: "" for key in BOARD if key.endswith(("_first_name", "_last_name"))},
        ),
    ],
)
def test_the_board_answers_as_it_did(client, db_session, world, name, changes):
    _board(client, world, db_session, name, BOARD | changes)


# ── the public door ──────────────────────────────────────────────────────────


def _member(**changes) -> dict:
    main = {
        "last_name": "Proef",
        "first_name": "Opnieuw",
        "email": "aanmelder-1251@example.com",
        "mobile": "0470000001",
        "date_of_birth": "1980-01-01",
        "gender_code": "M",
        "relation_type": "HOOFDLID",
    }
    return main | changes


def _payload(*members: dict, **changes) -> dict:
    household = {
        "street": "Dorpsplein",
        "house_number": "40",
        "postal_code": "2399",
        "payment_method": "transfer",
        "members": list(members),
    }
    return household | changes


def _door(client, db, name: str, payload: dict, **signed_in) -> None:
    answer = sign_up_at_the_door(client, json=payload, **signed_in)
    body = answer.json()
    said = str(body.get("detail", "(registered)")) if isinstance(body, dict) else str(body)
    _record(name, answer.status_code, said, db)


def test_a_visitor_signs_a_household_up_as_before(client, db_session, world):
    """A main member with two addresses and a phone number, a partner and a child."""
    main = _member(extra_emails=["tweede-1251@example.com"], phone="014 11 22 33")
    partner = _member(
        first_name="Mee", email="partner-1251@example.com", mobile="", relation_type="PARTNER"
    )
    child = _member(
        first_name="Klein",
        email=None,
        mobile=None,
        date_of_birth="2012-02-03",
        relation_type="KIND",
    )
    _door(client, db_session, "signup_registered", _payload(main, partner, child))


def test_an_account_that_signs_up_becomes_the_main_member_as_before(client, db_session, world):
    """The person who is signed in is adopted: no second person, the contact
    details he holds stay, what the form adds is added."""
    address = "account-1251@example.com"
    person = Person(first_name="Acco", last_name="Unt")
    db_session.add(person)
    db_session.flush()
    db_session.add(new_contact_detail(db_session, person, "EMAIL", address, is_primary=True))
    db_session.add(new_contact_detail(db_session, person, "MOBILE", "0470000009", is_primary=True))
    db_session.flush()

    main = _member(email=address, mobile="0470000001", phone="014 11 22 33")
    _door(client, db_session, "signup_by_an_account", _payload(main), signed_in_email=address)


@pytest.mark.parametrize(
    "name, payload",
    [
        ("signup_refused_unknown_postal_code", _payload(_member(), postal_code="9999")),
        ("signup_refused_no_house_number", _payload(_member(), house_number="")),
    ],
)
def test_a_sign_up_is_refused_as_it_was(client, db_session, world, name, payload):
    _door(client, db_session, name, payload)


# ── a household that is deleted ──────────────────────────────────────────────

SUBJECT = {
    MemberHistory: "member_id",
    PersonHistory: "person_id",
    MemberPersonHistory: "member_person_id",
    AddressHistory: "address_id",
    ContactDetailHistory: "contact_detail_id",
    MembershipHistory: "membership_id",
}


def _set_of_rows(db) -> str:
    """The same rows as a SET: every history row by its table, its subject, its
    operation, action, source and actor — without its own id, in no order."""
    lines = [line for line in _rows(db).splitlines() if "History " not in line]
    for model, subject in SUBJECT.items():
        for row in db.query(model):
            lines.append(
                f"{model.__name__} of {getattr(row, subject)}: {row.operation} {row.action} "
                f"source={row.source} actor={row.actor}"
            )
    return "\n".join(sorted(lines))


def test_the_board_deletes_a_household_with_the_same_rows(client, db_session, world):
    """mdm deletes its rows and says so (`HouseholdDeleted`); membership deletes
    its memberships on hearing it. The rows are the same, their order within the
    one deletion is not: until this cut the memberships went first. So this
    recording compares the set of rows, not their sequence."""
    created = client.post("/admin/leden", data=BOARD, headers=world)
    household = created.headers["HX-Redirect"].rsplit("/", 1)[-1]

    response = client.post(f"/admin/leden/gezin/{household}/verwijderen", headers=world)

    said = f"HX-Redirect: {response.headers.get('HX-Redirect')}"
    got = normalise(
        f"{response.status_code}\n{said}\n--- rows ---\n{_set_of_rows(db_session)}", {}, {}
    )
    compare(SNAPSHOTS, "board_deleted", got, BEFORE)

    missing = client.post("/admin/leden/gezin/1/verwijderen", headers=world)
    assert (missing.status_code, missing.json()) == (404, {"detail": "Family not found"})


# ── the rule no door reaches ─────────────────────────────────────────────────


def test_a_person_without_details_is_refused_where_the_household_is_made(db_session, world):
    """Both doors refuse a person without a birth date or a gender at their form
    (the schema), so no recording above reaches the rule that stands at the write
    itself. It moved to mdm with the write: asked here past the form, it refuses
    in the same words, as a 422 of membership's service, and nothing is made.

    Proven red: the `require_details` loop in `mdm.household_service.
    create_household` replaced by `pass` — the household is made."""
    from fastapi import HTTPException

    from app.domains.membership.api import (
        FamilyCreate,
        FamilyMemberCreate,
        create_family_with_members,
    )

    main = FamilyMemberCreate.model_construct(
        first_name="Zonder",
        last_name="Datum",
        date_of_birth=None,
        gender_code="M",
        gender=None,
        email=None,
        extra_emails=[],
        phone=None,
        mobile=None,
        relation_type="HOOFDLID",
    )
    data = FamilyCreate.model_construct(
        street="Proefstraat", house_number="1", bus_number=None, postal_code="2399", members=[main]
    )

    with pytest.raises(HTTPException) as refusal:
        create_family_with_members(db_session, data, actor="test", source="admin_manual")

    assert refusal.value.status_code == 422
    assert refusal.value.detail == "Geboortedatum en geslacht zijn verplicht voor elk gezinslid."
    assert db_session.query(Member).count() == 0
