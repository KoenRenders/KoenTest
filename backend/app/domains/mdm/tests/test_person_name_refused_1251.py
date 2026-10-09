"""#1251, after cut C6-2: a person without a first or a last name is refused, not a crash.

The two person forms of the Leden screen — the card of a person and "persoon
toevoegen" — mark the first and the last name as required. The object keeps
that promise (`Person._name_not_blank`), but the two functions the forms call
did not answer its refusal: the request ended in a 500. They answer it now as
they answer their other refusals — a 422 with the object's own words.

**What is measured here, and what is not.** The answer of the server: its status,
the words in its body, and that nothing was written. The answer is a JSON 422,
and the Leden screen does not swap a JSON 422 into the page: in a browser the
board member sees the general toast ("Er ging iets mis; je wijziging is niet
bewaard."), not these words — and gets there only with the field's `required`
removed. Showing the reason at the field is a change of the screen of its own.

Red before the repair (run on the code of cut C6-2): all four cases raised
`MasterDataError` out of the request. The nine steps below them — a birth date
that is no date, an unknown gender code, a name longer than the column, an
unknown relation — raised a `ValidationError`, an `IntegrityError` or a
`DataError` the same way, and are refused now with the words the master CLI
chose (9 October 2026).
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Person, PersonHistory
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family

pytestmark = pytest.mark.ui_serverrendered

WORDS = "Voornaam en achternaam zijn verplicht."
FIELDS = {
    "first_name": "Proef",
    "last_name": "Persoon",
    "date_of_birth": "1980-01-01",
    "gender_code": "M",
    "phone": "",
    "mobile": "",
}


def _headers(client) -> dict[str, str]:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


@pytest.mark.parametrize("blank", ["first_name", "last_name"])
def test_a_persons_card_without_a_name_is_refused(client, db_session, blank):
    household, main = create_test_family(db_session, email="naam-kaart-1251@example.com")
    db_session.commit()
    before = (main.first_name, main.last_name)
    history = db_session.query(PersonHistory).count()

    response = client.post(
        f"/admin/leden/gezin/{household.id}/persoon/{main.id}",
        data={**FIELDS, "relation_type": "HOOFDLID", blank: ""},
        headers=_headers(client),
    )

    assert response.status_code == 422, response.text[:200]
    assert response.json()["detail"] == WORDS
    db_session.expire_all()
    person = db_session.get(Person, main.id)
    assert (person.first_name, person.last_name) == before, "the name was changed after all"
    assert db_session.query(PersonHistory).count() == history, "a history row was written"


@pytest.mark.parametrize("blank", ["first_name", "last_name"])
def test_a_new_person_without_a_name_is_refused(client, db_session, blank):
    household, _main = create_test_family(db_session, email="naam-nieuw-1251@example.com")
    db_session.commit()
    persons = db_session.query(Person).count()

    response = client.post(
        f"/admin/leden/gezin/{household.id}/personen",
        data={**FIELDS, "relation_type": "KIND", blank: ""},
        headers=_headers(client),
    )

    assert response.status_code == 422, response.text[:200]
    assert response.json()["detail"] == WORDS
    assert db_session.query(Person).count() == persons, "a person was added after all"


def test_a_person_with_both_names_is_still_stored(client, db_session):
    """The way that is not refused, on both forms: without it a function that
    refuses everything would pass the four tests above."""
    household, main = create_test_family(db_session, email="naam-goed-1251@example.com")
    db_session.commit()
    headers = _headers(client)
    base = f"/admin/leden/gezin/{household.id}"
    persons = db_session.query(Person).count()

    changed = client.post(
        f"{base}/persoon/{main.id}",
        data={**FIELDS, "relation_type": "HOOFDLID", "last_name": "Anders"},
        headers=headers,
    )
    added = client.post(
        f"{base}/personen", data={**FIELDS, "relation_type": "KIND"}, headers=headers
    )

    assert (changed.status_code, added.status_code) == (200, 200)
    db_session.expire_all()
    assert db_session.get(Person, main.id).last_name == "Anders"
    assert db_session.query(Person).count() == persons + 1


# ── Four more values that ended in a 500 (the master CLI's words, 9 October 2026) ──

DATE = "Vul een geldige geboortedatum in."
GENDER = "Kies een geslacht uit de lijst."
LENGTH = "Een naam is ten hoogste 100 tekens lang."
RELATION = "Kies een relatie uit de lijst."

OTHER = [
    # (case, the field posted wrong, its value, the words)
    ("a birth date that is no date", "date_of_birth", "geen-datum", DATE),
    ("a gender code that is not of the list", "gender_code", "Q", GENDER),
    ("a first name longer than the column", "first_name", "x" * 101, LENGTH),
    ("a last name longer than the column", "last_name", "x" * 101, LENGTH),
]


def test_the_sentence_about_the_length_is_true_of_both_columns():
    """The words name a number; the two columns must have it."""
    columns = Person.__table__.c
    assert (columns.first_name.type.length, columns.last_name.type.length) == (100, 100)


@pytest.mark.parametrize("case, field, value, words", OTHER, ids=[c[0] for c in OTHER])
def test_a_persons_card_with_it_is_refused(client, db_session, case, field, value, words):
    household, main = create_test_family(db_session, email="waarde-kaart-1251@example.com")
    db_session.commit()
    before = (main.first_name, main.last_name, main.date_of_birth, main.gender_code)
    history = db_session.query(PersonHistory).count()

    response = client.post(
        f"/admin/leden/gezin/{household.id}/persoon/{main.id}",
        data={**FIELDS, "relation_type": "HOOFDLID", field: value},
        headers=_headers(client),
    )

    assert response.status_code == 422, response.text[:200]
    assert response.json()["detail"] == words
    db_session.expire_all()
    person = db_session.get(Person, main.id)
    assert (person.first_name, person.last_name, person.date_of_birth, person.gender_code) == (
        before
    ), "the person was changed after all"
    assert db_session.query(PersonHistory).count() == history, "a history row was written"


@pytest.mark.parametrize(
    "case, field, value, words",
    [*OTHER, ("a relation that is not of the list", "relation_type", "XYZ", RELATION)],
    ids=[*[c[0] for c in OTHER], "a relation that is not of the list"],
)
def test_a_new_person_with_it_is_refused(client, db_session, case, field, value, words):
    household, _main = create_test_family(db_session, email="waarde-nieuw-1251@example.com")
    db_session.commit()
    persons = db_session.query(Person).count()

    response = client.post(
        f"/admin/leden/gezin/{household.id}/personen",
        data={**FIELDS, "relation_type": "KIND", field: value},
        headers=_headers(client),
    )

    assert response.status_code == 422, response.text[:200]
    assert response.json()["detail"] == words
    assert db_session.query(Person).count() == persons, "a person was added after all"


def test_a_name_of_exactly_the_columns_length_is_stored(client, db_session):
    """The edge that is not refused: a hundred characters fit."""
    household, main = create_test_family(db_session, email="waarde-rand-1251@example.com")
    db_session.commit()

    response = client.post(
        f"/admin/leden/gezin/{household.id}/persoon/{main.id}",
        data={**FIELDS, "relation_type": "HOOFDLID", "last_name": "x" * 100},
        headers=_headers(client),
    )

    assert response.status_code == 200, response.text[:200]
    db_session.expire_all()
    assert db_session.get(Person, main.id).last_name == "x" * 100


def test_the_name_fields_stop_where_the_server_refuses(client, db_session):
    """A name longer than the column is the one of these values a browser could
    send, so the two name fields of both person forms carry `maxlength` — the
    number the rule refuses at (`PERSON_NAME_MAX`), not a second literal. Read
    from the page the server renders: the card of the one person and the form of
    a new one, four fields."""
    import re

    from app.domains.mdm.api import PERSON_NAME_MAX

    household, _main = create_test_family(db_session, email="veldlengte-1251@example.com")
    db_session.commit()
    _headers(client)

    page = client.get(f"/admin/leden/gezin/{household.id}").text

    fields = re.findall(r'<input[^>]*name="(?:first_name|last_name)"[^>]*>', page)
    assert len(fields) == 4, f"{len(fields)} name fields on the page — is this test still looking?"
    without = [field for field in fields if f'maxlength="{PERSON_NAME_MAX}"' not in field]
    assert not without, without
    assert PERSON_NAME_MAX == 100
