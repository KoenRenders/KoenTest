"""One person and one household per account, the facts per department (CR-26 phase 1, #2020).

Tests T4, T5 and T10 of the change request, and the import's recognition of a
known person (C2 mdm), on made-up data. The two seeded departments, Millegem
and the Voorbeeldafdeling, share one account; a tenant made here with
`a_tenant_with_id` is an account of its own.

Proven red, additively (put back each time):
- the old index `uq_memberships_member_year (member_id, year)` created again at
  the end of migration 314 → `test_a_household_is_a_member_of_two_departments_in_one_year`;
- `return True` added at the top of `household_at_tenant` → the 404 test gets
  200;
- `known = None` added after the e-mail lookup in `_sync_family` → the import
  test finds a second person;
- `return True` added at the top of `household_at_tenant` → all seven
  household routes answer (200, 422, 204: the delete went through);
- `return query` added at the top of `persons_seen_here` → the picker finds
  the other department's member.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.mdm.api import (
    ContactDetail,
    Member,
    MemberPerson,
    Person,
    person_at_tenant,
)
from app.kernel.tenancy import TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID, current_tenant_id
from tests._sites import a_tenant_with_id, at_tenant
from tests.conftest import board_session, create_test_family, create_test_person

pytestmark = pytest.mark.ui_agnostisch


class _At:
    """The current tenant for a block, as a request would set it."""

    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id

    def __enter__(self):
        self.token = current_tenant_id.set(self.tenant_id)

    def __exit__(self, *_exc):
        current_tenant_id.reset(self.token)


# ── T4: one household per person, memberships per department ────────────────


def test_a_second_living_household_for_one_person_is_refused(db_session):
    """F5: `uq_member_persons_one_household`. No door puts an existing person
    in a second household; the index is the net under every writer."""
    household, person = create_test_family(db_session, email="een-gezin@example.org")
    second = Member()
    db_session.add(second)
    db_session.flush()
    db_session.add(MemberPerson(member_id=second.id, person_id=person.id, relation_type="PARTNER"))
    with pytest.raises(IntegrityError, match="uq_member_persons_one_household"):
        db_session.flush()


def test_a_household_is_a_member_of_two_departments_in_one_year(db_session):
    """F5, AC2: one household, one membership at Millegem and one at the
    Voorbeeldafdeling, the same year. Red on the index before CR-26."""
    household, _person = create_test_family(db_session, email="twee-afdelingen@example.org")
    at_tenant(db_session, household, TENANT_MILLEGEM_ID, year=2026)
    at_tenant(db_session, household, TENANT_VOORBEELD_ID, year=2026)
    db_session.commit()
    from app.domains.membership.api import Membership

    rows = (
        db_session.query(Membership)
        .execution_options(include_all_tenants=True)
        .filter(Membership.member_id == household.id, Membership.year == 2026)
        .all()
    )
    assert sorted(r.tenant_id for r in rows) == [TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID]


# ── T10: a tenant sees by fact ──────────────────────────────────────────────


def test_a_household_without_a_fact_here_answers_404(client, db_session):
    """F9: a household of the account that is a member of the Voorbeeldafdeling
    only is not Millegem's: its record answers as an id that is not yours."""
    elsewhere, _person = create_test_family(db_session, email="elders-lid@example.org")
    at_tenant(db_session, elsewhere, TENANT_VOORBEELD_ID)
    here, _other = create_test_family(db_session, email="hier-lid@example.org")
    at_tenant(db_session, here, TENANT_MILLEGEM_ID)
    db_session.commit()
    board_session(client)

    assert client.get(f"/admin/leden/gezin/{here.id}").status_code == 200
    assert client.get(f"/admin/leden/gezin/{elsewhere.id}").status_code == 404


#: The routes of a household's record (`test_who_gets_in_unchanged_1722`): the
#: method, the path after the id, and what a POST sends.
HOUSEHOLD_ROUTES = [
    ("GET", "", None),
    ("GET", "/vernieuwen", None),
    ("GET", "/inschrijvingen", None),
    ("GET", "/betalingen", None),
    ("POST", "", {}),
    ("POST", "/vernieuwen", {"payment_method": "transfer"}),
    ("POST", "/verwijderen", {}),
]


