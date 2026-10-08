"""Personen in the back office (CR-22 S7, #1712; R18, R25; C6 T17).

- only ADMIN and OPERATOR open the screen; FINANCE alone gets a 403, no session
  a redirect to the sign-in;
- the list opens on "Zonder gezin"; the three views cut it, the search cuts it
  by name and by e-mail address, and the counts on the views follow the search;
- deleting a person without a household: he is gone from the list, with his
  contact rows, each with a history row, and **his registration keeps the name
  and address written on it**;
- deleting a person IN a household takes him out of it by the household's own
  rule — a history row `person_removed_from_family`, by the board — and then
  deletes him; the household and its other persons stay, and **his address
  finds nobody at the sign-in** (proven on a household person: a person
  without a household signs in from S4a on);
- **the main member is refused**, on the screen, on the household record's
  route and on the JSON route (`DELETE /api/v1/persons/{id}`) — one rule,
  `mdm.delete_person`; nothing is written;
- the menu item stands in a tenant workspace's Systeem group.

Red (each restored after): the view filter taken out of `persons._viewed` →
"Zonder gezin" lists the household's persons; the detach taken out of
`delete_person` → no `person_removed_from_family` row and the main member is
deleted; the order of the links in `delete_person` reversed → a write before
the refusal for someone in two households; the soft delete of the contact rows
taken out → the deleted person's contact rows are still there. On master the JSON route deletes a main
member (204) and there is no route `/admin/personen`.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from app.domains.activities.api import Registration
from app.domains.auth.api import (
    SESSION_COOKIE,
    csrf_token_for,
    login_person_for_email,
    make_session_value,
)
from app.domains.auth.models import User, UserRole
from app.domains.mdm.api import ContactDetail, MemberPerson, Person
from app.domains.mdm.models import ContactDetailHistory, MemberPersonHistory, PersonHistory
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    create_test_family,
    create_test_person,
    seed_activity_with_product,
)

pytestmark = pytest.mark.ui_serverrendered

PAGE = "/admin/personen"
MAIN_EMAIL = "hoofdlid-1712@example.org"
LOOSE_EMAIL = "los-1712@example.org"
PARTNER_EMAIL = "partner-1712@example.org"


def _board(client, email: str = SEEDED_ADMIN_EMAIL) -> dict:
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _rows(html: str) -> list[int]:
    return [int(n) for n in re.findall(r'<tr data-row data-person="(\d+)"', html)]


def _count(html: str, view: str) -> int:
    found = re.search(rf'id="personen-filter-n-{view}"[^>]*>\((\d+)\)', html)
    assert found, f"no count on the view {view!r}"
    return int(found.group(1))


@pytest.fixture
def world(client, db_session):
    """A household of two (Peeters) and one person without a household, with an
    e-mail address, a mobile number and a registration."""
    household, main = create_test_family(db_session, email=MAIN_EMAIL)
    main.first_name, main.last_name = "Mila", "Peeters"
    partner = create_test_person(db_session, first_name="Noor", last_name="Peeters")
    db_session.add(
        MemberPerson(member_id=household.id, person_id=partner.id, relation_type="PARTNER")
    )
    db_session.add(
        ContactDetail(
            person_id=partner.id, contact_type_code="EMAIL", value=PARTNER_EMAIL, is_primary=True
        )
    )
    loose = create_test_person(db_session, first_name="Tibo", last_name="Zondergezin")
    db_session.add_all(
        [
            ContactDetail(
                person_id=loose.id,
                contact_type_code="EMAIL",
                value=LOOSE_EMAIL,
                is_primary=True,
                confirmed_at=datetime.now(timezone.utc),
            ),
            ContactDetail(
                person_id=loose.id,
                contact_type_code="MOBILE",
                value="0470 00 17 12",
                is_primary=True,
            ),
        ]
    )
    activity, component, _product = seed_activity_with_product(db_session, price="10.00")
    registration = Registration(
        activity_id=activity.id,
        component_id=component.id,
        person_id=loose.id,
        registration_type="INDIVIDUAL",
        contact_name="Tibo Zondergezin",
        contact_email=LOOSE_EMAIL,
        phone="0470 00 17 12",
    )
    db_session.add(registration)
    db_session.commit()
    return {
        "household": household.id,
        "main": main.id,
        "partner": partner.id,
        "loose": loose.id,
        "registration": registration.id,
    }


# ── who may ──────────────────────────────────────────────────────────────────


def test_only_admin_and_operator_open_the_screen(client, db_session, world):
    assert client.get(PAGE, follow_redirects=False).status_code == 303
    finance = "penningmeester-1712@example.org"
    user = User(email=finance, is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="FINANCE"))
    db_session.commit()
    headers = _board(client, finance)
    assert client.get(PAGE).status_code == 403
    assert client.get(PAGE + "/lijst").status_code == 403
    refused = client.post(f"{PAGE}/{world['loose']}/verwijderen", headers=headers)
    assert refused.status_code == 403
    assert db_session.query(Person).filter(Person.id == world["loose"]).first() is not None
    _board(client)
    page = client.get(PAGE)
    assert page.status_code == 200
    # The shell carries the session's token: without it the delete is a 403 in
    # the browser (the tests here post their own header).
    token = csrf_token_for(client.cookies.get(SESSION_COOKIE))
    assert f'"X-CSRF-Token": "{token}"' in page.text.replace("&#34;", '"')


def test_the_menu_item_stands_in_systeem(client, world):
    _board(client)
    html = client.get(PAGE).text
    assert re.search(r'<a[^>]*href="/admin/personen"[^>]*aria-current="page"', html), (
        "the menu has no marked item Personen"
    )


# ── the list ─────────────────────────────────────────────────────────────────


def test_the_list_opens_on_zonder_gezin_and_the_views_cut_it(client, world):
    _board(client)
    first = client.get(PAGE).text
    assert world["loose"] in _rows(first)
    assert world["main"] not in _rows(first) and world["partner"] not in _rows(first)
    assert re.search(r'name="zicht" value="zonder"[^>]*checked', first), "not on Zonder gezin"
    row = first[first.index(f'data-person="{world["loose"]}"') :].split("</tr>")[0]
    assert "Tibo Zondergezin" in row and LOOSE_EMAIL in row and "0470 00 17 12" in row
    # No household and a confirmed address: an account (CR-22 D1); the name is
    # plain text, a person has no page.
    assert ">Account<" in row.replace("\n", "") and "data-row-link" not in row

    within = client.get(PAGE, params={"zicht": "in"}).text
    assert {world["main"], world["partner"]} <= set(_rows(within))
    assert world["loose"] not in _rows(within)
    row = within[within.index(f'data-person="{world["partner"]}"') :].split("</tr>")[0]
    assert f"/admin/leden/gezin/{world['household']}" in row and "Peeters Mila" in row

    everyone = _rows(client.get(PAGE, params={"zicht": "alle"}).text)
    assert {world["main"], world["partner"], world["loose"]} <= set(everyone)
    # An unknown view is the default, not an error.
    assert world["loose"] in _rows(client.get(PAGE, params={"zicht": "x"}).text)


def test_the_search_cuts_by_name_and_by_address_and_the_counts_follow(client, world):
    _board(client)
    by_name = client.get(PAGE + "/lijst", params={"zicht": "alle", "q": "peeters"}).text
    assert set(_rows(by_name)) == {world["main"], world["partner"]}
    assert _count(by_name, "alle") == 2 and _count(by_name, "in") == 2
    assert _count(by_name, "zonder") == 0
    by_address = client.get(PAGE + "/lijst", params={"zicht": "alle", "q": "LOS-1712@"}).text
    assert _rows(by_address) == [world["loose"]]
    nothing = client.get(PAGE + "/lijst", params={"zicht": "alle", "q": "niemand-zo"}).text
    assert _rows(nothing) == [] and "Geen personen gevonden" in nothing
    # A wildcard is a character, not a pattern.
    assert _rows(client.get(PAGE + "/lijst", params={"zicht": "alle", "q": "%"}).text) == []


# ── deleting ─────────────────────────────────────────────────────────────────


def test_the_confirmation_names_the_household_when_there_is_one(client, world):
    _board(client)
    everyone = client.get(PAGE, params={"zicht": "alle"}).text
    loose = everyone[everyone.index(f'data-person="{world["loose"]}"') :].split("</tr>")[0]
    assert 'data-confirm="Tibo Zondergezin verwijderen?"' in loose
    partner = everyone[everyone.index(f'data-person="{world["partner"]}"') :].split("</tr>")[0]
    assert (
        "Noor Peeters verwijderen? Deze persoon wordt ook uit het gezin Peeters Mila gehaald."
        in partner
    )


def test_deleting_a_person_without_a_household(client, db_session, world):
    headers = _board(client)
    answer = client.post(f"{PAGE}/{world['loose']}/verwijderen", headers=headers)
    assert answer.status_code == 200 and world["loose"] not in _rows(answer.text)
    db_session.expire_all()
    assert db_session.query(Person).filter(Person.id == world["loose"]).first() is None
    assert (
        db_session.query(ContactDetail).filter(ContactDetail.person_id == world["loose"]).count()
        == 0
    )
    person_rows = (
        db_session.query(PersonHistory).filter(PersonHistory.person_id == world["loose"]).all()
    )
    assert [(h.operation, h.action, h.source, h.actor) for h in person_rows][-1] == (
        "delete",
        "person_deleted",
        "admin_manual",
        SEEDED_ADMIN_EMAIL,
    )
    contact_rows = (
        db_session.query(ContactDetailHistory)
        .filter(ContactDetailHistory.person_id == world["loose"])
        .filter(ContactDetailHistory.action == "person_deleted")
        .count()
    )
    assert contact_rows == 2
    registration = (
        db_session.query(Registration).filter(Registration.id == world["registration"]).one()
    )
    assert (registration.contact_name, registration.contact_email, registration.phone) == (
        "Tibo Zondergezin",
        LOOSE_EMAIL,
        "0470 00 17 12",
    )


def test_deleting_a_household_person_takes_him_out_by_the_household_rule(client, db_session, world):
    headers = _board(client)
    assert login_person_for_email(db_session, PARTNER_EMAIL) is not None
    answer = client.post(
        f"{PAGE}/{world['partner']}/verwijderen",
        headers={**headers, "HX-Current-URL": "http://testserver/admin/personen?zicht=in"},
    )
    assert answer.status_code == 200
    assert _rows(answer.text) == [world["main"]], "the list did not keep its view"
    db_session.expire_all()
    assert db_session.query(Person).filter(Person.id == world["partner"]).first() is None
    links = (
        db_session.query(MemberPersonHistory)
        .filter(MemberPersonHistory.person_id == world["partner"])
        .all()
    )
    assert [(h.operation, h.action, h.source, h.actor) for h in links] == [
        ("delete", "person_removed_from_family", "admin_manual", SEEDED_ADMIN_EMAIL)
    ]
    # The household and its main member stay.
    assert (
        db_session.query(MemberPerson)
        .filter(MemberPerson.member_id == world["household"])
        .filter(MemberPerson.person_id == world["main"])
        .count()
        == 1
    )
    assert login_person_for_email(db_session, MAIN_EMAIL) is not None
    assert login_person_for_email(db_session, PARTNER_EMAIL) is None, (
        "the deleted person's address still signs in"
    )


def _main_member_stays(db_session, world) -> None:
    db_session.expire_all()
    assert db_session.query(Person).filter(Person.id == world["main"]).first() is not None
    assert (
        db_session.query(MemberPerson).filter(MemberPerson.person_id == world["main"]).count() == 1
    )
    assert db_session.query(ContactDetail).filter(ContactDetail.person_id == world["main"]).count()
    for model in (PersonHistory, MemberPersonHistory, ContactDetailHistory):
        assert db_session.query(model).filter(model.person_id == world["main"]).count() == 0, (
            f"a refused delete wrote a {model.__name__} row"
        )


def test_the_main_member_is_refused_on_the_screen(client, db_session, world):
    headers = _board(client)
    answer = client.post(
        f"{PAGE}/{world['main']}/verwijderen",
        headers={**headers, "HX-Current-URL": "http://testserver/admin/personen?zicht=in"},
    )
    assert answer.status_code == 200
    assert "Mila Peeters is niet verwijderd. Een gezin heeft een hoofdlid nodig." in answer.text
    assert world["main"] in _rows(answer.text)
    _main_member_stays(db_session, world)


def test_the_main_member_is_refused_on_the_household_record_route(client, db_session, world):
    headers = _board(client)
    answer = client.post(
        f"/admin/leden/gezin/{world['household']}/persoon/{world['main']}/verwijderen",
        headers=headers,
    )
    assert answer.status_code == 400 and "Een gezin heeft een hoofdlid nodig." in answer.text
    _main_member_stays(db_session, world)


def test_the_main_member_is_refused_on_the_json_route(client, db_session, world, admin_headers):
    answer = client.delete(f"/api/v1/persons/{world['main']}", headers=admin_headers)
    assert answer.status_code == 400, answer.text
    assert answer.json()["detail"] == "Een gezin heeft een hoofdlid nodig."
    _main_member_stays(db_session, world)
    # The same route still deletes a partner, through the same rule.
    assert (
        client.delete(f"/api/v1/persons/{world['partner']}", headers=admin_headers).status_code
        == 204
    )
    db_session.expire_all()
    assert db_session.query(Person).filter(Person.id == world["partner"]).first() is None
    assert (
        db_session.query(MemberPersonHistory)
        .filter(MemberPersonHistory.person_id == world["partner"])
        .one()
        .action
        == "person_removed_from_family"
    )


def test_a_refusal_writes_nothing_for_someone_in_two_households(client, db_session, world):
    """The partner of one household is the main member of another: the refusal
    comes before his link to the first is touched.

    Red: the sort taken out of `delete_person` → the first household's link is
    detached (a `MemberPersonHistory` row) before the second one refuses."""
    from tests.conftest import create_test_member

    second = create_test_member(db_session)
    db_session.add(
        MemberPerson(member_id=second.id, person_id=world["partner"], relation_type="HOOFDLID")
    )
    db_session.commit()
    headers = _board(client)
    answer = client.post(
        f"{PAGE}/{world['partner']}/verwijderen",
        headers={**headers, "HX-Current-URL": "http://testserver/admin/personen?zicht=in"},
    )
    assert "Noor Peeters is niet verwijderd. Een gezin heeft een hoofdlid nodig." in answer.text
    assert (
        db_session.query(MemberPersonHistory)
        .filter(MemberPersonHistory.person_id == world["partner"])
        .count()
        == 0
    ), "the refusal came after a write"
    db_session.expire_all()
    assert (
        db_session.query(MemberPerson).filter(MemberPerson.person_id == world["partner"]).count()
        == 2
    )


def test_a_person_who_is_gone_is_said_so(client, world):
    headers = _board(client)
    answer = client.post(f"{PAGE}/99999999/verwijderen", headers=headers)
    assert answer.status_code == 200 and "Deze persoon bestaat niet (meer)." in answer.text
