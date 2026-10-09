"""The database holds one main member per household (#1832).

The rule is the service's (`require_one_main_member`); the member import does
not load an address group that would break it. This constraint is the net under
both, for a writer that does not ask.

So the tests write past the service on purpose: a second main-member link
straight into the session. That is the additive violation — something is added
that may not exist, nothing that exists is broken to prove it.

The constraint is checked when the transaction ends. A test never commits, so
each test asks for the check itself (`_end_of_transaction`), and the suite's
session fixture asks it once more after every test (`tests/conftest.py`).

Proven red, one replacement each in the migration, restored afterwards — the
counts stand in the pull request: the constraint not added (the violation is
stored without a word, "DID NOT RAISE"); the predicate without
`deleted_at IS NULL` (the softly deleted main member stands in the way);
without `DEFERRABLE INITIALLY DEFERRED` (the passing state fails at its flush).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domains.mdm.api import Member, MemberPerson, Person, RelationType

CONSTRAINT = "ex_member_persons_one_main_member"


def _person(db, first_name: str) -> Person:
    person = Person(
        first_name=first_name, last_name="Peeters", date_of_birth=date(1980, 5, 1), gender_code="M"
    )
    db.add(person)
    db.flush()
    return person


def _link(db, household: Member, first_name: str, relation: RelationType) -> MemberPerson:
    link = MemberPerson(
        member_id=household.id, person_id=_person(db, first_name).id, relation_type=relation
    )
    db.add(link)
    db.flush()
    return link


def _household(db) -> Member:
    household = Member()
    db.add(household)
    db.flush()
    return household


def _end_of_transaction(db) -> None:
    """What a commit checks, asked now."""
    db.flush()
    db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    db.execute(text("SET CONSTRAINTS ALL DEFERRED"))


def test_the_constraint_is_there_with_its_predicate(db_session):
    """The test database is built by the migrations: this reads what they made."""
    row = db_session.execute(
        text(
            "SELECT pg_get_constraintdef(oid), condeferrable, condeferred "
            "FROM pg_constraint WHERE conname = :name"
        ),
        {"name": CONSTRAINT},
    ).one_or_none()
    assert row, "the migration made no constraint"
    definition, deferrable, deferred = row
    assert "EXCLUDE" in definition and "member_id WITH =" in definition
    assert "HOOFDLID" in definition and "deleted_at IS NULL" in definition
    assert deferrable and deferred


def test_a_second_main_member_is_refused_by_the_database(db_session):
    household = _household(db_session)
    _link(db_session, household, "Piet", RelationType.PRIMARY_MEMBER)
    _link(db_session, household, "Mia", RelationType.PRIMARY_MEMBER)

    with pytest.raises(IntegrityError) as refused:
        _end_of_transaction(db_session)

    assert CONSTRAINT in str(refused.value)


def test_two_main_members_on_the_way_to_one_are_let_through(db_session):
    """What the member import does: the new main member arrives, then the old one
    becomes a partner. Only the end counts."""
    household = _household(db_session)
    old = _link(db_session, household, "Piet", RelationType.PRIMARY_MEMBER)
    _link(db_session, household, "Mia", RelationType.PRIMARY_MEMBER)
    old.relation_type = RelationType.PARTNER

    _end_of_transaction(db_session)


def test_a_partner_and_children_beside_the_main_member_are_fine(db_session):
    household = _household(db_session)
    _link(db_session, household, "Piet", RelationType.PRIMARY_MEMBER)
    _link(db_session, household, "Mia", RelationType.PARTNER)
    _link(db_session, household, "Kim", RelationType.ADULT_CHILD)
    _link(db_session, household, "Lou", RelationType.ADULT_CHILD)

    _end_of_transaction(db_session)
    assert db_session.query(MemberPerson).filter_by(member_id=household.id).count() == 4


def test_every_household_has_its_own_main_member(db_session):
    _link(db_session, _household(db_session), "Piet", RelationType.PRIMARY_MEMBER)
    _link(db_session, _household(db_session), "Mia", RelationType.PRIMARY_MEMBER)

    _end_of_transaction(db_session)


def test_a_softly_deleted_main_member_does_not_stand_in_the_way(db_session):
    """Living links only: the household whose main member was removed gets a new one."""
    household = _household(db_session)
    old = _link(db_session, household, "Piet", RelationType.PRIMARY_MEMBER)
    old.deleted_at = datetime.now(timezone.utc)
    db_session.flush()
    _link(db_session, household, "Mia", RelationType.PRIMARY_MEMBER)

    _end_of_transaction(db_session)


def test_a_deleted_main_member_does_not_come_back_beside_another(db_session):
    """The other side of "living links only": the old link cannot be revived
    while the household has a new main member."""
    household = _household(db_session)
    old = _link(db_session, household, "Piet", RelationType.PRIMARY_MEMBER)
    old.deleted_at = datetime.now(timezone.utc)
    db_session.flush()
    _link(db_session, household, "Mia", RelationType.PRIMARY_MEMBER)
    old.deleted_at = None

    with pytest.raises(IntegrityError):
        _end_of_transaction(db_session)


def test_a_commit_refuses_two_main_members():
    """The proof that needs no helper: a transaction of its own that really
    commits. The commit fails, so nothing of it stays in the test database — and
    should it ever succeed, the test removes what it stored before it fails."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        household = _household(db)
        links = [
            _link(db, household, "Piet", RelationType.PRIMARY_MEMBER),
            _link(db, household, "Mia", RelationType.PRIMARY_MEMBER),
        ]
        made = [*links, *(link.person for link in links), household]
        try:
            db.commit()
        except IntegrityError as refused:
            assert CONSTRAINT in str(refused)
        else:
            for row in made:
                db.delete(row)
                db.flush()
            db.commit()
            pytest.fail("the commit stored a household with two main members")
    finally:
        db.rollback()
        db.close()


def test_the_suites_own_check_catches_a_test_that_leaves_two_main_members(db_session):
    """The session fixture asks after every test what a commit would check
    (`tests/conftest.py`). This is that check, called on a session that holds the
    violation: it fails the test. Without it a deferred constraint is never
    checked in a suite that never commits."""
    from tests.conftest import _check_deferred_constraints

    household = _household(db_session)
    _link(db_session, household, "Piet", RelationType.PRIMARY_MEMBER)
    _link(db_session, household, "Mia", RelationType.PRIMARY_MEMBER)

    with pytest.raises(pytest.fail.Exception) as caught:
        _check_deferred_constraints(db_session.connection())

    assert CONSTRAINT in str(caught.value)