@pytest.mark.parametrize(("method", "tail", "data"), HOUSEHOLD_ROUTES)
def test_every_household_route_refuses_a_household_of_another_department(
    client, db_session, method, tail, data
):
    """dev2's read of #2158: the guard on every door, not on one GET. A
    household of the account that is a member of the Voorbeeldafdeling only,
    asked of Millegem: 404, and nothing written."""
    from app.domains.membership.api import Membership

    elsewhere, _person = create_test_family(db_session, email=f"deur{len(tail)}@example.org")
    at_tenant(db_session, elsewhere, TENANT_VOORBEELD_ID)
    db_session.commit()
    headers = board_session(client)
    path = f"/admin/leden/gezin/{elsewhere.id}{tail}"
    answer = client.get(path) if method == "GET" else client.post(path, data=data, headers=headers)
    assert answer.status_code == 404, (method, path, answer.status_code)
    db_session.expire_all()
    assert db_session.get(Member, elsewhere.id).deleted_at is None
    rows = (
        db_session.query(Membership)
        .execution_options(include_all_tenants=True)
        .filter(Membership.member_id == elsewhere.id)
        .count()
    )
    assert rows == 1, "no membership was written"


def test_the_person_pickers_find_only_who_the_tenant_sees(db_session):
    """dev2's read of #2158: the circle, the organiser and the order contact
    search, and 'bestaand lid toevoegen', narrow like Personen — a member of the
    other department is not found, a person with a fact nowhere is."""
    from app.domains.mdm.service import list_persons, search_persons

    household, elsewhere = create_test_family(db_session, email="zoek-elders@example.org")
    elsewhere.first_name, elsewhere.last_name = "Zoek", "Elders"
    at_tenant(db_session, household, TENANT_VOORBEELD_ID)
    create_test_person(db_session, first_name="Zoek", last_name="Nergens")
    db_session.commit()
    with _At(TENANT_MILLEGEM_ID):
        db_session.expire_all()
        found = {f"{m.first_name} {m.last_name}" for m in search_persons(db_session, "zoek")}
        listed = {f"{p.first_name} {p.last_name}" for p in list_persons(db_session)}
    assert found == {"Zoek Nergens"}
    assert "Zoek Elders" not in listed and "Zoek Nergens" in listed


def test_the_member_list_holds_only_the_tenants_households(client, db_session):
    elsewhere, person = create_test_family(db_session, email="lijst-elders@example.org")
    person.last_name = "Elderslid"
    at_tenant(db_session, elsewhere, TENANT_VOORBEELD_ID)
    here, mine = create_test_family(db_session, email="lijst-hier@example.org")
    mine.last_name = "Hierlid"
    at_tenant(db_session, here, TENANT_MILLEGEM_ID)
    db_session.commit()
    board_session(client)

    # Neither paid: both stand under Opgezegd.
    html = client.get("/admin/leden/lijst?status=opgezegd").text
    assert "Hierlid" in html
    assert "Elderslid" not in html


def test_a_registration_puts_a_person_at_the_tenant(db_session):
    """F9: a person in no household is at a tenant through a registration
    there, and only there."""
    from app.domains.activities.api import Registration
    from tests.conftest import seed_activity_with_product

    person = create_test_person(db_session, first_name="Ingeschreven", last_name="Gast")
    with _At(TENANT_MILLEGEM_ID):
        activity, component, _product = seed_activity_with_product(db_session, price="5.00")
        db_session.add(
            Registration(
                activity_id=activity.id,
                component_id=component.id,
                person_id=person.id,
                registration_type="INDIVIDUAL",
                contact_name="Ingeschreven Gast",
                contact_email="ingeschreven@example.org",
            )
        )
        db_session.flush()
        assert person_at_tenant(db_session, person.id)
    with _At(TENANT_VOORBEELD_ID):
        assert not person_at_tenant(db_session, person.id)


