"""CR-13 phase 3, B8 test 12: the family portal answers as it did.

Phase 3 moves the portal's three mutations — change a person, add one, remove one —
from `membership` to `mdm`, rules and doors both: the household and its persons are
master data (Koen, 27 September 2026). The paths, the URLs and the HTML stay what
they were (master CLI, 29 September 2026), so every answer of those doors is
rendered on the code **before** the move, kept, and the moved code must answer the
same (`tests/_snapshot.py`) — the screen after each mutation, each refusal with its
status and its words, and the JSON the portal's API returns.

**"Before" is master `456bfb83`, not this branch**: recorded by running this file
alone on that commit, before the first line of the move changed.

The world is one household of three — a main member with an address and an e-mail
address, a partner, a child — and a membership until 2099, so the renewal button,
which depends on today, stays out of the picture.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Address, ContactDetail, Member, MemberPerson, Person, PostalCode
from app.domains.membership.api import Membership
from tests._snapshot import compare, main_region, normalise

pytestmark = pytest.mark.ui_serverrendered

SNAPSHOTS = Path(__file__).parent / "snapshots" / "household_portal"
BEFORE = "the move to mdm (CR-13 phase 3)"

BASE = 993_000
MEMBER_ID = BASE
MAIN_ID = BASE + 1
PARTNER_ID = BASE + 2
CHILD_ID = BASE + 3
POSTAL_CODE_ID = BASE + 4
ADDRESS_ID = BASE + 5
MEMBERSHIP_ID = BASE + 6
CONTACT_ID = BASE + 7
#: Where the sequences of the rows a test creates start, so a new person or contact
#: gets the same id on every run — and one that no house number can be mistaken for.
SEQUENCES = {"mdm.persons_id_seq": BASE + 100, "mdm.contact_details_id_seq": BASE + 200}
MAIN_EMAIL = "portaal-hoofd@example.com"


@pytest.fixture
def household(db_session):
    import sqlalchemy as sa

    db = db_session
    for sequence, start in SEQUENCES.items():
        db.execute(sa.text("SELECT setval(:s, :n)"), {"s": sequence, "n": start})
    db.add(PostalCode(id=POSTAL_CODE_ID, postal_code="2399", municipality="Proefdorp"))
    db.add(Member(id=MEMBER_ID))
    db.flush()
    people = (
        (MAIN_ID, "Hanne", "Proef", date(1980, 3, 4), "F", "HOOFDLID"),
        (PARTNER_ID, "Bram", "Proef", date(1979, 5, 6), "M", "PARTNER"),
        (CHILD_ID, "Lotte", "Proef", date(2010, 7, 8), "F", "KIND"),
    )
    for person_id, first, last, born, gender, relation in people:
        db.add(
            Person(
                id=person_id,
                first_name=first,
                last_name=last,
                date_of_birth=born,
                gender_code=gender,
            )
        )
        db.flush()
        db.add(MemberPerson(member_id=MEMBER_ID, person_id=person_id, relation_type=relation))
    db.add(
        Address(
            id=ADDRESS_ID,
            person_id=MAIN_ID,
            street="Proefstraat",
            house_number="1",
            postal_code_id=POSTAL_CODE_ID,
        )
    )
    db.add(
        ContactDetail(
            id=CONTACT_ID,
            person_id=MAIN_ID,
            contact_type_code="EMAIL",
            value=MAIN_EMAIL,
            is_primary=True,
        )
    )
    db.add(
        Membership(
            id=MEMBERSHIP_ID,
            member_id=MEMBER_ID,
            year=2026,
            is_active=True,
            valid_from=date(2026, 1, 1),
            valid_to=date(2099, 12, 31),
        )
    )
    db.commit()


def _login(client) -> dict[str, str]:
    value = make_session_value(MAIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


#: The e-mail row's placeholder address (`_email_rij.html`) renders on the portal; the
#: public-repo gate on e-mail domains reads the snapshots and this file, and does not
#: know a placeholder, so the snapshot keeps its place and not its value.
PLACEHOLDER = re.compile(r'placeholder="[^"@]*@[^"]*"')


def _names() -> dict[int, str]:
    names = {
        MEMBER_ID: "<MEMBER>",
        MAIN_ID: "<MAIN>",
        PARTNER_ID: "<PARTNER>",
        CHILD_ID: "<CHILD>",
        POSTAL_CODE_ID: "<POSTAL>",
        ADDRESS_ID: "<ADDRESS>",
        MEMBERSHIP_ID: "<MEMBERSHIP>",
        CONTACT_ID: "<CONTACT>",
    }
    # A row a test creates: its id comes from a sequence set in the fixture.
    names.update({BASE + 100 + i: f"<NEW-PERSON-{i}>" for i in range(1, 50)})
    names.update({BASE + 200 + i: f"<NEW-CONTACT-{i}>" for i in range(1, 50)})
    return names


def _screen(response) -> str:
    """A 200 is the portal; anything else is its status and what it says."""
    if response.status_code == 200 and "<main" in response.text:
        page = PLACEHOLDER.sub('placeholder="<PLACEHOLDER-EMAIL>"', main_region(response.text))
        return normalise(page, _names(), {})
    return normalise(f"{response.status_code}\n{response.text}", _names(), {})


def _json(response) -> str:
    body = json.dumps(response.json(), indent=1, sort_keys=True, ensure_ascii=False)
    return normalise(f"{response.status_code}\n{body}", _names(), {})


PERSON_FORM = {
    "first_name": "Lotte",
    "last_name": "Proef-Anders",
    "date_of_birth": "2010-07-08",
    "gender_code": "F",
    "phone": "",
    "mobile": "0470123456",
}

NEW_PERSON = {
    "first_name": "Nieuw",
    "last_name": "Proef",
    "date_of_birth": "2015-01-02",
    "gender_code": "M",
    "email": "",
    "phone": "",
    "mobile": "",
}


# ── The screen ───────────────────────────────────────────────────────────────


def test_the_portal(client, db_session, household):
    _login(client)
    compare(SNAPSHOTS, "portal", _screen(client.get("/leden/gezin")), BEFORE)


def test_the_screen_after_changing_a_person(client, db_session, household):
    headers = _login(client)
    response = client.post(f"/leden/gezin/personen/{CHILD_ID}", data=PERSON_FORM, headers=headers)
    compare(SNAPSHOTS, "screen_update", _screen(response), BEFORE)


def test_the_screen_after_changing_an_address(client, db_session, household):
    headers = _login(client)
    form = {
        **PERSON_FORM,
        "first_name": "Hanne",
        "last_name": "Proef",
        "date_of_birth": "1980-03-04",
        "street": "Andere straat",
        "house_number": "9",
        "bus_number": "b",
        "postal_code": "2399",
    }
    response = client.post(f"/leden/gezin/personen/{MAIN_ID}", data=form, headers=headers)
    compare(SNAPSHOTS, "screen_update_address", _screen(response), BEFORE)


def test_the_screen_after_adding_a_person(client, db_session, household):
    headers = _login(client)
    response = client.post("/leden/gezin/personen", data=NEW_PERSON, headers=headers)
    compare(SNAPSHOTS, "screen_add", _screen(response), BEFORE)


def test_the_screen_after_removing_a_person(client, db_session, household):
    headers = _login(client)
    response = client.post(f"/leden/gezin/personen/{PARTNER_ID}/verwijderen", headers=headers)
    compare(SNAPSHOTS, "screen_remove", _screen(response), BEFORE)


@pytest.mark.parametrize(
    "screen,path,data",
    [
        (
            "screen_refused_no_birth_date",
            f"/leden/gezin/personen/{CHILD_ID}",
            {**PERSON_FORM, "date_of_birth": ""},
        ),
        (
            "screen_refused_unknown_postal_code",
            f"/leden/gezin/personen/{MAIN_ID}",
            {**PERSON_FORM, "street": "X", "house_number": "1", "postal_code": "0001"},
        ),
        ("screen_refused_no_last_name", "/leden/gezin/personen", {**NEW_PERSON, "last_name": ""}),
        ("screen_refused_self", f"/leden/gezin/personen/{MAIN_ID}/verwijderen", {}),
        ("screen_refused_unknown_person", f"/leden/gezin/personen/{BASE + 98}/verwijderen", {}),
    ],
)
def test_the_screen_refuses_in_the_same_words(client, db_session, household, screen, path, data):
    headers = _login(client)
    response = client.post(path, data=data, headers=headers)
    compare(SNAPSHOTS, screen, _screen(response), BEFORE)


def test_the_screen_refuses_a_stranger(client, db_session, household):
    """Another household's person: the boundary every portal mutation keeps."""
    stranger = Person(
        first_name="Vreemd", last_name="Iemand", date_of_birth=date(1990, 1, 1), gender_code="M"
    )
    db_session.add(stranger)
    db_session.flush()
    db_session.add(Member(id=BASE + 50))
    db_session.flush()
    db_session.add(
        MemberPerson(member_id=BASE + 50, person_id=stranger.id, relation_type="HOOFDLID")
    )
    db_session.commit()
    headers = _login(client)
    response = client.post(f"/leden/gezin/personen/{stranger.id}/verwijderen", headers=headers)
    names = {stranger.id: "<STRANGER>"}
    got = normalise(f"{response.status_code}\n{response.text}", names, {})
    compare(SNAPSHOTS, "screen_refused_stranger", got, BEFORE)


