"""The back office shows a waiting e-mail address as "wacht op bevestiging"
(#1733; CR-22 R15; Koen, 8 October 2026).

Since #1711 an address a person types himself waits for its code: it does not
sign in and is never the main address. The member's own pages say so; the
back office showed the row like any other and offered "Maak hoofdadres" on it,
which could only answer 409.

- on the household record a waiting row carries the badge "wacht op
  bevestiging" and **no "Maak hoofdadres"**; a confirmed second address carries
  the button and no badge; the main address its own badge;
- **the route still refuses** when called directly (409), and nothing changes;
- deleting a waiting address stays possible;
- Personen shows an address that counts where the person has one; someone whose
  only address waits shows it with the same badge, and is no account.

Red (each restored after): the `confirmed=` taken off the row the board's
screen builds → the waiting row has no badge and offers the button; the waiting
branch taken out of `_email_rij.html` → the same; `email_waiting` always False
in `mdm.persons` → Personen shows the waiting address without a mark.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import ContactDetail, new_contact_detail
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family, create_test_person

pytestmark = pytest.mark.ui_serverrendered

MAIN = "hoofd-1733@example.org"
SECOND = "tweede-1733@example.org"
WAITING = "wacht-1733@example.org"
BADGE = "wacht op bevestiging"


def _board(client) -> dict:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _address(db, person, value: str, *, confirmed: bool) -> ContactDetail:
    row = new_contact_detail(db, person, "EMAIL", value, is_primary=False, confirmed=confirmed)
    db.add(row)
    db.flush()
    return row


def _rows(html: str) -> dict[str, str]:
    """The e-mail rows of a screen, by the address in their field."""
    found = {}
    for part in html.split("data-email-rij")[1:]:
        value = re.search(r'<input[^>]*type="email"[^>]*value="([^"]*)"', part)
        if value:
            found[value.group(1)] = (
                part.split("</div>\n</div>")[0] if "</div>\n</div>" in part else part
            )
    return found


@pytest.fixture
def world(client, db_session):
    household, person = create_test_family(db_session, email=MAIN)
    person.first_name, person.last_name = "Wies", "Wachter"
    second = _address(db_session, person, SECOND, confirmed=True)
    waiting = _address(db_session, person, WAITING, confirmed=False)
    db_session.commit()
    return {
        "household": household.id,
        "person": person.id,
        "second": second.id,
        "waiting": waiting.id,
    }


def _base(world) -> str:
    return f"/admin/leden/gezin/{world['household']}/persoon/{world['person']}/email"


def test_the_household_record_marks_a_waiting_address_and_offers_no_main_address(client, world):
    _board(client)
    page = client.get(f"/admin/leden/gezin/{world['household']}")
    assert page.status_code == 200
    rows = _rows(page.text)
    assert set(rows) == {MAIN, SECOND, WAITING}, set(rows)

    waiting = rows[WAITING]
    assert "data-email-waiting" in waiting and BADGE in waiting
    assert "Maak hoofdadres" not in waiting and f"/{world['waiting']}/hoofd" not in waiting
    assert f"/{world['waiting']}/verwijderen" in waiting, "a waiting address cannot be deleted"

    second = rows[SECOND]
    assert BADGE not in second and "data-email-waiting" not in second
    assert "Maak hoofdadres" in second and f"/{world['second']}/hoofd" in second

    main = rows[MAIN]
    assert "hoofdadres" in main and BADGE not in main and "Maak hoofdadres" not in main
    assert page.text.count(BADGE) == 1, "the mark stands on more than the waiting row"


def test_the_route_still_refuses_a_waiting_address_as_the_main_one(client, db_session, world):
    headers = _board(client)
    refused = client.post(f"{_base(world)}/{world['waiting']}/hoofd", headers=headers)
    assert refused.status_code == 409, refused.text[:200]
    db_session.expire_all()
    rows = {
        c.value: (bool(c.is_primary), c.confirmed_at is not None)
        for c in db_session.query(ContactDetail).filter(ContactDetail.person_id == world["person"])
    }
    assert rows == {MAIN: (True, True), SECOND: (False, True), WAITING: (False, False)}
    # … and a confirmed one is still made the main address by the same route.
    done = client.post(f"{_base(world)}/{world['second']}/hoofd", headers=headers)
    assert done.status_code == 200
    assert "hoofdadres" in _rows(done.text)[SECOND]


def test_a_waiting_address_can_still_be_deleted(client, db_session, world):
    headers = _board(client)
    answer = client.post(f"{_base(world)}/{world['waiting']}/verwijderen", headers=headers)
    assert answer.status_code == 200
    assert WAITING not in _rows(answer.text) and BADGE not in answer.text
    db_session.expire_all()
    assert (
        db_session.query(ContactDetail).filter(ContactDetail.id == world["waiting"]).first() is None
    )


def test_personen_shows_an_address_that_counts_and_marks_one_that_only_waits(client, db_session):
    both = create_test_person(db_session, first_name="Bea", last_name="Beide-1733")
    _address(db_session, both, "bea-wacht-1733@example.org", confirmed=False)
    _address(db_session, both, "bea-telt-1733@example.org", confirmed=True)
    only = create_test_person(db_session, first_name="Odo", last_name="Wachtend-1733")
    _address(db_session, only, "odo-wacht-1733@example.org", confirmed=False)
    db_session.commit()
    _board(client)
    html = client.get("/admin/personen", params={"zicht": "zonder", "q": "-1733"}).text

    def row(person) -> str:
        return html[html.index(f'data-person="{person.id}"') :].split("</tr>")[0]

    counted = row(both)
    assert "bea-telt-1733@example.org" in counted and "bea-wacht-1733@example.org" not in counted
    assert BADGE not in counted and ">Account<" in counted.replace("\n", "")

    waiting = row(only)
    assert "odo-wacht-1733@example.org" in waiting
    assert "data-email-waiting" in waiting and BADGE in waiting
    assert ">Account<" not in waiting.replace("\n", ""), "a waiting address makes no account"


def test_the_read_line_of_a_person_card_shows_an_address_that_counts(client, db_session, world):
    """The card's read line names "the" e-mail address: the main one — never a
    waiting one while another counts. A partner whose only address waits shows
    it with the mark.

    Red: `email_waiting` taken off the schema's call → the partner's waiting
    address stands on the read line like any other."""
    from app.domains.mdm.api import MemberPerson

    partner = create_test_person(db_session, first_name="Pia", last_name="Wachter")
    db_session.add(
        MemberPerson(member_id=world["household"], person_id=partner.id, relation_type="PARTNER")
    )
    _address(db_session, partner, "pia-wacht-1733@example.org", confirmed=False)
    db_session.commit()
    _board(client)
    html = client.get(f"/admin/leden/gezin/{world['household']}").text

    def read_line(person_id: int) -> str:
        card = html[html.index(f'id="persoon-{person_id}"') :]
        return card[: card.index("<form")]

    main = read_line(world["person"])
    assert MAIN in main and WAITING not in main and BADGE not in main
    waiting = read_line(partner.id)
    assert "pia-wacht-1733@example.org" in waiting
    assert "data-email-waiting" in waiting and BADGE in waiting
