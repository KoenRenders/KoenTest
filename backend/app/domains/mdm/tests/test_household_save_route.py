"""The portal's one save route (CR-11 pilot B, #1590).

`POST /leden/gezin` with the whole form is how the page "Mijn gezin" writes
its persons, their e-mail addresses and the address. What the save itself
guarantees — one transaction, every refusal, every history row — is proven on
the service (`mdm/tests/test_household_save.py`); here the wiring: the form's
names reach the save, a refusal answers in the page's message line and leaves
the form alone, and only a member of the household gets in.

Broken on purpose, each seen red: the route answering a refusal with the whole
page (the banner test finds the page); the retarget header left out; the CSRF
check dropped from the member's door; and the route saving another household
than the signed-in member's.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import (
    Address,
    ContactDetail,
    Member,
    MemberPerson,
    Person,
    PostalCode,
)

pytestmark = pytest.mark.ui_serverrendered

MAIL = "an.gezin@example.com"
MOBILE = "0470 00 00 01"


@pytest.fixture
def world(db_session):
    """An (main member, signed in, with an address) and Cas (child)."""
    db = db_session
    if db.query(PostalCode).filter(PostalCode.postal_code == "2400").first() is None:
        db.add(PostalCode(postal_code="2400", municipality="Mol"))
        db.flush()
    household = Member()
    db.add(household)
    db.flush()
    people = {}
    for name, relation in (("An", "HOOFDLID"), ("Cas", "KIND")):
        person = Person(
            first_name=name, last_name="Voorbeeld", date_of_birth=date(1980, 1, 1), gender_code="M"
        )
        db.add(person)
        db.flush()
        db.add(MemberPerson(member_id=household.id, person_id=person.id, relation_type=relation))
        people[name] = person
    postal = db.query(PostalCode).filter(PostalCode.postal_code == "2400").one()
    db.add(
        Address(
            person_id=people["An"].id,
            street="Dorpsstraat",
            house_number="1",
            postal_code_id=postal.id,
        )
    )
    mail = ContactDetail(
        person_id=people["An"].id, contact_type_code="EMAIL", value=MAIL, is_primary=True
    )
    db.add(mail)
    db.add(
        ContactDetail(
            person_id=people["An"].id, contact_type_code="MOBILE", value=MOBILE, is_primary=True
        )
    )
    db.commit()
    return {"household": household, "mail": mail, **people}


def _sign_in(client, address: str = MAIL) -> dict:
    value = make_session_value(address)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _form(world, **changes) -> list[tuple[str, str]]:
    """The household as the page sends it when nothing was touched; `changes`
    replace or add fields by name."""
    an, cas, mail = world["An"], world["Cas"], world["mail"]
    fields = {
        f"h.{an.id}.first_name": "An",
        f"h.{an.id}.last_name": "Voorbeeld",
        f"h.{an.id}.date_of_birth": "1980-01-01",
        f"h.{an.id}.gender_code": "M",
        f"h.{an.id}.mobile": MOBILE,
        f"e.{mail.id}.value": MAIL,
        f"e_primary.{an.id}": str(mail.id),
        f"h.{cas.id}.first_name": "Cas",
        f"h.{cas.id}.last_name": "Voorbeeld",
        f"h.{cas.id}.date_of_birth": "1980-01-01",
        f"h.{cas.id}.gender_code": "M",
        "address.street": "Dorpsstraat",
        "address.house_number": "1",
        "address.bus_number": "",
        "address.postal_code": "2400",
    }
    fields.update(changes)
    order = [("h_order", str(an.id)), ("h_order", str(cas.id)), (f"e_order.{an.id}", str(mail.id))]
    return order + list(fields.items())


def _post(client, headers, fields):
    from urllib.parse import urlencode

    return client.post(
        "/leden/gezin",
        content=urlencode(fields),
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
    )


def test_one_post_saves_a_person_an_address_and_an_e_mail_address(client, db_session, world):
    headers = _sign_in(client)
    an, cas = world["An"], world["Cas"]
    fields = _form(
        world,
        **{
            f"h.{cas.id}.first_name": "Casper",
            "address.street": "Kerkstraat",
            "e.nx1.value": "an.werk@example.com",
        },
    ) + [(f"e_order.{an.id}", "nx1")]
    answer = _post(client, headers, fields)
    assert answer.status_code == 200, answer.text[:300]
    assert "<html" in answer.text.lower(), "the page, as every portal write answers"
    assert 'data-mode="read"' in answer.text and 'id="gezin-form"' not in answer.text
    assert answer.headers["HX-Push-Url"] == "/leden/gezin", "the address bar leaves the edit mode"
    assert 'hx-swap-oob="afterbegin:#toasts"' in answer.text and "Opgeslagen ✓" in answer.text
    db_session.expire_all()
    assert db_session.get(Person, cas.id).first_name == "Casper"
    assert db_session.get(Person, an.id).address.street == "Kerkstraat"
    mails = {
        c.value: c.is_primary
        for c in db_session.get(Person, an.id).contact_details
        if c.contact_type_code == "EMAIL"
    }
    assert mails == {MAIL: True, "an.werk@example.com": False}


def test_a_refusal_answers_with_the_banner_alone_and_writes_nothing(client, db_session, world):
    """An HTML 422 for the page's message line: every refused field as a link to
    it, nothing of the page, nothing written — the good change in the same save
    neither."""
    headers = _sign_in(client)
    an, cas = world["An"], world["Cas"]
    answer = _post(
        client,
        headers,
        _form(
            world,
            **{
                f"h.{cas.id}.first_name": "",
                f"h.{an.id}.date_of_birth": "31/02/1980",
                f"h.{an.id}.last_name": "Niet bewaard",
                "address.postal_code": "9999",
            },
        ),
    )
    assert answer.status_code == 422
    assert answer.headers["HX-Retarget"] == "#gezin-melding"
    assert answer.headers["HX-Reswap"].startswith("innerHTML")
    # Out of whatever the form selects for its good answer: the banner itself.
    assert answer.headers["HX-Reselect"] == "[data-save-refusal]"
    assert "<html" not in answer.text.lower(), "the banner alone: the form keeps what was typed"
    assert "Opslaan kan nog niet: controleer 3 velden." in answer.text
    assert re.findall(r'data-error-for="([^"]+)"', answer.text) == [
        f"h.{an.id}.date_of_birth",
        f"h.{cas.id}.first_name",
        "address.postal_code",
    ]
    for message in (
        "Ongeldige geboortedatum.",
        "Voornaam en achternaam zijn verplicht.",
        "Onbekende postcode: 9999",
    ):
        assert message in answer.text
    db_session.expire_all()
    assert db_session.get(Person, cas.id).first_name == "Cas"
    assert db_session.get(Person, an.id).last_name == "Voorbeeld"


def test_the_main_member_without_a_mobile_is_named_at_that_field(client, db_session, world):
    """The rule Word lid asks too, at this door (#1590): the banner names the
    main member's Gsm field, the child — who has none either — is not asked,
    and the number that was there stays. The same form with the number is the
    first test of this file, so the emptied field is the cause."""
    headers = _sign_in(client)
    an = world["An"]
    answer = _post(client, headers, _form(world, **{f"h.{an.id}.mobile": "  "}))
    assert answer.status_code == 422
    assert re.findall(r'data-error-for="([^"]+)"', answer.text) == [f"h.{an.id}.mobile"]
    assert "Mobiel nummer is verplicht voor het hoofdgezinslid." in answer.text
    assert "Opslaan kan nog niet: controleer 1 veld." in answer.text
    db_session.expire_all()
    stored = [
        c.value
        for c in db_session.get(Person, an.id).contact_details
        if c.contact_type_code == "MOBILE"
    ]
    assert stored == [MOBILE]


def test_the_save_needs_a_session_and_the_csrf_token(client, db_session, world):
    assert _post(client, {}, _form(world)).status_code == 401, "no session"
    _sign_in(client)
    assert _post(client, {}, _form(world)).status_code == 403, "a session without the token"


def test_a_member_saves_only_their_own_household(client, db_session, world):
    """The household is the signed-in member's — never one the form names. A
    person of another household sent as a row is refused as that row."""
    db = db_session
    other = Member()
    db.add(other)
    db.flush()
    stranger = Person(
        first_name="Vreemd", last_name="Elders", date_of_birth=date(1970, 1, 1), gender_code="M"
    )
    db.add(stranger)
    db.flush()
    db.add(MemberPerson(member_id=other.id, person_id=stranger.id, relation_type="HOOFDLID"))
    db.commit()
    headers = _sign_in(client)
    fields = _form(
        world, **{f"h.{stranger.id}.first_name": "Gekaapt", f"h.{stranger.id}.last_name": "Elders"}
    )
    fields.append(("h_order", str(stranger.id)))
    answer = _post(client, headers, fields)
    assert answer.status_code == 422
    assert re.findall(r'data-error-for="([^"]+)"', answer.text) == [f"h.{stranger.id}"]
    db.expire_all()
    assert db.get(Person, stranger.id).first_name == "Vreemd"
    assert db.query(MemberPerson).filter_by(member_id=other.id).count() == 1
