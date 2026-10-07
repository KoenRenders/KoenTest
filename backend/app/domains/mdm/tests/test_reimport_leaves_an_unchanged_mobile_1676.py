"""A re-import logs nothing for a mobile number that did not change (#1676).

Found on PROD on 6 October 2026: every import of the national member report
listed "Gewijzigd · Contact · MOBILE" for the members who also have a landline,
with the number they already had. Ten rows, two identical history rows each.
"""

from __future__ import annotations

import pytest

from app.domains.mdm.codes import CONTACT
from app.domains.mdm.import_service import _sync_contacts
from app.domains.mdm.models import ContactDetail, ContactDetailHistory, Person

pytestmark = pytest.mark.ui_serverrendered

ROW = {"email": "lid-1676@example.com", "telefoon": "014123456", "gsm": "0470123456"}


#: Since #1687 a change is a `FieldChange` keyed by its contact type; these tests
#: speak in the report's columns.
_COLUMN = {"EMAIL": "email", "PHONE": "telefoon", "MOBILE": "gsm"}


def _columns(changes) -> list[str]:
    return [_COLUMN[c.key] for c in changes]


def _person(db) -> Person:
    person = Person(first_name="Proef", last_name="Herimport")
    db.add(person)
    db.flush()
    return person


def _rows(db, person: Person) -> list[tuple]:
    db.expire_all()
    return sorted(
        (c.contact_type_code, c.value, bool(c.is_primary))
        for c in db.query(ContactDetail).filter(ContactDetail.person_id == person.id)
    )


def _history(db, person: Person) -> int:
    ids = [c.id for c in db.query(ContactDetail).filter(ContactDetail.person_id == person.id)]
    return (
        db.query(ContactDetailHistory)
        .filter(ContactDetailHistory.contact_detail_id.in_(ids))
        .count()
    )


def test_the_same_row_imported_twice_changes_nothing_the_second_time(db_session):
    """Red on master: the second import returns ["gsm"] and writes a history
    row that changes nothing."""
    person = _person(db_session)
    assert _columns(_sync_contacts(db_session, person, ROW, apply=True)) == [
        "email",
        "telefoon",
        "gsm",
    ]
    db_session.flush()
    db_session.refresh(person)
    before = _rows(db_session, person), _history(db_session, person)

    assert _sync_contacts(db_session, person, ROW, apply=False) == [], (
        "the dry run reports a change"
    )
    assert _sync_contacts(db_session, person, ROW, apply=True) == [], "the import reports a change"
    db_session.flush()

    assert (_rows(db_session, person), _history(db_session, person)) == before


def _imported(db, row=ROW) -> Person:
    person = _person(db)
    _sync_contacts(db, person, row, apply=True)
    db.flush()
    db.refresh(person)
    return person


def _legacy(db) -> Person:
    """A person as the import wrote them until #1676: the mobile number next to
    a landline as a NON-primary row."""
    person = _person(db)
    db.add_all(
        [
            ContactDetail(
                person_id=person.id,
                contact_type_code=CONTACT.PHONE,
                value="014123456",
                is_primary=True,
            ),
            ContactDetail(
                person_id=person.id,
                contact_type_code=CONTACT.MOBILE,
                value="0470123456",
                is_primary=False,
            ),
        ]
    )
    db.flush()
    db.refresh(person)
    return person


def _again(db, person, row, *, apply=True) -> list[str]:
    changed = _columns(_sync_contacts(db, person, row, apply=apply))
    db.flush()
    db.refresh(person)
    return changed


def test_a_mobile_number_is_the_primary_row_of_its_type_also_next_to_a_landline(db_session):
    person = _imported(db_session)
    assert _rows(db_session, person) == [
        ("EMAIL", "lid-1676@example.com", True),
        ("MOBILE", "0470123456", True),
        ("PHONE", "014123456", True),
    ]


