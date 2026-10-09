"""The Leden screen says why it refuses, in the card that was saved (#1831).

A household's page has a form per card. Every refusal of the address card, of a
person's card and of "persoon toevoegen" answered a bare JSON error, and the
screen showed the kit's general message — "Er ging iets mis … probeer opnieuw" —
for something no retry would mend. The rule's own sentence existed and never
reached the screen.

Each card has a message line now and the refusal is the kit's `refusal_response`
for that line: the heading "Opslaan is niet gelukt." with the rule's sentence
under it, nothing else swapped, nothing written.

**Measured at the answer of the route, as the screen gets it** (`tests/_refusal`):
an HTML 422 that htmx swaps, the sentence in the banner, and the message line it
is sent to — which must be the line of the card that was saved. That the line
stands inside its card and in view at 390 px is the browser test's
(`tests_e2e/members/test_household_cards_say_why.py`).

Two answers were no refusal until this issue and are one now, each red before:
an e-mail address that is none was stored as typed, and a relation outside the
list on a person's card was dropped without a word.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import (
    Address,
    ContactDetail,
    MemberPerson,
    Person,
    PostalCode,
    new_contact_detail,
)
from tests._refusal import heading, message_line, said
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

TAKEN = "bezet-1831@example.com"


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
NEW |= _person(0, "Hanne", email="hanne-1831@example.com", mobile="0470 00 00 01")
NEW |= _person(1, "Bram", gender_code="M")
ADDRESS = {"street": "Proefstraat", "house_number": "12", "bus_number": "", "postal_code": "2399"}
CARD = {name[3:]: value for name, value in _person(9, "Bram", gender_code="M").items()}
CARD |= {"relation_type": "PARTNER"}


class World:
    household: int
    main: int
    partner: int
    headers: dict[str, str]


@pytest.fixture
def world(client, db_session) -> World:
    """A household of a main member and a partner, made through the screen, and
    one person outside it who holds an e-mail address."""
    db_session.add(PostalCode(postal_code="2399", municipality="Proefdorp"))
    outsider = Person(first_name="Buiten", last_name="Staander")
    db_session.add(outsider)
    db_session.flush()
    db_session.add(new_contact_detail(db_session, outsider, "EMAIL", TAKEN, is_primary=True))
    db_session.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    w = World()
    w.headers = {"X-CSRF-Token": csrf_token_for(value)}
    made = client.post("/admin/leden", data=NEW, headers=w.headers)
    assert made.status_code == 204, made.text
    w.household = int(made.headers["HX-Redirect"].rsplit("/", 1)[-1])
    links = (
        db_session.query(MemberPerson)
        .filter(MemberPerson.member_id == w.household)
        .order_by(MemberPerson.id)
        .all()
    )
    w.main, w.partner = links[0].person_id, links[1].person_id
    return w


def _state(db) -> tuple:
    """Everything a card's save could have written, as one value to compare."""
    db.expire_all()
    people = [
        (p.id, p.first_name, p.last_name, str(p.date_of_birth), p.gender_code, bool(p.deleted_at))
        for p in db.query(Person).execution_options(include_deleted=True).order_by(Person.id)
    ]
    links = [
        (m.person_id, str(m.relation_type))
        for m in db.query(MemberPerson).order_by(MemberPerson.id)
    ]
    places = [
        (a.street, a.house_number, a.postal_code_id) for a in db.query(Address).order_by(Address.id)
    ]
    contacts = [(c.person_id, c.value) for c in db.query(ContactDetail).order_by(ContactDetail.id)]
    return people, links, places, contacts


ADDRESS_RULE = "Een adres heeft een straat, een huisnummer en een postcode nodig."
DETAILS_RULE = "Geboortedatum en geslacht zijn verplicht voor elk gezinslid."
NAME_RULE = "Voornaam en achternaam zijn verplicht."
LENGTH_RULE = "Een naam is ten hoogste 100 tekens lang."
DATE_RULE = "Vul een geldige geboortedatum in."
GENDER_RULE = "Kies een geslacht uit de lijst."
ONE_MAIN = "Een gezin heeft één hoofdlid."
RELATION_RULE = "Kies een relatie uit de lijst."
IN_USE = "Dit e-mailadres is al in gebruik door iemand anders."
NO_ADDRESS = "Vul een geldig e-mailadres in."
MAIN_STAYS = "Een gezin heeft een hoofdlid nodig."

