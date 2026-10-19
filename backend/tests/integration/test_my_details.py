"""Mijn gegevens: a person's own details (CR-22 S6a, #1710; R16, R17; C6 T15).

- the page shows the person block of Mijn gezin for ONE person: first name, last
  name, mobile number and the e-mail rows — no birth date, gender, telephone,
  relation or address (R17);
- **a name changed here shows in Mijn gezin at once, and the other way round**
  (T15): one person, one save path;
- the save writes this person only: a blank name is refused at its field with
  nothing written, and a form that names another person is refused whole;
- e-mail rows and the mobile number go through the household's own helpers;
- a person without a household — an account, from S4a on — saves without
  birth date or gender: those are not this page's to ask.

Red (each restored after): `own=True` taken off the block in `my_details.html`
→ the fields test finds a birth date; `save_person` writing and committing the
mobile row before the name is judged → the refusal test finds a mobile number
stored; the key check taken out of `save_person` → the other person's name is
written.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import ContactDetail, Person, new_contact_detail
from app.domains.membership.api import person_block as _person_block
from tests._sites import at_tenant
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

EMAIL = "lid-1710@example.org"
ACCOUNT = "account-1899@example.org"


def person_block(person, *, edit: bool = False):
    """The block as the page builds it. The code lists play no part in what these
    tests send or read, so they are empty here."""
    return _person_block(person, {"gender_codes": []}, short_date=str, edit=edit)


def _main(html: str) -> str:
    return html[html.index('<main id="main"') : html.index("</main>")]


@pytest.fixture
def member(client, db_session):
    _household, person = create_test_family(db_session, email=EMAIL)
    at_tenant(db_session, _household)  # CR-26 F9
    person.first_name, person.last_name = "Emma", "Voorbeeld"
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(EMAIL))
    return person


def _csrf(client) -> dict:
    """The CSRF token of the session the client carries."""
    return {"X-CSRF-Token": csrf_token_for(client.cookies.get(SESSION_COOKIE))}


def _form(person, block, **changes) -> dict:
    """What the page's form sends for this person, with `changes` typed in."""
    key = block.person.key
    data = {
        "h_order": key,
        f"h.{key}.first_name": block.person.first_name,
        f"h.{key}.last_name": block.person.last_name,
        f"h.{key}.date_of_birth": block.person.date_of_birth,
        f"h.{key}.gender_code": block.person.gender_code,
        f"h.{key}.mobile": block.person.mobile,
        f"h.{key}.phone": block.person.phone,
        f"e_order.{key}": [m.key for m in block.person.emails],
        f"e_primary.{key}": block.person.primary_key,
    }
    for mail in block.person.emails:
        data[f"e.{mail.key}.value"] = mail.value
    for name, value in changes.items():
        data[f"h.{key}.{name}"] = value
    return data


def _save(client, data: dict):
    return client.post("/mijn/gegevens", data=data, headers=_csrf(client))


