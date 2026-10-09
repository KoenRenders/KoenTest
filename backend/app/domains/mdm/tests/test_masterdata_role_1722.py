"""CR-24 (#1722) T4, AC5: a user with only MASTERDATA manages persons, households
and memberships, and is refused activities, payments and settings.

Slice 4, group (a): the gates of the member screens ask `party.view` and
`party.masterdata`, which the bundle of MASTERDATA holds beside ADMIN's and the
operator's. Everything is asked on requests, with a session and the CSRF token
of that session, as the browser sends them.

A screen is more than its gate, so the last test walks what the member screens
point at **inside the page** (links, htmx addresses, form targets within
`<main>`): each must answer the MASTERDATA user, or be named in `REFUSED_ON_PAGE`
with the reason. The menu around the page is not walked here: it shows every
item to every role until it asks rights (slice 5).

Proven red (9 October 2026), one edit each, put back:
- `party.masterdata` taken out of MASTERDATA's bundle in the migration → the
  changes are refused (403);
- the household page's gate asked `activity.view` → the page and the walk red;
- the list of activities asked `party.view` → "is refused the rest" red.
"""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

import pytest

from app.domains.auth.api import (
    SESSION_COOKIE,
    User,
    UserRole,
    csrf_token_for,
    make_session_value,
)
from app.domains.mdm.api import ExternalNumber, MemberPerson, Person
from app.domains.mdm.import_service import upsert_families
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from tests.conftest import seed_postal_code

pytestmark = pytest.mark.ui_serverrendered

#: Addresses inside a member screen that refuse a MASTERDATA-only user, each
#: with the reason. Empty is the aim; an entry is a decision.
REFUSED_ON_PAGE: dict[str, str] = {}

ADDRESS = re.compile(r'(?:href|hx-get|action|hx-post|src)="(/admin/[^"#]*)"')
GETS = re.compile(r'(?:href|hx-get|src)="(/admin/[^"#]*)"')


def _row(number: str, first_name: str, relation: str, born: str) -> dict:
    return {
        "lidnr": number,
        "voornaam": first_name,
        "naam": "Voorbeeld",
        "straat": "milostraat",
        "huisnummer": "40",
        "busnummer": "",
        "postcode": "2400",
        "gemeente": "Mol",
        "email": None,
        "telefoon": None,
        "gsm": None,
        "geboortedatum": born,
        "geslacht": None,
        "bestuurslid": None,
        "_relatie": relation,
    }


@pytest.fixture
def world(db_session):
    seed_postal_code(db_session)
    rows = [
        _row("172201", "An", "HOOFDLID", "1980-01-01"),
        _row("172202", "Bert", "PARTNER", "1981-02-02"),
    ]
    upsert_families(db_session, [rows], {}, [], apply=True)
    db_session.flush()
    numbers = {n.external_id: n.person_id for n in db_session.query(ExternalNumber).all()}
    partner = numbers["172202"]
    member = db_session.query(MemberPerson).filter_by(person_id=partner).one().member_id
    users = {}
    for role in ("MASTERDATA", "SALES"):
        user = User(email=f"{role.lower()}-t4@example.com", is_active=True)
        db_session.add(user)
        db_session.flush()
        db_session.add(UserRole(user_id=user.id, role_code=role, tenant_id=TENANT_MILLEGEM_ID))
        users[role] = user.email
    db_session.commit()
    return SimpleNamespace(member=member, head=numbers["172201"], partner=partner, users=users)


def _as(client, email: str) -> dict:
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _screens(world) -> list[str]:
    household = f"/admin/leden/gezin/{world.member}"
    return [
        "/admin/leden",
        "/admin/leden/lijst",
        "/admin/leden/nieuw",
        household,
        f"{household}/inschrijvingen",
        "/admin/personen",
        "/admin/leden-import",
    ]


def test_masterdata_alone_opens_the_member_screens(client, world):
    _as(client, world.users["MASTERDATA"])
    answers = {path: client.get(path).status_code for path in _screens(world)}
    assert answers == dict.fromkeys(_screens(world), 200)


def test_masterdata_alone_changes_a_household_and_its_memberships(client, db_session, world):
    headers = _as(client, world.users["MASTERDATA"])
    household = f"/admin/leden/gezin/{world.member}"

    removed = client.post(f"{household}/persoon/{world.partner}/verwijderen", headers=headers)
    assert removed.status_code == 200, removed.text[:200]
    db_session.expire_all()
    assert db_session.get(Person, world.partner) is None, "the partner is still there"

    year = date.today().year
    membership = client.post(
        f"{household}/lidmaatschappen",
        headers=headers,
        data={"year": str(year), "valid_from": f"{year}-01-01", "valid_to": f"{year}-12-31"},
    )
    assert membership.status_code not in (401, 403), membership.text[:200]

    person = client.post(f"/admin/personen/{world.head}/verwijderen", headers=headers)
    assert person.status_code not in (401, 403), person.text[:200]


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/admin/activiteiten"),
        ("POST", "/admin/activiteiten/nieuw"),
        ("GET", "/admin/betalingen"),
        ("POST", "/admin/betalingen/1/bevestigen"),
        ("GET", "/admin/instellingen"),
        ("GET", "/admin/gebruikers"),
    ],
)
def test_masterdata_alone_is_refused_the_rest(client, world, method, path):
    headers = _as(client, world.users["MASTERDATA"])
    assert client.request(method, path, headers=headers).status_code == 403


def test_a_shop_role_opens_no_member_screen(client, world):
    """AC6: the bundle of Verkoop holds nothing of master data."""
    headers = _as(client, world.users["SALES"])
    answers = {path: client.get(path).status_code for path in _screens(world)}
    assert answers == dict.fromkeys(_screens(world), 403)
    household = f"/admin/leden/gezin/{world.member}"
    assert client.post(f"{household}/verwijderen", headers=headers).status_code == 403


def test_what_a_member_screen_points_at_answers_masterdata_too(client, world):
    _as(client, world.users["MASTERDATA"])
    pointed, changing = set(), set()
    for path in _screens(world):
        html = client.get(path).text
        assert "<main" in html or path.endswith(("/lijst", "/inschrijvingen")), path
        page = html.split("<main", 1)[-1].split("</main>", 1)[0]
        pointed |= {a.replace("&amp;", "&") for a in GETS.findall(page)}
        changing |= set(ADDRESS.findall(page)) - set(GETS.findall(page))
    assert len(pointed) >= 10, f"the walk found only {sorted(pointed)}"

    refused = {a for a in sorted(pointed) if client.get(a).status_code == 403}
    print("WALK pointed", len(pointed), "changing", len(changing), "refused", sorted(refused))
    outside = {
        a for a in pointed | changing if not a.startswith(("/admin/leden", "/admin/personen"))
    }
    print("WALK outside the member screens", sorted(outside))
    assert refused == set(REFUSED_ON_PAGE), (
        f"refused and not named: {sorted(refused - set(REFUSED_ON_PAGE))}; "
        f"named and not refused: {sorted(set(REFUSED_ON_PAGE) - refused)}"
    )
