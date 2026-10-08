"""CR-13 phase 3 (#1250): the rules of a person and a household link, at their addresses.

- **one field** — a person always has a first and a last name (Koen, 29 September
  2026): `@validates` on `Person`, and `ck_persons_*_not_blank` at rest;
- **the household link** — a member of a household has a birth date and a gender
  (#681): `MemberPerson.check()` for a new, moved or revived link, `Person.check()`
  for a change to a person who is in a household, both fired by the flush listener
  without anyone calling them;
- **one named exception** — the member report import reads an incomplete member in
  and reports it (Koen, 29 September 2026): `kernel.rules.exempt` with
  `MEMBER_REPORT_IMPORT`, for that transaction only.

Broken on purpose to check these tests can go red (run, then restored), each
additively, with what failed:

- `return` as the first line of `MemberPerson.check()` → three: the new link, the
  revived link, and the exemption test (its second link went through). The import
  pair stays green, because the portal side asks `require_details` before it
  writes — the early question, not the flush;
- `return` as the first line of `Person.check()` → two: clearing a member's birth
  date, and a new name for an old incomplete member;
- `return` as the first line of `kernel.rules._end_exemptions` → one: "the
  exemption outlives no transaction" — the commit listener is what ends it.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domains.mdm.api import (
    MEMBER_REPORT_IMPORT,
    ContactDetail,
    MasterDataError,
    Member,
    MemberPerson,
    Person,
    PersonDetailsMissing,
)
from app.domains.mdm.models import HOUSEHOLD_MEMBER_DETAILS
from app.kernel import rules

pytestmark = pytest.mark.ui_agnostisch


def _household(db) -> Member:
    household = Member()
    db.add(household)
    db.flush()
    return household


def _person(db, **values) -> Person:
    person = Person(first_name="Tine", last_name="Regel", **values)
    db.add(person)
    db.flush()
    return person


def _complete(db) -> Person:
    return _person(db, date_of_birth=date(1985, 2, 3), gender_code="F")


def _incomplete_member_at_rest(db) -> tuple[Person, MemberPerson]:
    """An old row from before #681: written past the objects, as PROD holds two."""
    household = _household(db)
    person_id = db.execute(
        text(
            "INSERT INTO mdm.persons (first_name, last_name, tenant_id, created_at, updated_at) "
            "VALUES ('Oud', 'Lid', 2, now(), now()) RETURNING id"
        )
    ).scalar()
    link_id = db.execute(
        text(
            "INSERT INTO mdm.member_persons "
            "(member_id, person_id, relation_type, tenant_id, created_at, updated_at) "
            "VALUES (:m, :p, 'HOOFDLID', 2, now(), now()) RETURNING id"
        ),
        {"m": household.id, "p": person_id},
    ).scalar()
    db.expire_all()
    return db.get(Person, person_id), db.get(MemberPerson, link_id)


# ── A person has a name ──────────────────────────────────────────────────────


@pytest.mark.parametrize("field", ["first_name", "last_name"])
@pytest.mark.parametrize("value", ["", "   "])
def test_a_person_without_a_name_is_refused_on_assignment(field, value):
    person = Person(first_name="Jan", last_name="Peeters")
    with pytest.raises(MasterDataError):
        setattr(person, field, value)


def test_a_blank_name_is_refused_at_rest_too(db_session):
    """A bulk path passes no validator; the CHECK of migration 172 still refuses."""
    person = _complete(db_session)
    with pytest.raises(IntegrityError, match="ck_persons_last_name_not_blank"):
        with db_session.begin_nested():
            db_session.execute(
                text("UPDATE mdm.persons SET last_name = ' ' WHERE id = :id"), {"id": person.id}
            )


# ── A member of a household has a birth date and a gender (#681) ─────────────


def test_a_new_link_to_an_incomplete_person_is_refused_without_a_call(db_session):
    """No function called: the flush listener runs `MemberPerson.check()`."""
    household = _household(db_session)
    person = _person(db_session, date_of_birth=None, gender_code="M")
    db_session.add(MemberPerson(member_id=household.id, person_id=person.id))
    with pytest.raises(PersonDetailsMissing):
        db_session.flush()


def test_without_the_listener_the_same_flush_goes_through(db_session):
    """The other direction: the refusal above comes from the listener."""
    household = _household(db_session)
    person = _person(db_session, date_of_birth=None, gender_code="M")
    rules.uninstall_flush_checks()
    try:
        db_session.add(MemberPerson(member_id=household.id, person_id=person.id))
        db_session.flush()
    finally:
        rules.install_flush_checks()


def test_a_person_outside_a_household_needs_neither(db_session):
    """The meeting circle (#939): a person, not a member — the rule does not apply."""
    person = _person(db_session, date_of_birth=None, gender_code=None)
    person.first_name = "Ondersteuner"
    db_session.flush()


def test_clearing_the_birth_date_of_a_member_is_refused(db_session):
    household = _household(db_session)
    person = _complete(db_session)
    db_session.add(MemberPerson(member_id=household.id, person_id=person.id))
    db_session.flush()
    person.date_of_birth = None
    with pytest.raises(PersonDetailsMissing):
        db_session.flush()


