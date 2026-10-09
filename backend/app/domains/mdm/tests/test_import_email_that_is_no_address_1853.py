"""The member import does not take over an e-mail text that is no address (#1853).

The contact detail refuses such a text at every flush. For the report of the
national programme that would stop the whole import on one mistyped row. So the
import asks the rule first, as it already does for an address that is in use:
the person is read in WITHOUT that address, and the detail says so — in the
preview and in the run alike.

**A working assumption** (option a of three put to Koen on 9 October 2026; his
answer was not in when this was built): should he choose otherwise, this file
and the lines it tests in `import_service._sync_contacts` are what changes.

Red proof: the question removed from `_sync_contacts` → the run stops on
`EmailAddressInvalid` at the flush, and the preview says nothing.
"""

from __future__ import annotations

from app.domains.mdm.api import ContactDetail, Person
from app.domains.mdm.tests.test_import_says_what_it_refuses_1832 import _load, _row
from tests.conftest import seed_postal_code

NOT_TAKEN = "e-mailadres niet overgenomen — het is geen e-mailadres."


def _report(email: str) -> list[list[dict]]:
    main = _row("100", "Jan", "Janssens", "HOOFDLID")
    main["email"] = email
    return [[main, _row("101", "An", "Janssens", "PARTNER")]]


def _contacts(db, first_name: str) -> list[tuple[str, str]]:
    db.expire_all()
    person = db.query(Person).filter_by(first_name=first_name).one()
    return sorted(
        (c.contact_type_code, c.value)
        for c in db.query(ContactDetail).filter_by(person_id=person.id)
    )


def test_the_person_is_read_in_without_the_text_and_the_detail_says_so(db_session):
    seed_postal_code(db_session)

    report = _load(db_session, _report("jan zonder adres"))

    assert report.new_families == 1 and report.persons_added == 2 and report.skipped == 0
    (sentence,) = report.warnings
    assert sentence.startswith("#100 Jan Janssens: " + NOT_TAKEN)
    assert "Verbeter het in het rapport" in sentence
    # The rest of the row is loaded: the mobile number, and no e-mail row at all.
    assert [kind for kind, _value in _contacts(db_session, "Jan")] == ["MOBILE"]
    assert not any("E-mail" in line for line in report.lines)


def test_the_preview_says_the_same_as_the_run(db_session):
    seed_postal_code(db_session)

    preview = _load(db_session, _report("jan@"), apply=False)
    assert db_session.query(Person).count() == 0, "the preview wrote"
    run = _load(db_session, _report("jan@"))

    assert preview.warnings == run.warnings and len(run.warnings) == 1
    assert preview.lines == run.lines


def test_an_address_that_was_loaded_stays_when_the_report_spoils_it(db_session):
    """Not taken over means not written: the address the person had is not
    replaced by the text and not emptied either."""
    seed_postal_code(db_session)
    _load(db_session, _report("jan@example.com"))
    before = _contacts(db_session, "Jan")
    assert ("EMAIL", "jan@example.com") in before

    report = _load(db_session, _report("jan example.com"))

    assert _contacts(db_session, "Jan") == before
    assert any(NOT_TAKEN in sentence for sentence in report.warnings)
    assert report.updated_families == 0


def test_an_address_is_taken_over_as_before(db_session):
    seed_postal_code(db_session)

    report = _load(db_session, _report("jan.janssens@example.com"))

    assert not report.warnings
    assert ("EMAIL", "jan.janssens@example.com") in _contacts(db_session, "Jan")