def test_without_a_session_the_page_asks_to_sign_in(client):
    response = client.get("/mijn/gegevens", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/aanmelden?terug=/mijn/gegevens"
    assert client.post("/mijn/gegevens", data={}).status_code == 401


def test_the_page_shows_the_own_block_and_nothing_of_the_household(client, member):
    read = _main(client.get("/mijn/gegevens").text)
    assert "Emma" in read and "Voorbeeld" in read and EMAIL in read
    assert re.search(r"<h1[^>]*>\s*Mijn gegevens\s*</h1>", read)
    assert 'href="/mijn/gegevens?bewerken=1"' in read and "data-to-household" in read
    edit = _main(client.get("/mijn/gegevens?bewerken=1").text)
    key = str(member.id)
    names = set(re.findall(rf'name="h\.{key}\.([a-z_]+)"', edit))
    # #1899 (CR-22 R17 as corrected on 10 October 2026): the whole person card
    # without the relation — birth date, gender and telephone included.
    assert names == {
        "first_name",
        "last_name",
        "date_of_birth",
        "gender_code",
        "mobile",
        "phone",
    }, names
    assert f'name="e_order.{key}"' in edit and 'hx-post="/mijn/gegevens"' in edit
    # R17: nothing of the household — no address and no relation — in neither mode.
    for word in ("Postcode", "Straat", "Relatie", "Hoofdlid", "Partner"):
        assert word not in read and word not in edit, word
    # The menu marks this page.
    menu = edit[edit.index("data-account-page-menu") : edit.index("</nav>")]
    assert re.search(
        r'href="/mijn/gegevens" data-account-item="member" class="site-drawer-row" aria-current="page"',
        menu,
    )


def test_a_name_changed_here_shows_in_mijn_gezin_and_back(client, db_session, member):
    """T15."""
    block = person_block(member, edit=True)
    answer = _save(client, _form(member, block, first_name="Emmanuelle"))
    assert answer.status_code == 200, answer.text[:300]
    assert "Emmanuelle" in _main(answer.text) and "data-toast" in answer.text
    assert "Emmanuelle" in _main(client.get("/leden/gezin").text)
    # And back: the household's own save, the same person.
    db_session.expire_all()
    person = db_session.get(Person, member.id)
    key = str(person.id)
    mails = [c for c in person.contact_details if c.contact_type_code == "EMAIL"]
    data = {
        "h_order": [key],
        f"h.{key}.first_name": "Emma",
        f"h.{key}.last_name": person.last_name,
        f"h.{key}.date_of_birth": person.date_of_birth.isoformat(),
        f"h.{key}.gender_code": person.gender_code,
        f"e_order.{key}": [str(c.id) for c in mails],
        f"e_primary.{key}": str(next(c.id for c in mails if c.is_primary)),
        **{f"e.{c.id}.value": c.value for c in mails},
    }
    saved = client.post("/leden/gezin", data=data, headers=_csrf(client))
    assert saved.status_code == 200, saved.text[:400]
    mine = _main(client.get("/mijn/gegevens").text)
    assert "Emma" in mine and "Emmanuelle" not in mine


def test_a_blank_name_is_refused_at_its_field_and_nothing_is_written(client, db_session, member):
    block = person_block(member, edit=True)
    answer = _save(
        client, _form(member, block, first_name="", last_name="Anders", mobile="0470 00 00 00")
    )
    assert answer.status_code == 422
    assert f"h.{member.id}.first_name" in answer.text, "the refusal does not name the field"
    db_session.expire_all()
    person = db_session.get(Person, member.id)
    assert (person.first_name, person.last_name) == ("Emma", "Voorbeeld")
    assert not any(c.contact_type_code == "MOBILE" for c in person.contact_details)


def test_the_mobile_number_and_the_e_mail_rows_are_written(client, db_session, member):
    block = person_block(member, edit=True)
    key = block.person.key
    data = _form(member, block, mobile="0470 11 22 33")
    data[f"e_order.{key}"] = [*data[f"e_order.{key}"], "nieuw1"]
    data["e.nieuw1.value"] = "tweede-1710@example.org"
    assert _save(client, data).status_code == 200
    db_session.expire_all()
    person = db_session.get(Person, member.id)
    rows = {(c.contact_type_code, c.value) for c in person.contact_details if c.deleted_at is None}
    assert ("MOBILE", "0470 11 22 33") in rows
    assert ("EMAIL", "tweede-1710@example.org") in rows and ("EMAIL", EMAIL) in rows
    read = _main(client.get("/mijn/gegevens").text)
    assert "tweede-1710@example.org" in read and "hoofdadres" in read


def test_an_e_mail_row_that_is_no_address_is_refused_at_its_row(client, db_session, member):
    """#1853: the rule of the contact detail, asked at the row's own field — and a
    refused save writes nothing, also not the mobile number typed beside it."""
    block = person_block(member, edit=True)
    key = block.person.key
    data = _form(member, block, mobile="0470 11 22 33")
    data[f"e_order.{key}"] = [*data[f"e_order.{key}"], "nieuw1"]
    data["e.nieuw1.value"] = "emma zonder adres"

    answer = _save(client, data)

    assert answer.status_code == 422
    assert "Vul een geldig e-mailadres in." in answer.text
    assert "e.nieuw1.value" in answer.text, "the refusal does not name the row's field"
    db_session.expire_all()
    person = db_session.get(Person, member.id)
    rows = {(c.contact_type_code, c.value) for c in person.contact_details if c.deleted_at is None}
    assert rows == {("EMAIL", EMAIL)}, rows


def test_a_form_that_names_another_person_is_refused_whole(client, db_session, member):
    _other_household, other = create_test_family(db_session, email="ander-1710@example.org")
    at_tenant(db_session, _other_household)  # CR-26 F9
    other.first_name = "Ander"
    db_session.commit()
    block = person_block(other, edit=True)
    answer = _save(client, _form(other, block, first_name="Gekaapt"))
    assert answer.status_code == 422
    db_session.expire_all()
    assert db_session.get(Person, other.id).first_name == "Ander"
    assert db_session.get(Person, member.id).first_name == "Emma"


def test_a_person_without_a_household_saves_without_birth_date_or_gender(db_session):
    """Birth date and gender are the household's questions (R17): this save does
    not ask them. From CR-22 S4a on such a person is an account; a member always
    has both — the object refuses a household person without them."""
    from app.domains.mdm.api import HouseholdSaveRefused, PersonRow, save_person

    person = Person(first_name="Noor", last_name="Voorbeeld")
    db_session.add(person)
    db_session.commit()
    row = PersonRow(
        key=str(person.id), first_name="Noor", last_name="Verbeterd", mobile="0470 99 88 77"
    )
    save_person(db_session, person, [row], actor=None)
    db_session.expire_all()
    stored = db_session.get(Person, person.id)
    assert stored.last_name == "Verbeterd" and stored.date_of_birth is None
    assert [c.value for c in stored.contact_details if c.contact_type_code == "MOBILE"] == [
        "0470 99 88 77"
    ]
    # A blank name is refused for him too, and nothing is written.
    with pytest.raises(HouseholdSaveRefused) as refused:
        save_person(
            db_session,
            stored,
            [PersonRow(key=str(stored.id), first_name="", last_name="X")],
            actor=None,
        )
    assert [e.field for e in refused.value.errors] == [f"h.{stored.id}.first_name"]
    db_session.expire_all()
    assert db_session.get(Person, person.id).last_name == "Verbeterd"


def test_the_block_reads_only_live_rows_main_address_first(db_session, member):
    db_session.add(
        ContactDetail(
            person_id=member.id,
            contact_type_code="EMAIL",
            value="extra-1710@example.org",
            is_primary=False,
        )
    )
    db_session.commit()
    db_session.refresh(member)
    block = person_block(member)
    assert [m.value for m in block.person.emails] == [EMAIL, "extra-1710@example.org"]
    assert (
        block.person.primary_key == block.person.emails[0].key and block.contact_required is False
    )


# ── #1899: the whole person card — birth date, gender and telephone ─────────────


@pytest.fixture
def account(client, db_session):
    """An account alone: a person who signs in and belongs to no household —
    without a birth date and a gender, as the sign-up of an account leaves him."""
    person = Person(first_name="Alex", last_name="Alleen")
    db_session.add(person)
    db_session.flush()
    db_session.add(
        new_contact_detail(db_session, person, "EMAIL", ACCOUNT, is_primary=True, confirmed=True)
    )
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(ACCOUNT))
    return person