def test_a_person_with_no_fact_anywhere_is_seen_by_every_department(db_session):
    """Koen, 19 October 2026: "1 voor allen zichtbaar" — an account without a
    household and without a fact is the account's, and every department sees it
    in Personen until it gets a fact somewhere; then only that department."""
    from app.domains.mdm.persons import EVERYONE, persons_page

    loose = create_test_person(db_session, first_name="Los", last_name="Account")
    household, mine = create_test_family(db_session, email="feit-hier@example.org")
    mine.first_name, mine.last_name = "Gebonden", "Lid"
    at_tenant(db_session, household, TENANT_MILLEGEM_ID)
    db_session.commit()

    def names(tenant: int) -> set[str]:
        with _At(tenant):
            db_session.expire_all()
            return {row.name for row in persons_page(db_session, view=EVERYONE).rows}

    assert {"Los Account", "Gebonden Lid"} <= names(TENANT_MILLEGEM_ID)
    voorbeeld = names(TENANT_VOORBEELD_ID)
    assert "Los Account" in voorbeeld and "Gebonden Lid" not in voorbeeld
    with _At(TENANT_VOORBEELD_ID):
        assert person_at_tenant(db_session, loose.id)
        assert not person_at_tenant(db_session, mine.id)


# ── T5: the sign-in finds the account's person ──────────────────────────────


def _confirmed_email(db, person, address: str) -> None:
    from datetime import datetime, timezone

    db.add(
        ContactDetail(
            person_id=person.id,
            contact_type_code="EMAIL",
            value=address,
            is_primary=True,
            confirmed_at=datetime.now(timezone.utc),
        )
    )
    db.flush()


def test_a_member_of_one_department_signs_in_at_the_other_as_himself(db_session):
    """R3, AC1: one person for the account. At the department where his
    household has no membership he has no *Mijn gezin* there — he sees *Word
    lid* (A3)."""
    from app.domains.auth.api import (
        has_household,
        in_household_elsewhere,
        login_person_for_email,
    )

    with _At(TENANT_MILLEGEM_ID):
        household, person = create_test_family(db_session, email="tweeplekken@example.org")
        at_tenant(db_session, household, TENANT_MILLEGEM_ID)
        db_session.query(ContactDetail).filter_by(person_id=person.id).update(
            {"confirmed_at": db_session.query(Person.created_at).filter_by(id=person.id).scalar()}
        )
        db_session.commit()
        here = login_person_for_email(db_session, "tweeplekken@example.org")
        assert here is not None and here.id == person.id
        assert has_household(here)
    with _At(TENANT_VOORBEELD_ID):
        db_session.expire_all()
        there = login_person_for_email(db_session, "tweeplekken@example.org")
        assert there is not None and there.id == person.id, "the same person, not a second"
        assert not has_household(there) and in_household_elsewhere(there)


def test_another_account_does_not_find_the_person(db_session):
    from app.domains.auth.api import login_person_for_email

    with _At(TENANT_MILLEGEM_ID):
        person = create_test_person(db_session, first_name="Een", last_name="Account")
        _confirmed_email(db_session, person, "een-account@example.org")
    other = a_tenant_with_id(db_session, 9_826)
    db_session.commit()
    with _At(other.id):
        db_session.expire_all()
        assert login_person_for_email(db_session, "een-account@example.org") is None