#: (case, the card, what is sent beside a complete form, the sentence)
CASES = [
    ("address_no_street", "address", {"street": "  "}, ADDRESS_RULE),
    ("address_no_house_number", "address", {"house_number": ""}, ADDRESS_RULE),
    ("address_unknown_postal_code", "address", {"postal_code": "9999"}, "Onbekende postcode: 9999"),
    ("card_no_first_name", "card", {"first_name": "  "}, NAME_RULE),
    ("card_name_too_long", "card", {"last_name": "x" * 101}, LENGTH_RULE),
    ("card_date_that_is_none", "card", {"date_of_birth": "32-13-2020"}, DATE_RULE),
    ("card_no_date_of_birth", "card", {"date_of_birth": ""}, DETAILS_RULE),
    ("card_no_gender", "card", {"gender_code": ""}, DETAILS_RULE),
    ("card_unknown_gender", "card", {"gender_code": "Q"}, GENDER_RULE),
    ("card_second_main_member", "card", {"relation_type": "HOOFDLID"}, ONE_MAIN),
    ("card_address_of_someone_else", "card", {"email": TAKEN}, IN_USE),
    ("add_no_last_name", "add", {"last_name": ""}, NAME_RULE),
    ("add_name_too_long", "add", {"first_name": "x" * 101}, LENGTH_RULE),
    ("add_date_that_is_none", "add", {"date_of_birth": "gisteren"}, DATE_RULE),
    ("add_no_date_of_birth", "add", {"date_of_birth": ""}, DETAILS_RULE),
    ("add_second_main_member", "add", {"relation_type": "HOOFDLID"}, ONE_MAIN),
    ("add_address_of_someone_else", "add", {"email": TAKEN}, IN_USE),
]
#: No refusal until #1831 — stored as typed, or dropped without a word.
NEW_REFUSALS = [
    ("card_relation_outside_the_list", "card", {"relation_type": "TANTE"}, RELATION_RULE),
    ("card_address_that_is_none", "card", {"email": "geen-adres"}, NO_ADDRESS),
    ("add_address_that_is_none", "add", {"email": "geen-adres"}, NO_ADDRESS),
]


def _post(client, w: World, card: str, changes: dict):
    """Post one card's form; returns the answer and the message line it owns."""
    base = f"/admin/leden/gezin/{w.household}"
    if card == "address":
        return client.post(
            f"{base}/adres", data=ADDRESS | changes, headers=w.headers
        ), "#adres-melding"
    if card == "card":
        path, line = f"{base}/persoon/{w.partner}", f"#persoon-{w.partner}-melding"
        return client.post(path, data=CARD | changes, headers=w.headers), line
    path, line = f"{base}/personen", "#persoon-toevoegen-melding"
    return client.post(path, data=CARD | changes, headers=w.headers), line


@pytest.mark.parametrize(("case", "card", "changes", "sentence"), CASES + NEW_REFUSALS)
def test_a_card_says_why_in_its_own_line_and_writes_nothing(
    client, db_session, world, case, card, changes, sentence
):
    before = _state(db_session)

    answer, line = _post(client, world, card, changes)

    assert answer.status_code == 422, (case, answer.status_code, answer.text[:200])
    assert heading(answer) == "Opslaan is niet gelukt."
    assert said(answer) == [sentence]
    assert message_line(answer) == line, "the sentence goes to another card's line"
    assert _state(db_session) == before, f"{case}: something was written"


def test_deleting_the_main_member_says_why_in_his_card(client, db_session, world):
    before = _state(db_session)

    answer = client.post(
        f"/admin/leden/gezin/{world.household}/persoon/{world.main}/verwijderen",
        headers=world.headers,
    )

    assert answer.status_code == 422
    assert said(answer) == [MAIN_STAYS]
    assert message_line(answer) == f"#persoon-{world.main}-melding"
    assert _state(db_session) == before


def test_a_card_that_is_not_there_is_no_refusal(client, db_session, world):
    """A household or a person that does not exist stays a 404: there is no card
    to say anything in."""
    answer = client.post(
        f"/admin/leden/gezin/{world.household}/persoon/999999",
        data=CARD,
        headers=world.headers,
    )

    assert answer.status_code == 404
    assert answer.json() == {"detail": "Person not found"}


def test_every_card_carries_its_message_line_once(client, db_session, world):
    page = client.get(f"/admin/leden/gezin/{world.household}").text

    for line in (
        "adres-melding",
        f"persoon-{world.main}-melding",
        f"persoon-{world.partner}-melding",
        "persoon-toevoegen-melding",
    ):
        assert page.count(f'id="{line}" data-form-message') == 1, line


def test_a_good_save_answers_the_card_with_an_empty_line(client, db_session, world):
    """The card is redrawn by its good answer, and its message line with it: a
    sentence of an earlier refusal does not stay."""
    answer, _line = _post(client, world, "card", {"first_name": "Bram-Jan"})

    assert answer.status_code == 200
    assert f'<div id="persoon-{world.partner}-melding" data-form-message' in answer.text
    assert "data-save-refusal" not in answer.text