def test_birth_date_gender_and_telephone_are_written(client, db_session, member):
    """CR-22 R17 as corrected on 10 October 2026: Mijn gegevens holds the whole
    person card. Red (restored after): `date_of_birth` and `gender_code` taken out
    of what `save_person` writes → the stored date is the old one."""
    block = person_block(member, edit=True)
    answer = _save(
        client,
        _form(member, block, date_of_birth="1985-06-07", gender_code="F", phone="014 12 34 56"),
    )
    assert answer.status_code == 200, answer.text[:300]
    db_session.expire_all()
    person = db_session.get(Person, member.id)
    assert person.date_of_birth.isoformat() == "1985-06-07" and str(person.gender_code) == "F"
    phones = [c.value for c in person.contact_details if c.contact_type_code == "PHONE"]
    assert len(phones) == 1 and "".join(ch for ch in phones[0] if ch.isdigit()) == "014123456"
    read = _main(client.get("/mijn/gegevens").text)
    assert "° 07-06-1985" in read


def test_a_person_of_a_household_is_asked_birth_date_and_gender(client, db_session, member):
    """Asked of a person in a household (#681), at the field that is missing, and
    nothing is written. Red (restored after): `details_required` always False in
    `save_person` → the empty date is stored."""
    block = person_block(member, edit=True)
    before = db_session.get(Person, member.id).date_of_birth
    answer = _save(client, _form(member, block, date_of_birth="", first_name="Anders"))
    assert answer.status_code == 422, answer.status_code
    assert f"h.{member.id}.date_of_birth" in answer.text
    db_session.expire_all()
    person = db_session.get(Person, member.id)
    assert person.date_of_birth == before and person.first_name == "Emma"
    edit = _main(client.get("/mijn/gegevens?bewerken=1").text)
    assert re.search(rf'name="h\.{member.id}\.date_of_birth"[^>]* required', edit)


def test_an_account_alone_is_not_asked_birth_date_and_gender(client, db_session, account):
    """Optional for an account without a household: the save goes through without
    them, the fields carry no star, and given, they are stored. Red (restored
    after): `details_required` always True in `save_person` → the save is refused."""
    edit = _main(client.get("/mijn/gegevens?bewerken=1").text)
    key = str(account.id)
    for name in ("date_of_birth", "gender_code"):
        field = re.search(rf'<(?:input|select)[^>]*name="h\.{key}\.{name}"[^>]*>', edit)
        assert field and " required" not in field.group(0), name
    block = person_block(account, edit=True)
    answer = _save(client, _form(account, block, first_name="Alexa"))
    assert answer.status_code == 200, answer.text[:300]
    db_session.expire_all()
    person = db_session.get(Person, account.id)
    assert person.first_name == "Alexa" and person.date_of_birth is None
    answer = _save(
        client,
        _form(
            account, person_block(person, edit=True), date_of_birth="1990-02-03", gender_code="M"
        ),
    )
    assert answer.status_code == 200, answer.text[:300]
    db_session.expire_all()
    assert db_session.get(Person, account.id).date_of_birth.isoformat() == "1990-02-03"