def test_a_duplicate_pair_of_the_account_signs_in_nowhere(db_session):
    """Q19 ("c"): one address on two persons in two households of one account —
    as today's data holds — answers MULTIPLE at every department."""
    from app.domains.auth.member_identity import MULTIPLE, sign_in_identity

    with _At(TENANT_MILLEGEM_ID):
        for name, tenant in (("Eerste", TENANT_MILLEGEM_ID), ("Tweede", TENANT_VOORBEELD_ID)):
            household = Member()
            db_session.add(household)
            db_session.flush()
            at_tenant(db_session, household, tenant)
            person = create_test_person(db_session, first_name=name, last_name="Dubbel")
            db_session.add(
                MemberPerson(member_id=household.id, person_id=person.id, relation_type="HOOFDLID")
            )
            # Written past the refusal, as the data from before CR-26 stands.
            db_session.flush()
            db_session.execute(
                ContactDetail.__table__.insert().values(
                    person_id=person.id,
                    account_id=person.account_id,
                    contact_type_code="EMAIL",
                    value="dubbel@example.org",
                    is_primary=True,
                    confirmed_at=person.created_at,
                    created_at=person.created_at,
                    updated_at=person.created_at,
                )
            )
        db_session.commit()
    for tenant in (TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID):
        with _At(tenant):
            assert sign_in_identity(db_session, "dubbel@example.org")[0] == MULTIPLE


# ── Word lid at a second department (A3, AC2) ───────────────────────────────


def test_word_lid_at_a_second_department_joins_with_the_existing_household(client, db_session):
    """Koen, 19 October 2026: "1a" — the page that pays a membership, without
    the way back to Mijn gezin; the payment makes a membership of the existing
    household here, not a second household."""
    from datetime import datetime, timezone

    from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
    from app.domains.membership.api import Membership

    household, person = create_test_family(db_session, email="aansluiten@example.org")
    at_tenant(db_session, household, TENANT_MILLEGEM_ID)
    db_session.query(ContactDetail).filter_by(person_id=person.id).update(
        {"confirmed_at": datetime.now(timezone.utc)}
    )
    db_session.commit()
    session = make_session_value("aansluiten@example.org")
    client.cookies.set(SESSION_COOKIE, session)

    page = client.get("/raakvoorbeeldafdeling/lid-worden").text
    main = page[page.index('<main id="main"') : page.index("</main>")]
    assert ">Lidmaatschap betalen</h1>" in main
    assert "Naar Mijn gezin" not in main and "‹ Mijn gezin" not in main
    assert 'name="payment_method"' in main

    answer = client.post(
        "/raakvoorbeeldafdeling/leden/gezin/vernieuwen",
        data={"payment_method": "transfer"},
        headers={"X-CSRF-Token": csrf_token_for(session)},
    )
    assert answer.status_code == 200, answer.text[:300]
    db_session.expire_all()
    tenants = {
        m.tenant_id
        for m in db_session.query(Membership)
        .execution_options(include_all_tenants=True)
        .filter(Membership.member_id == household.id)
    }
    assert tenants == {TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID}
    assert db_session.query(MemberPerson).filter_by(person_id=person.id).count() == 1


# ── The import recognises a known person (C2 mdm) ───────────────────────────


def test_the_import_links_a_member_of_another_department_by_e_mail(db_session):
    """A row of the Voorbeeldafdeling's report whose e-mail address is a person
    of the account — a member of Millegem — adds the department's member number
    and membership to that person and household; no second person."""
    from app.domains.mdm.import_service import upsert_families
    from tests.conftest import seed_postal_code

    seed_postal_code(db_session)
    with _At(TENANT_MILLEGEM_ID):
        household, person = create_test_family(db_session, email="bekend@example.org")
        person.first_name, person.last_name = "Bekend", "Lid"
        at_tenant(db_session, household, TENANT_MILLEGEM_ID)
        db_session.commit()
    row = {
        "lidnr": "88001",
        "voornaam": "Bekend",
        "naam": "Lid",
        "straat": "Kerkstraat",
        "huisnummer": "1",
        "busnummer": "",
        "postcode": "2400",
        "gemeente": "Mol",
        "email": "bekend@example.org",
        "telefoon": None,
        "gsm": None,
        "geboortedatum": None,
        "geslacht": None,
        "bestuurslid": None,
        "_relatie": "HOOFDLID",
    }
    with _At(TENANT_VOORBEELD_ID):
        report = upsert_families(db_session, [[row]], {}, [], apply=True)
        db_session.commit()
    same = (
        db_session.query(Person)
        .execution_options(include_all_tenants=True)
        .filter(Person.first_name == "Bekend", Person.last_name == "Lid")
        .all()
    )
    assert [p.id for p in same] == [person.id], "known and linked, not made again"
    assert any("bekend #88001" in line for line in report.lines), report.lines
    from app.domains.membership.api import Membership

    tenants = {
        m.tenant_id
        for m in db_session.query(Membership)
        .execution_options(include_all_tenants=True)
        .filter(Membership.member_id == household.id)
    }
    assert tenants == {TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID}