def test_an_old_incomplete_member_can_still_be_merged_or_deleted(db_session):
    """The rule speaks when the person's details change, not on bookkeeping — so a
    merge or a soft delete of a row from before #681 stays possible."""
    person, _link = _incomplete_member_at_rest(db_session)
    survivor = _complete(db_session)
    person.superseded_by_id = survivor.id
    db_session.flush()
    person.deleted_at = survivor.created_at
    db_session.flush()


def test_changing_an_old_incomplete_member_asks_for_the_two_fields(db_session):
    """Judged on the outcome: a new name for a member without a birth date is
    refused until the birth date is there — as the portal has done since #681."""
    person, _link = _incomplete_member_at_rest(db_session)
    person.first_name = "Nieuw"
    with pytest.raises(PersonDetailsMissing):
        db_session.flush()


def test_a_link_that_comes_back_from_a_soft_delete_is_checked_again(db_session):
    person, link = _incomplete_member_at_rest(db_session)
    db_session.execute(
        text("UPDATE mdm.member_persons SET deleted_at = now() WHERE id = :id"), {"id": link.id}
    )
    db_session.expire_all()
    link = (
        db_session.query(MemberPerson)
        .execution_options(include_deleted=True)
        .filter(MemberPerson.id == link.id)
        .one()
    )
    link.deleted_at = None
    with pytest.raises(PersonDetailsMissing):
        db_session.flush()


# ── The one exception, by name: the member report import ─────────────────────


def _report_row(**values) -> dict:
    row = {
        "lidnr": "990001",
        "voornaam": "Onvolledig",
        "naam": "Uitrapport",
        "straat": "Rapportstraat",
        "huisnummer": "1",
        "busnummer": "",
        "postcode": "2400",
        "gemeente": "Mol",
        "email": None,
        "telefoon": None,
        "gsm": None,
        "geboortedatum": None,
        "geslacht": "M",
        "bestuurslid": None,
        "_relatie": "HOOFDLID",
    }
    row.update(values)
    return row


def test_the_import_reads_an_incomplete_member_in_and_the_portal_refuses_one(db_session):
    """Both sides of Koen's decision (29 September 2026), side by side: the report of
    Raak Nationaal is read in, incomplete member and all, with a warning — and the
    same member is refused on the portal, the way every other path refuses it."""
    from app.domains.mdm.household_service import insert_household_person
    from app.domains.mdm.import_service import upsert_families
    from tests.conftest import seed_postal_code

    seed_postal_code(db_session)
    report = upsert_families(db_session, [[_report_row()]], {}, [], apply=True)
    db_session.commit()

    person = db_session.query(Person).filter(Person.last_name == "Uitrapport").one()
    assert person.date_of_birth is None
    assert [link for link in person.member_persons if link.deleted_at is None], (
        "the import did not link the incomplete member to a household"
    )
    assert any("Uitrapport" in w and "geboortedatum" in w for w in report.warnings), report.warnings

    household = person.member_persons[0].member
    with pytest.raises(PersonDetailsMissing):
        insert_household_person(
            db_session,
            household,
            {"first_name": "Kind", "last_name": "Uitrapport", "gender_code": "M"},
            actor=None,
        )


def test_the_exemption_outlives_no_transaction(db_session):
    """Granted for one transaction: after its commit, the next incomplete link in the
    same session is refused again."""
    rules.exempt(db_session, HOUSEHOLD_MEMBER_DETAILS, MEMBER_REPORT_IMPORT)
    household = _household(db_session)
    first = _person(db_session, date_of_birth=None, gender_code="M")
    db_session.add(MemberPerson(member_id=household.id, person_id=first.id))
    db_session.commit()

    second = _person(db_session, date_of_birth=None, gender_code="M")
    db_session.add(MemberPerson(member_id=household.id, person_id=second.id))
    with pytest.raises(PersonDetailsMissing):
        db_session.flush()


# ── primary_contact(type) ────────────────────────────────────────────────────


def _contact(db, person, value, *, primary, kind="EMAIL"):
    db.add(
        ContactDetail(person_id=person.id, contact_type_code=kind, value=value, is_primary=primary)
    )
    db.flush()


def test_the_primary_contact_is_the_marked_one(db_session):
    person = _complete(db_session)
    _contact(db_session, person, "extra@example.com", primary=False)
    _contact(db_session, person, "hoofd@example.com", primary=True)
    _contact(db_session, person, "0470000000", primary=True, kind="MOBILE")
    db_session.refresh(person)
    assert person.primary_contact("EMAIL").value == "hoofd@example.com"
    assert person.primary_contact("MOBILE").value == "0470000000"


def test_without_a_marked_one_any_contact_of_that_kind_answers(db_session):
    """#1174: the index allows at most one primary, not at least one."""
    person = _complete(db_session)
    _contact(db_session, person, "enige@example.com", primary=False)
    db_session.refresh(person)
    assert person.primary_contact("EMAIL").value == "enige@example.com"
    assert person.primary_contact("PHONE") is None
