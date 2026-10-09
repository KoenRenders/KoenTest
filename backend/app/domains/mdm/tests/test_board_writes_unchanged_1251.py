"""CR-13 phase 4c, C6-2 (#1251): the board's writes on a household move to mdm — what
the screen answers and what is written stays.

The Leden screen (`mdm/ui.py`) changes a household's persons, their contact
details, their relation, its address and its board member. The seven functions
that write those rows stood in `membership/household_service.py` — a second
domain writing mdm's rows, reached from mdm's own screen through
`membership.api`. They stand in `mdm/household_board_service.py` now.

No behaviour changes, so the proof is **the same answer and the same rows on the
same input**: each of the five routes that call those functions is posted once
the way that is accepted and once the way that is refused, and for each the
screen's answer, the rows of the household and **every history row the write
left** were recorded on the code BEFORE the move; the moved code must give them
again, character for character (`tests/_snapshot.py`).

Two of the twelve were recorded again on purpose, after the move: a blank name on
the person's card and on a new person ended the request in a 500 (recorded as
"raised MasterDataError") and is a 422 with the object's words since the repair
that followed C6-2 — `test_person_name_refused_1251.py` holds that change, red
before it. Their rows are as they were: nothing is written either way.

A third was recorded again with the rule that a household has one main member
(`test_one_main_member_1251.py`): making a child the main
member saved the rest of the card and dropped the relation without a word — a
200 — and is a 422 that writes nothing now.
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
)
from tests._snapshot import compare, fixed_ids, normalise
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

SNAPSHOTS = Path(__file__).parent / "snapshots" / "board_writes_1251"
BEFORE = "the board's writes on a household moved to mdm (CR-13 phase 4c, C6-2)"
MODELS = (Member, Person, MemberPerson, Address, ContactDetail, PostalCode)
MODELS += (PersonHistory, MemberHistory, MemberPersonHistory, AddressHistory, ContactDetailHistory)
HISTORIES = (
    PersonHistory,
    MemberHistory,
    MemberPersonHistory,
    AddressHistory,
    ContactDetailHistory,
)


class World:
    household: int
    main: int
    partner: int
    child: int
    outsider: int


@pytest.fixture
def world(db_session):
    """A household of three — a main member with an address and an e-mail
    address, a partner, a child — and one person outside it."""
    with fixed_ids(db_session, MODELS):
        db = db_session
        postal = PostalCode(postal_code="2399", municipality="Proefdorp")
        household = Member()
        db.add_all([postal, household])
        db.flush()
        people = {}
        for key, first, born, gender, relation in (
            ("main", "Hanne", date(1980, 3, 4), "F", "HOOFDLID"),
            ("partner", "Bram", date(1979, 5, 6), "M", "PARTNER"),
            ("child", "Lotte", date(2010, 7, 8), "F", "KIND"),
        ):
            person = Person(
                first_name=first, last_name="Proef", date_of_birth=born, gender_code=gender
            )
            db.add(person)
            db.flush()
            db.add(
                MemberPerson(member_id=household.id, person_id=person.id, relation_type=relation)
            )
            people[key] = person.id
        outsider = Person(
            first_name="Buiten",
            last_name="Staander",
            date_of_birth=date(1990, 1, 1),
            gender_code="M",
        )
        db.add(outsider)
        db.add(
            Address(
                person_id=people["main"],
                street="Proefstraat",
                house_number="1",
                postal_code_id=postal.id,
            )
        )
        db.add(
            ContactDetail(
                person_id=people["main"],
                contact_type_code="EMAIL",
                value="bestuur-1251@example.com",
                is_primary=True,
            )
        )
        db.commit()
        w = World()
        w.household, w.outsider = household.id, outsider.id
        w.main, w.partner, w.child = people["main"], people["partner"], people["child"]
        yield w


def _headers(client) -> dict[str, str]:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _rows(db, w: World) -> str:
    """The household as it stands — persons, links, address, contact rows, board
    member — and every history row of mdm, in the order they were written."""
    db.expire_all()
    lines = []
    household = db.query(Member).execution_options(include_deleted=True).get(w.household)
    lines.append(f"household {household.id}: board_member={household.board_member_id}")
    links = (
        db.query(MemberPerson)
        .execution_options(include_deleted=True)
        .filter(MemberPerson.member_id == w.household)
        .order_by(MemberPerson.person_id)
    )
    for link in links:
        lines.append(
            f"link person={link.person_id}: {link.relation_type} "
            f"deleted={'yes' if link.deleted_at else 'no'}"
        )
    for person in db.query(Person).execution_options(include_deleted=True).order_by(Person.id):
        lines.append(
            f"person {person.id}: {person.first_name!r} {person.last_name!r} "
            f"born={person.date_of_birth} gender={person.gender_code} "
            f"deleted={'yes' if person.deleted_at else 'no'}"
        )
    for address in db.query(Address).execution_options(include_deleted=True).order_by(Address.id):
        lines.append(
            f"address of {address.person_id}: {address.street!r} {address.house_number!r} "
            f"bus={address.bus_number!r} postal={address.postal_code_id}"
        )
    contacts = (
        db.query(ContactDetail).execution_options(include_deleted=True).order_by(ContactDetail.id)
    )
    for contact in contacts:
        lines.append(
            f"contact of {contact.person_id}: {contact.contact_type_code} {contact.value!r} "
            f"primary={contact.is_primary} deleted={'yes' if contact.deleted_at else 'no'}"
        )
    for model in HISTORIES:
        for row in db.query(model).order_by(model.id):
            lines.append(
                f"{model.__name__}: {row.operation} {row.action} source={row.source} "
                f"actor={row.actor}"
            )
    return "\n".join(lines)


def _record(name: str, response, db, w: World) -> None:
    today = date.today()
    moving = {today.isoformat(): "<TODAY>", str(today.year): "<YEAR>"}
    # A field's example address is copy, not data — and no address outside the
    # reserved domains may stand in a test file of this public repository.
    screen = re.sub(r'(placeholder=")[^"]*@[^"]*', r"\1<EXAMPLE-ADDRESS>", response.text)
    got = normalise(f"{response.status_code}\n{screen}\n--- rows ---\n{_rows(db, w)}", {}, moving)
    compare(SNAPSHOTS, name, got, BEFORE)


def _base(w: World) -> str:
    return f"/admin/leden/gezin/{w.household}"


ADDRESS = {"street": "Andere straat", "house_number": "9", "bus_number": "b", "postal_code": "2399"}
PERSON = {
    "first_name": "Lotte",
    "last_name": "Proef-Anders",
    "date_of_birth": "2010-07-08",
    "gender_code": "F",
    "phone": "",
    "mobile": "0470 12 34 56",
    "relation_type": "KIND",
}
NEW = {
    "first_name": "Nieuw",
    "last_name": "Proef",
    "date_of_birth": "2015-01-02",
    "gender_code": "M",
    "email": "nieuwkind-1251@example.com",
    "phone": "",
    "mobile": "",
    "relation_type": "KIND",
}


def _cases(w: World) -> dict[str, tuple[str, dict]]:
    """Every case: the path and the fields. Two per route — accepted, refused."""
    base = _base(w)
    return {
        "address_accepted": (f"{base}/adres", ADDRESS),
        "address_refused": (f"{base}/adres", {**ADDRESS, "street": ""}),
        "person_accepted": (f"{base}/persoon/{w.child}", PERSON),
        "person_refused_blank_name": (f"{base}/persoon/{w.child}", {**PERSON, "last_name": ""}),
        "person_refused_second_main": (
            f"{base}/persoon/{w.child}",
            {**PERSON, "relation_type": "HOOFDLID"},
        ),
        "partner_becomes_child": (
            f"{base}/persoon/{w.partner}",
            {
                **PERSON,
                "first_name": "Bram",
                "last_name": "Proef",
                "date_of_birth": "1979-05-06",
                "gender_code": "M",
                "mobile": "",
                "relation_type": "KIND",
            },
        ),
        "add_accepted": (f"{base}/personen", NEW),
        "add_refused_no_last_name": (f"{base}/personen", {**NEW, "last_name": ""}),
        "delete_accepted": (f"{base}/persoon/{w.child}/verwijderen", {}),
        "delete_refused_main": (f"{base}/persoon/{w.main}/verwijderen", {}),
        "board_member_accepted": (f"{base}/bestuurslid", {"person_id": str(w.partner)}),
        "board_member_refused_unknown": (f"{base}/bestuurslid", {"person_id": "999999"}),
    }


CASES = [
    "address_accepted",
    "address_refused",
    "person_accepted",
    "person_refused_blank_name",
    "person_refused_second_main",
    "partner_becomes_child",
    "add_accepted",
    "add_refused_no_last_name",
    "delete_accepted",
    "delete_refused_main",
    "board_member_accepted",
    "board_member_refused_unknown",
]


@pytest.mark.parametrize("name", CASES)
def test_the_boards_write_answers_and_writes_as_it_did(client, db_session, world, name):
    path, fields = _cases(world)[name]
    try:
        response = client.post(path, data=fields, headers=_headers(client))
    except Exception as crash:  # a refusal the screen does not catch is an answer too

        class Crashed:
            status_code = f"raised {type(crash).__name__}"
            text = str(crash)

        response = Crashed()
    _record(name, response, db_session, world)
