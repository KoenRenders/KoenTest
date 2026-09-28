"""#1246 — the public Word lid form takes several e-mail addresses per person.

Since v2.6.0 a person's addresses are rows (#1174, #1219), on the admin side and in
the family portal. The public form still drew one field, because the shared
`person_fields` macro keeps `include_email=True` by default and this form did not
pass `False`. A family could only add a second address after its first login.

Now the form draws rows with the portal's fragment. **The first address is the
primary one** (Koen, 28 September 2026): it keeps the plain `m<i>_email` name —
what the JSON API and the admin create screen already send — carries the
"hoofdadres" label and has no remove button; extra rows are `m<i>_email_new_<n>`.

These tests post the form the way the browser does. That the rows reach the
database in a committed transaction, read through a second connection, is the
e2e test's job (`tests_e2e/test_word_lid_email_rows.py`): inside this suite the
request shares the test's session, which cannot tell a flush from a commit.

Broken on purpose to check these tests can go red (run, then restored):
  - `include_email=False` removed from `_lid_persoon_rij.html` → the form test
    fails: the macro draws its own `m0_email` beside the first row, two fields;
  - the `extra_emails` line removed from `create_family_with_members` (the loop
    over `person_data.extra_emails` reduced to the primary address) → the
    two-address test fails with only the primary stored, and the login test
    with "the second address does not log in".
"""

from __future__ import annotations

import re

import pytest

from app.domains.mdm.api import ContactDetail, Person

pytestmark = pytest.mark.ui_serverrendered


def _form(email: str, *extra: str, **overrides) -> dict:
    data = {
        "m0_first_name": "Rij",
        "m0_last_name": "Proef-1246",
        "m0_date_of_birth": "1985-05-05",
        "m0_gender_code": "F",
        "m0_mobile": "0470000001",
        "m0_relation_type": "HOOFDLID",
        "m0_email": email,
        "street": "Proefstraat",
        "house_number": "1",
        "postal_code": "",
        "payment_method": "transfer",
    }
    for n, address in enumerate(extra, start=1):
        data[f"m0_email_new_{1727000000000 + n}"] = address
    data.update(overrides)
    return data


@pytest.fixture
def postal_code(db_session):
    from app.domains.mdm.api import PostalCode

    pc = db_session.query(PostalCode).first()
    if pc is None:
        pc = PostalCode(postal_code="9999", municipality="Proef")
        db_session.add(pc)
        db_session.flush()
    return pc.postal_code


def _addresses(db, email: str) -> dict[str, bool]:
    """The e-mail rows of the person who owns `email`, as {value: is_primary}."""
    db.expire_all()
    person_id = db.query(ContactDetail.person_id).filter(ContactDetail.value == email).scalar()
    assert person_id, f"no person was stored with {email}"
    person = db.get(Person, person_id)
    return {
        c.value: bool(c.is_primary)
        for c in person.contact_details
        if c.contact_type_code == "EMAIL"
    }


def test_the_form_draws_rows_and_one_primary_field(client):
    html = client.get("/lid-worden").text
    fields = re.findall(r'name="m0_email"', html)
    assert len(fields) == 1, f"expected one primary e-mail field, found {len(fields)}"
    assert 'hx-get="/lid-worden/email-rij"' in html, "no button to add an address"
    start = html.find('id="m0_email"')
    assert start != -1, "the first e-mail row is not on the page"
    end = html.find("data-email-rij", start)
    first_row = html[start : end if end != -1 else start + 2000]
    assert "hoofdadres" in first_row, "the first row carries no primary label"
    assert "Verwijderen" not in first_row, "the primary row must not be removable"


def test_an_added_row_is_a_removable_extra_address(client):
    html = client.get("/lid-worden/email-rij?member=0&index=1727000000001&nummer=2").text
    assert 'name="m0_email_new_1727000000001"' in html
    assert "hoofdadres" not in html, "an added row is never the primary address"
    assert "Verwijderen" in html


def test_two_addresses_are_stored_with_the_first_as_primary(client, db_session, postal_code):
    first, second = "rij.een-1246@example.com", "rij.twee-1246@example.com"
    response = client.post("/lid-worden", data=_form(first, second, postal_code=postal_code))
    assert response.status_code == 200, response.text[:500]
    assert _addresses(db_session, first) == {first: True, second: False}


def test_one_address_is_the_primary_one(client, db_session, postal_code):
    only = "rij.alleen-1246@example.com"
    client.post("/lid-worden", data=_form(only, postal_code=postal_code))
    assert _addresses(db_session, only) == {only: True}


def test_the_same_address_twice_is_stored_once(client, db_session, postal_code):
    address = "rij.dubbel-1246@example.com"
    client.post("/lid-worden", data=_form(address, address.upper(), postal_code=postal_code))
    assert _addresses(db_session, address) == {address: True}


def test_an_empty_extra_row_adds_nothing(client, db_session, postal_code):
    address = "rij.leeg-1246@example.com"
    client.post("/lid-worden", data=_form(address, "", postal_code=postal_code))
    assert _addresses(db_session, address) == {address: True}


def test_the_second_address_logs_in(client, db_session, postal_code):
    """The reason this issue exists: every address logs in (#1174)."""
    from app.domains.auth.api import login_person_for_email

    first, second = "rij.login1-1246@example.com", "rij.login2-1246@example.com"
    client.post("/lid-worden", data=_form(first, second, postal_code=postal_code))
    db_session.expire_all()
    owner = db_session.query(ContactDetail.person_id).filter(ContactDetail.value == first).scalar()
    person = login_person_for_email(db_session, second)
    assert person is not None, "the second address does not log in"
    assert getattr(person, "id", person) == owner


def test_extra_rows_survive_a_validation_error(client, postal_code):
    """Without a postal code the form comes back; what was typed stays."""
    first, second = "rij.terug1-1246@example.com", "rij.terug2-1246@example.com"
    html = client.post("/lid-worden", data=_form(first, second, postal_code="")).text
    assert f'value="{first}"' in html
    assert f'value="{second}"' in html
