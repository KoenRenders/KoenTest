"""Lid worden shows a signed-in account as the main member, with his own details (#1883).

Koen, 10 October 2026: he created himself an account, signed in, clicked "Lid
worden" — and got an empty form, where he expected to stand in it as the main
member with what the application already knows of him. And on 15 October 2026,
to whether the visitor may still change his own name, e-mail and mobile there:
"a" — they stand as his and are not editable on this form; he changes them on
Mijn gegevens. So nothing is silently overwritten, and no second person arises
from a typed address.

- signed in as an account: the main member's card shows his name, his e-mail
  address and his mobile as read values, and says where he changes them; what
  he still has to give (birth date, gender, the address) is asked;
- the door takes his own details, whatever a request posts in their place;
- signed out: the empty form, as before;
- point 3 of the issue: who has a household is offered no "Word lid" on the
  newsletter's public form either — the same source as the CMS's buttons.

Broken on purpose (16 October 2026, each put back): `own=` left out of the
GET's `signup_group` → the page test fails on an empty name field; `own=` left
out of the POST → the overwrite test fails on the posted name; the newsletter's
condition made `true` → the household's case fails on "Liever lid worden?".
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.mdm.api import Person, new_contact_detail
from tests.conftest import create_test_family, signup_fields

pytestmark = pytest.mark.ui_serverrendered

ADDRESS = "account-1883@example.com"


def _account(db) -> Person:
    """A person without a household, as "Account aanmaken" makes one: a name, a
    confirmed address and a mobile number — no birth date, no gender."""
    person = Person(first_name="Acco", last_name="Unt")
    db.add(person)
    db.flush()
    db.add(new_contact_detail(db, person, "EMAIL", ADDRESS, is_primary=True, confirmed=True))
    db.add(new_contact_detail(db, person, "MOBILE", "0470001883", is_primary=True))
    db.commit()
    return person


def _main_card(html: str) -> str:
    start = html.index('id="hoofdlid"')
    return (
        html[start : html.index("</section>", start)]
        if "</section>" in html[start:]
        else html[start:]
    )


def test_a_signed_in_account_stands_in_the_form_as_the_main_member(client, db_session):
    _account(db_session)
    client.cookies.set(SESSION_COOKIE, make_session_value(ADDRESS))
    page = client.get("/lid-worden").text
    card = _main_card(page)

    for shown in ("Acco", "Unt", ADDRESS, "0470 00 18 83"):
        assert shown in card, shown
    # His own: read, not typed — no input for them on this form.
    for name in ("h.n0.first_name", "h.n0.last_name", "h.n0.mobile"):
        assert f'name="{name}"' not in card, name
    assert not re.search(r'name="e\.[^"]+\.value"', card), "an e-mail field to type in"
    assert "data-own-details" in card and "/mijn/gegevens" in card
    # What he still has to give is asked.
    for name in ("h.n0.date_of_birth", "h.n0.gender_code", "address.street"):
        assert f'name="{name}"' in page, name


def test_a_visitor_without_a_session_gets_the_empty_form(client, db_session):
    _account(db_session)
    client.cookies.clear()
    card = _main_card(client.get("/lid-worden").text)
    assert 'name="h.n0.first_name"' in card and 'name="h.n0.mobile"' in card
    assert "Acco" not in card and "data-own-details" not in card


def test_the_door_takes_his_own_details_whatever_is_posted(client, db_session):
    """A request that posts another name, address and number for the main member
    changes none of his and makes no second person."""
    account = _account(db_session)
    persons = db_session.query(Person).count()
    client.cookies.set(SESSION_COOKIE, make_session_value(ADDRESS))

    answer = client.post(
        "/lid-worden",
        data=signup_fields(
            db_session,
            emails=("iemand-anders-1883@example.com",),
            **{"h.n0.first_name": "Ander", "h.n0.last_name": "Iemand", "h.n0.mobile": "0479999999"},
        ),
    )

    assert answer.status_code == 200, answer.text[:300]
    db_session.expire_all()
    assert db_session.query(Person).count() == persons, "a second person for one human"
    person = db_session.get(Person, account.id)
    assert person.member_persons, "the account did not become the main member"
    assert (person.first_name, person.last_name) == ("Acco", "Unt")
    values = sorted(c.value for c in person.contact_details if c.deleted_at is None)
    assert values == sorted([ADDRESS, "0470001883"]), values


@pytest.mark.parametrize("household", [True, False])
def test_the_newsletter_offers_word_lid_only_to_who_has_no_household(client, db_session, household):
    if household:
        create_test_family(db_session, email="gezin-1883@example.com")
        email = "gezin-1883@example.com"
    else:
        _account(db_session)
        email = ADDRESS
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(email))
    page = client.get("/nieuwsbrief").text
    assert ("Liever lid worden?" in page) is (not household)