def test_another_number_in_the_report_replaces_the_row(db_session):
    """Red on master: a second mobile row beside the first."""
    person = _imported(db_session)
    history = _history(db_session, person)

    assert _again(db_session, person, ROW | {"gsm": "0470999999"}) == ["gsm"]

    assert [r for r in _rows(db_session, person) if r[0] == "MOBILE"] == [
        ("MOBILE", "0470999999", True)
    ]
    assert _history(db_session, person) == history + 1, "one update, no more"


def test_an_emptied_cell_removes_the_row_and_leaves_an_address_we_collected(db_session):
    """Red on master: the mobile row stayed. The extra e-mail address is ours
    (#1174) and no import touches it."""
    person = _imported(db_session)
    db_session.add(
        ContactDetail(
            person_id=person.id,
            contact_type_code=CONTACT.EMAIL,
            value="extra-1676@example.com",
            is_primary=False,
        )
    )
    db_session.flush()
    db_session.refresh(person)

    assert _again(db_session, person, ROW | {"gsm": ""}) == ["gsm"]

    assert _rows(db_session, person) == [
        ("EMAIL", "extra-1676@example.com", False),
        ("EMAIL", "lid-1676@example.com", True),
        ("PHONE", "014123456", True),
    ]


def test_a_row_of_the_first_import_is_adopted_once_and_then_left_alone(db_session):
    """The ten rows on PROD: the first import after the deploy makes the mobile
    row the primary one — one real change, said in the dry run too — and every
    import after it changes nothing."""
    person = _legacy(db_session)
    before = _rows(db_session, person), _history(db_session, person)

    assert _again(db_session, person, ROW, apply=False) == ["email", "gsm"]
    assert (_rows(db_session, person), _history(db_session, person)) == before, (
        "the dry run wrote something"
    )

    assert _again(db_session, person, ROW) == ["email", "gsm"]
    assert [r for r in _rows(db_session, person) if r[0] == "MOBILE"] == [
        ("MOBILE", "0470123456", True)
    ]
    after = _history(db_session, person)
    assert after == before[1] + 2, "the e-mail address and the one promotion"

    assert _again(db_session, person, ROW, apply=False) == []
    assert _again(db_session, person, ROW) == []
    assert _history(db_session, person) == after


def test_a_row_of_the_first_import_takes_a_changed_number_instead_of_a_second_row(db_session):
    person = _legacy(db_session)
    assert "gsm" in _again(db_session, person, ROW | {"gsm": "0470999999"})
    assert [r for r in _rows(db_session, person) if r[0] == "MOBILE"] == [
        ("MOBILE", "0470999999", True)
    ]


def test_a_row_of_the_first_import_goes_with_an_emptied_cell(db_session):
    person = _legacy(db_session)
    assert "gsm" in _again(db_session, person, ROW | {"gsm": ""})
    assert [r for r in _rows(db_session, person) if r[0] == "MOBILE"] == []


def test_with_two_primary_rows_the_one_with_the_reports_value_is_the_row(db_session):
    """Two primary mobile rows for one person exist on two environments. The
    row is chosen, never "the first one": the one that holds the report's
    value, else the oldest — and the other row is not touched."""
    from types import SimpleNamespace

    from app.domains.mdm.service import upsert_primary_contact

    old = SimpleNamespace(
        id=1, contact_type_code=CONTACT.MOBILE, value="0470111111", is_primary=True
    )
    new = SimpleNamespace(
        id=2, contact_type_code=CONTACT.MOBILE, value="0470123456", is_primary=True
    )
    for order in ([old, new], [new, old]):
        person = SimpleNamespace(contact_details=list(order))
        same = upsert_primary_contact(
            db_session, person, CONTACT.MOBILE, "0470123456", action="x", source="x", apply=False
        )
        assert same is None, "the row with the report's value was not found"
        other = upsert_primary_contact(
            db_session, person, CONTACT.MOBILE, "0470999999", action="x", source="x", apply=False
        )
        assert other is not None and (other.old, other.new) == ("0470111111", "0470999999")