# ── The JSON door ────────────────────────────────────────────────────────────


def test_the_json_answers(client, db_session, household):
    from app.domains.auth.api import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token({'sub': MAIN_EMAIL})}"}
    answers = [
        _json(client.get("/api/v1/member/household", headers=headers)),
        _json(
            client.put(
                f"/api/v1/member/household/persons/{CHILD_ID}",
                json={"first_name": "Lotte", "last_name": "Proef-Json", "mobile": "0470999999"},
                headers=headers,
            ),
        ),
        _json(
            client.post(
                "/api/v1/member/household/persons",
                json={**NEW_PERSON, "phone": "014000000"},
                headers=headers,
            ),
        ),
        _json(
            client.put(
                f"/api/v1/member/household/persons/{CHILD_ID}",
                json={"gender_code": ""},
                headers=headers,
            ),
        ),
        _json(
            client.post(
                "/api/v1/member/household/persons",
                json={**NEW_PERSON, "first_name": " "},
                headers=headers,
            ),
        ),
        _json(
            client.delete(f"/api/v1/member/household/persons/{MAIN_ID}", headers=headers),
        ),
    ]
    removed = client.delete(f"/api/v1/member/household/persons/{PARTNER_ID}", headers=headers)
    answers.append(normalise(f"{removed.status_code}\n{removed.text}", {}, {}))
    compare(SNAPSHOTS, "json", "\n".join(answers), BEFORE)