def _shared_household(db, millegem_year: int):
    """A household of Millegem with two persons — a main member the
    Voorbeeldafdeling's report will list, and a child only Millegem knows — and an
    active membership at Millegem for `millegem_year`."""
    with _At(TENANT_MILLEGEM_ID):
        household, main = create_test_family(db, email="gedeeld@example.org")
        main.first_name, main.last_name = "Gedeeld", "Lid"
        child = create_test_person(db)
        child.first_name, child.last_name = "Enkel", "Millegem"
        db.add(MemberPerson(member_id=household.id, person_id=child.id, relation_type="KIND"))
        at_tenant(db, household, TENANT_MILLEGEM_ID, year=millegem_year).is_active = True
        db.commit()
    return household, child


def _report_of_the_main_member_only():
    return [
        [
            {
                "lidnr": "88002",
                "voornaam": "Gedeeld",
                "naam": "Lid",
                "straat": "Kerkstraat",
                "huisnummer": "1",
                "busnummer": "",
                "postcode": "2400",
                "gemeente": "Mol",
                "email": "gedeeld@example.org",
                "telefoon": None,
                "gsm": None,
                "geboortedatum": None,
                "geslacht": None,
                "bestuurslid": None,
                "_relatie": "HOOFDLID",
            }
        ]
    ]


def _members_of(db, household_id: int) -> set[int]:
    return {
        mp.person_id
        for mp in db.query(MemberPerson)
        .execution_options(include_all_tenants=True)
        .filter(MemberPerson.member_id == household_id)
    }


def test_the_import_keeps_whom_another_department_still_counts(db_session):
    """The Voorbeeldafdeling's report links the main member of a household that is
    still a member at Millegem, and leaves out the child: the child stays, in the
    dry run as in the run, and each names it once with the count (Koen, 19 October
    2026: "b").

    Proven red, additively: `elsewhere = False` added after the call of
    `member_at_another_tenant` in `_sync_family` → the dry run counts the child
    as removed, and the run takes it out of the household.
    """
    from app.domains.mdm.import_service import IMPORT_YEAR, upsert_families
    from tests.conftest import seed_postal_code

    seed_postal_code(db_session)
    household, child = _shared_household(db_session, IMPORT_YEAR)
    with _At(TENANT_VOORBEELD_ID):
        dry = upsert_families(db_session, _report_of_the_main_member_only(), {}, [], apply=False)
        run = upsert_families(db_session, _report_of_the_main_member_only(), {}, [], apply=True)
        db_session.commit()
    for report in (dry, run):
        assert (report.persons_removed, report.persons_kept_elsewhere) == (0, 1)
        assert [w for w in report.warnings if "Enkel Millegem" in w], report.warnings
        assert not [line for line in report.lines if "verwijderd" in line], report.lines
    assert child.id in _members_of(db_session, household.id)


def test_the_import_removes_whom_no_other_department_counts_any_more(db_session):
    """The same report, but Millegem's membership is of an earlier year: no other
    department counts the household now, so the child leaves it, as before."""
    from app.domains.mdm.import_service import IMPORT_YEAR, upsert_families
    from tests.conftest import seed_postal_code

    seed_postal_code(db_session)
    household, child = _shared_household(db_session, IMPORT_YEAR - 1)
    with _At(TENANT_VOORBEELD_ID):
        report = upsert_families(db_session, _report_of_the_main_member_only(), {}, [], apply=True)
        db_session.commit()
    assert (report.persons_removed, report.persons_kept_elsewhere) == (1, 0)
    assert child.id not in _members_of(db_session, household.id)
