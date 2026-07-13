"""Fase 2 (#400): MDM — merge/survivorship, resolve, unmerge, organisaties."""
import pytest

from app.domains.mdm.api import (
    MergeError, Organization, Person, PersonHistory,
    merge_persons, resolve, unmerge_person,
)
from tests.conftest import create_test_person


def test_merge_sets_pointer_and_never_deletes(db_session):
    a = create_test_person(db_session, first_name="An", last_name="Dubbel")
    b = create_test_person(db_session, first_name="An", last_name="Dubbels")
    survivor = merge_persons(db_session, a.id, b.id, actor="admin@test")
    assert survivor.id == b.id
    assert a.superseded_by_id == b.id
    # Nooit hard weg: de bron bestaat nog.
    assert db_session.get(Person, a.id) is not None
    # Snapshot voor unmerge staat in de history.
    hist = (db_session.query(PersonHistory)
            .filter(PersonHistory.person_id == a.id,
                    PersonHistory.action == "person_merged").one())
    assert hist.actor == "admin@test" and hist.last_name == "Dubbel"


def test_merge_is_idempotent_and_flattens_chain(db_session):
    a = create_test_person(db_session)
    b = create_test_person(db_session)
    c = create_test_person(db_session)
    merge_persons(db_session, a.id, b.id)
    merge_persons(db_session, a.id, b.id)  # idempotent, geen fout
    # b -> c: de keten a -> b -> c wordt platgeslagen naar a -> c.
    merge_persons(db_session, b.id, c.id)
    db_session.expire_all()
    assert a.superseded_by_id == c.id and b.superseded_by_id == c.id
    assert resolve(db_session, a.id).id == c.id  # O(1), één stap


def test_merge_into_merged_target_lands_on_survivor(db_session):
    a = create_test_person(db_session)
    b = create_test_person(db_session)
    c = create_test_person(db_session)
    merge_persons(db_session, b.id, c.id)
    survivor = merge_persons(db_session, a.id, b.id)  # target is zelf gemerged
    assert survivor.id == c.id and a.superseded_by_id == c.id


def test_merge_rejects_self_and_unknown(db_session):
    p = create_test_person(db_session)
    with pytest.raises(MergeError):
        merge_persons(db_session, p.id, p.id)
    with pytest.raises(MergeError):
        merge_persons(db_session, p.id, 999_999_999)


def test_merge_publishes_entity_merged_event(db_session):
    from app.kernel.contracts.mdm import EntityMerged
    from app.kernel.events import subscribe, _subscribers

    seen = []

    def _handler(event, db):
        seen.append(event)

    subscribe(EntityMerged)(_handler)
    try:
        a = create_test_person(db_session)
        b = create_test_person(db_session)
        merge_persons(db_session, a.id, b.id)
        assert len(seen) == 1
        assert seen[0].entity_type == "person"
        assert (seen[0].source_id, seen[0].target_id) == (a.id, b.id)
    finally:
        _subscribers[EntityMerged].remove(_handler)


def test_unmerge_restores_person(db_session):
    a = create_test_person(db_session)
    b = create_test_person(db_session)
    merge_persons(db_session, a.id, b.id, actor="admin@test")
    unmerge_person(db_session, a.id, actor="admin@test")
    db_session.expire_all()
    assert a.superseded_by_id is None
    assert resolve(db_session, a.id).id == a.id
    hist = (db_session.query(PersonHistory)
            .filter(PersonHistory.person_id == a.id,
                    PersonHistory.action == "person_unmerged").one())
    assert hist.actor == "admin@test"
    with pytest.raises(MergeError):
        unmerge_person(db_session, a.id)  # niet (meer) gemerged


def test_resolve_plain_person_returns_itself(db_session):
    p = create_test_person(db_session)
    assert resolve(db_session, p.id).id == p.id
    assert resolve(db_session, 999_999_999) is None


def test_organizations_account_unit_hierarchy(db_session):
    account = Organization(code="raakmillegem", name="Raak Millegem", org_type="ACCOUNT")
    db_session.add(account)
    db_session.flush()
    unit = Organization(code="raakmillegem-jeugd", name="Jeugdwerking",
                        org_type="UNIT", parent_id=account.id)
    db_session.add(unit)
    db_session.flush()
    assert unit.parent.id == account.id
    from sqlalchemy.exc import IntegrityError
    db_session.add(Organization(code="fout", name="Fout type", org_type="WRONG"))
    with pytest.raises(IntegrityError):
        db_session.flush()
