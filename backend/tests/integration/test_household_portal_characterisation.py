"""CR-13 phase 3, B8 test 12: the family portal answers as it did.

Phase 3 moved the portal's three mutations — change a person, add one, remove one —
from `membership` to `mdm`, rules and doors both: the household and its persons are
master data (Koen, 27 September 2026). Every answer of those doors was rendered on
the code **before** the move (master `456bfb83`), kept, and the moved code had to
answer the same (`tests/_snapshot.py`).

**The JSON door still stands on that recording** (`json.html`, untouched): the
portal's API did not change.

**The screen snapshots were recorded again with #1590**, because the screen
itself was rebuilt — CR-11 pilot B put "Mijn gezin" on the public form page, read
first, with one edit mode and one "Opslaan" (`POST /leden/gezin`) instead of a
route per person, per e-mail row and per removal. The snapshots of those row
routes (`screen_update`, `screen_add`, `screen_remove`, `screen_refused_*`) went
with the routes. What stands in their place:

- `portal_read` and `portal_edit`: the page in its two modes;
- `save_answer`: what one save answers that changes a person, changes the
  address, adds a person and removes one — the page in read mode;
- `save_refused`: what a refused save answers — the banner, with every refusal
  the row routes used to make one at a time, now together and each at its place.

A snapshot recorded on the code it guards proves nothing about that code: these
four are the baseline for the NEXT change of the portal, not a proof of #1590.
What #1590 itself must keep — every rule, every history row, one transaction —
is proven in `mdm/tests/test_household_save.py` and `test_household_save_route.py`.

The world is one household of three — a main member with an address and an e-mail
address, a partner, a child — and a membership until 2099, so the renewal button,
which depends on today, stays out of the picture.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Address, ContactDetail, Member, MemberPerson, Person, PostalCode
from app.domains.membership.api import Membership
from tests._snapshot import compare, main_region, normalise
from tests.conftest import household_at_the_portal, household_fields

pytestmark = pytest.mark.ui_serverrendered

SNAPSHOTS = Path(__file__).parent / "snapshots" / "household_portal"
BEFORE = "the move to mdm (CR-13 phase 3)"
REBUILT = "the next change of the portal (recorded with #1590)"

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
        return normalise(main_region(response.text), _names(), {})
    return normalise(f"{response.status_code}\n{response.text}", _names(), {})


def _json(response) -> str:
    body = json.dumps(response.json(), indent=1, sort_keys=True, ensure_ascii=False)
    return normalise(f"{response.status_code}\n{body}", _names(), {})


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


def _save(client, headers, fields):
    return client.post("/leden/gezin", data=fields, headers=headers)


def test_the_portal_in_read_mode(client, db_session, household):
    _login(client)
    compare(SNAPSHOTS, "portal_read", _screen(client.get("/leden/gezin")), REBUILT)


def test_the_portal_in_edit_mode(client, db_session, household):
    _login(client)
    compare(SNAPSHOTS, "portal_edit", _screen(client.get("/leden/gezin?bewerken=1")), REBUILT)


def test_the_answer_of_one_save(client, db_session, household):
    """One "Opslaan" that does what four row routes did: the child gets another
    name and a mobile number, the address moves, a person is added with an
    e-mail address, and the partner — no longer in the form — leaves. The main
    member has no mobile number in this world (the JSON recording is older than
    the rule), so she types one: the save asks it of her (#1590)."""
    headers = _login(client)
    fields = household_fields(client)
    assert fields["h_order"] == [str(MAIN_ID), str(PARTNER_ID), str(CHILD_ID)]
    fields["h_order"] = [str(MAIN_ID), str(CHILD_ID), "n1"]
    for name in [n for n in fields if n.startswith(f"h.{PARTNER_ID}.")]:
        del fields[name]
    fields.update(
        {
            f"h.{MAIN_ID}.mobile": "0470 00 00 01",
            f"h.{CHILD_ID}.last_name": "Proef-Anders",
            f"h.{CHILD_ID}.mobile": "0470123456",
            "address.street": "Andere straat",
            "address.house_number": "9",
            "address.bus_number": "b",
            "h.n1.first_name": "Nieuw",
            "h.n1.last_name": "Proef",
            "h.n1.date_of_birth": "2015-01-02",
            "h.n1.gender_code": "M",
            "e_order.n1": ["n1e"],
            "e.n1e.value": "portaal-nieuw@example.com",
            "e_primary.n1": "n1e",
        }
    )
    response = _save(client, headers, fields)
    assert response.status_code == 200, response.text[:300]
    assert response.headers["HX-Push-Url"] == "/leden/gezin"
    compare(SNAPSHOTS, "save_answer", _screen(response), REBUILT)


def test_a_refused_save_answers_in_these_words(client, db_session, household):
    """Every refusal the row routes made, in one save: the child without a birth
    date, a new person without a last name, an unknown postal code, a person who
    is not (or no longer) of this household, a person of ANOTHER household — the
    boundary every portal mutation keeps — and the member taking themselves out.
    The banner names each at its place; nothing of the page comes back."""
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
    fields = household_fields(client)
    for name in [n for n in fields if n.startswith(f"h.{MAIN_ID}.")]:
        del fields[name]
    fields["h_order"] = [str(PARTNER_ID), str(CHILD_ID), "n1", str(BASE + 98), str(stranger.id)]
    fields.update(
        {
            f"h.{CHILD_ID}.date_of_birth": "",
            "h.n1.first_name": "Nieuw",
            "h.n1.last_name": "",
            "h.n1.date_of_birth": "2015-01-02",
            "h.n1.gender_code": "M",
            f"h.{BASE + 98}.first_name": "Onbekend",
            f"h.{BASE + 98}.last_name": "Proef",
            f"h.{stranger.id}.first_name": "Gekaapt",
            f"h.{stranger.id}.last_name": "Iemand",
            "address.postal_code": "0001",
        }
    )
    response = _save(client, headers, fields)
    assert response.status_code == 422
    assert "<main" not in response.text and "<html" not in response.text.lower()
    names = {**_names(), stranger.id: "<STRANGER>", BASE + 98: "<UNKNOWN>"}
    got = normalise(f"{response.status_code}\n{response.text}", names, {})
    compare(SNAPSHOTS, "save_refused", got, REBUILT)
    db_session.expire_all()
    assert db_session.get(Person, stranger.id).first_name == "Vreemd"
    assert db_session.get(Person, CHILD_ID).date_of_birth == date(2010, 7, 8)
    assert db_session.query(MemberPerson).filter_by(member_id=MEMBER_ID).count() == 3


# ── The JSON door ────────────────────────────────────────────────────────────


def test_the_json_answers(client, db_session, household):
    from app.domains.auth.api import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token({'sub': MAIN_EMAIL})}"}
    answers = [
        _json(household_at_the_portal(client, MAIN_EMAIL)),
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


def test_the_json_door_does_not_ask_the_main_member_a_mobile(client, db_session, household):
    """#1590: the rule is asked at Word lid and at the one save of Mijn gezin,
    not here — the API stores and removes a main member's mobile as before.
    (The same household's save through the page is refused without one: the
    portal tests in `mdm/tests`.)"""
    from app.domains.auth.api import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token({'sub': MAIN_EMAIL})}"}
    path = f"/api/v1/member/household/persons/{MAIN_ID}"

    def mobiles() -> list[str]:
        db_session.expire_all()
        return [
            c.value
            for c in db_session.get(Person, MAIN_ID).contact_details
            if c.contact_type_code == "MOBILE"
        ]

    assert client.put(path, json={"mobile": "0470999999"}, headers=headers).status_code == 200
    assert mobiles() == ["0470999999"]
    emptied = client.put(path, json={"mobile": ""}, headers=headers)
    assert emptied.status_code == 200, emptied.text
    assert mobiles() == []


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

    for _ in range(3):
        answer = household_at_the_portal(client, "volgorde-hoofd@example.com")
        assert answer.status_code == 200, answer.text
        assert [p["first_name"] for p in answer.json()["persons"]] == [
            "Hoofd",
            "Partner",
            "Oudste",
            "Jongste",
            "Zonderdatum",
        ]
