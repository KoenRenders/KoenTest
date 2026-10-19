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
from tests._sites import at_tenant, party_of
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    create_test_family,
    create_test_person,
    record_fields,
    save_record,
)

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
    """The e-mail rows of the record in edit mode (#1899: rows of the kit's list),
    by the address in their field. Personen keeps its own row mark."""
    found = {}
    for part in re.split(r'<div data-group-row data-row-key="', html)[1:]:
        value = re.search(r'<input[^>]*type="email"[^>]*value="([^"]*)"', part)
        # A person's card holds its e-mail rows: only a part that STARTS as an
        # e-mail row is one.
        if value and 'name="e_order.' in part[:400]:
            found[value.group(1)] = part
    return found


@pytest.fixture
def world(client, db_session):
    household, person = create_test_family(db_session, email=MAIN)
    at_tenant(db_session, household)  # CR-26 F9
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


def _primary(client, world, row_id: int):
    """The record's one save (#1899) with this row marked as the main address."""
    fields = record_fields(client, world["household"])
    fields[f"e_primary.{world['person']}"] = str(row_id)
    return save_record(client, world["household"], fields)


def test_the_household_record_marks_a_waiting_address_and_offers_no_main_address(client, world):
    _board(client)
    page = client.get(f"/admin/leden/gezin/{world['household']}?bewerken=1")
    assert page.status_code == 200
    rows = _rows(page.text)
    assert set(rows) == {MAIN, SECOND, WAITING}, set(rows)
    make, remove = 'data-row-action="choose"', 'data-row-action="remove"'

    waiting = rows[WAITING]
    assert "data-row-tag" in waiting and BADGE in waiting
    assert make not in waiting and "Maak hoofdadres" not in waiting
    assert remove in waiting, "a waiting address cannot be deleted"

    second = rows[SECOND]
    assert BADGE not in second and "data-row-tag" not in second
    assert make in second and "Maak hoofdadres" in second

    main = rows[MAIN]
    assert re.search(r"<span data-row-one-tag class=\"shrink-0\">", main), "the main tag is hidden"
    assert BADGE not in main
    form = page.text[page.text.index('<form id="gezin-form"') :]
    form = form[: form.index("<template data-group-template>")]
    assert form.count(BADGE) == 1, "the mark stands on more than the waiting row"


def test_a_waiting_address_is_never_made_the_main_one(client, db_session, world):
    """The page offers no "Maak hoofdadres" on a waiting row; a form that marks
    it anyway changes nothing — the save does not promote what is not proven
    (#1711) — and a confirmed one is made the main address by the same save."""
    _board(client)
    ignored = _primary(client, world, world["waiting"])
    assert ignored.status_code == 200, ignored.text[:200]
    db_session.expire_all()
    rows = {
        c.value: (bool(c.is_primary), c.confirmed_at is not None)
        for c in db_session.query(ContactDetail).filter(
            ContactDetail.party_id == party_of(db_session, world["person"])
        )
    }
    assert rows == {MAIN: (True, True), SECOND: (False, True), WAITING: (False, False)}

    done = _primary(client, world, world["second"])
    assert done.status_code == 200
    db_session.expire_all()
    primary = [
        c.value
        for c in db_session.query(ContactDetail).filter(
            ContactDetail.party_id == party_of(db_session, world["person"])
        )
        if c.is_primary
    ]
    assert primary == [SECOND]


def test_a_waiting_address_can_still_be_deleted(client, db_session, world):
    _board(client)
    fields = record_fields(client, world["household"])
    key = f"e_order.{world['person']}"
    fields[key] = [row for row in fields[key] if row != str(world["waiting"])]
    answer = save_record(client, world["household"], fields)
    assert answer.status_code == 200
    assert WAITING not in answer.text and BADGE not in answer.text
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


def test_the_read_card_marks_an_address_that_waits(client, db_session, world):
    """#1899: the read card shows every address of a person on a line of its own
    — the main one tagged, a waiting one with the mark, never as if it counted.
    A partner whose only address waits shows it with the mark.

    Red: the `pending` branch taken out of the kit's `person_card` → the waiting
    addresses stand on their line like any other."""
    from app.domains.mdm.api import MemberPerson

    partner = create_test_person(db_session, first_name="Pia", last_name="Wachter")
    db_session.add(
        MemberPerson(member_id=world["household"], person_id=partner.id, relation_type="PARTNER")
    )
    _address(db_session, partner, "pia-wacht-1733@example.org", confirmed=False)
    db_session.commit()
    _board(client)
    html = client.get(f"/admin/leden/gezin/{world['household']}").text

    def lines(person_id: int) -> dict[str, str]:
        card = html[html.index(f'data-person="{person_id}"') :]
        card = card[: card.index("</section>")]
        found = {}
        for line in re.findall(r"<p data-person-email.*?</p>", card, re.S):
            address = re.search(r'href="mailto:([^"]*)"', line)
            found[address.group(1) if address else "—"] = line
        return found

    main = lines(world["person"])
    assert set(main) == {MAIN, SECOND, WAITING}
    assert "hoofdadres" in main[MAIN] and BADGE not in main[MAIN]
    assert BADGE in main[WAITING] and BADGE not in main[SECOND]
    waiting = lines(partner.id)
    assert BADGE in waiting["pia-wacht-1733@example.org"]
    # The board is no person of the household: it is offered no code.
    assert "data-enter-code" not in html and "data-send-code" not in html