# ── The household's own order (Koen, 29 September 2026) ──────────────────────


def test_the_household_is_in_its_own_order(client, db_session):
    """Main member, partner, then the children from oldest to youngest, a child
    without a birth date last — whatever order they joined in. Before, the portal
    showed the order the database returned the rows in, and a snapshot of it swapped
    main member and partner about one run in three.

    The partner joins first and the youngest child before the oldest, so an order
    that follows the joining (or the id) is wrong here in two places. Asked three
    times, the same answer.

    Broken on purpose (run, then restored), additively: `links =
    list(member.member_persons)` added after the sort in `get_household` → this
    test fails with the partner first.
    """
    from app.domains.auth.api import create_access_token
    from app.domains.mdm.models import HOUSEHOLD_MEMBER_DETAILS
    from app.kernel.rules import exempt

    household = Member()
    db_session.add(household)
    db_session.flush()
    joining = [
        ("Partner", date(1981, 1, 1), "PARTNER"),
        ("Jongste", date(2012, 1, 1), "KIND"),
        ("Zonderdatum", None, "KIND"),
        ("Hoofd", date(1980, 1, 1), "HOOFDLID"),
        ("Oudste", date(2008, 1, 1), "KIND"),
    ]
    # A child without a birth date exists only from before #681 (PROD holds two).
    exempt(db_session, HOUSEHOLD_MEMBER_DETAILS, "an old member from before #681")
    for first, born, relation in joining:
        person = Person(first_name=first, last_name="Volgorde", date_of_birth=born, gender_code="M")
        db_session.add(person)
        db_session.flush()
        db_session.add(
            MemberPerson(member_id=household.id, person_id=person.id, relation_type=relation)
        )
        db_session.flush()
        if first == "Hoofd":
            db_session.add(
                ContactDetail(
                    person_id=person.id,
                    contact_type_code="EMAIL",
                    value="volgorde-hoofd@example.com",
                    is_primary=True,
                )
            )
    db_session.commit()

    headers = {
        "Authorization": f"Bearer {create_access_token({'sub': 'volgorde-hoofd@example.com'})}"
    }
    for _ in range(3):
        answer = client.get("/api/v1/member/household", headers=headers)
        assert answer.status_code == 200, answer.text
        assert [p["first_name"] for p in answer.json()["persons"]] == [
            "Hoofd",
            "Partner",
            "Oudste",
            "Jongste",
            "Zonderdatum",
        ]
