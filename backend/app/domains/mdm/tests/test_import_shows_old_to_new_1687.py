"""The member import's check shows what changes, from the old value to the new (#1687).

Koen, 7 October 2026: the details of the check said which fields change —
"velden: telefoon, gsm", "velden: relatie" — and not from what to what, so a
change could not be judged before applying it.

Each line of a change now carries `<field>: <old> → <new>`, built from the
pair the deciding function returns. The words are Koen's choice of the same
day: Mobiel, E-mail, Telefoon and the relation's label from the code tables;
the fields of a person and an address in the words of the household record.

On made-up data, through the import's own entry point.

Broken on purpose (7 October 2026), each red for its own reason: the line built
from the report's column names again → every line test; a number shown as
stored → the contact line; the old value taken after the write → the applied
import shows "new → new" while the dry run shows "old → new"; the "#?" put
back → the removed person without a number.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest

from app.domains.mdm.api import Member, MemberPerson, Person
from app.domains.mdm.import_service import upsert_families
from app.kernel.codes import code_label
from tests.conftest import seed_postal_code

pytestmark = pytest.mark.ui_agnostisch


def _row(lidnr, voornaam, naam, relatie, **more):
    row = {
        "lidnr": lidnr,
        "voornaam": voornaam,
        "naam": naam,
        "straat": "milostraat",
        "huisnummer": "1",
        "busnummer": "",
        "postcode": "2400",
        "gemeente": "Mol",
        "email": None,
        "telefoon": None,
        "gsm": None,
        "geboortedatum": date(1980, 5, 1),
        "geslacht": "M",
        "bestuurslid": None,
        "_relatie": relatie,
    }
    return row | more


def _first():
    return [
        [
            _row("100", "An", "Aerts", "HOOFDLID", email="an@example.com", gsm="0470112233"),
            _row("101", "Bo", "Aerts", "PARTNER"),
        ],
        [
            _row("200", "Cas", "Boons", "HOOFDLID", huisnummer="2"),
            _row("201", "Dirk", "Boons", "KIND", huisnummer="2"),
        ],
    ]


def _second():
    return [
        [
            _row(
                "100",
                "Ann",
                "Aerts",
                "HOOFDLID",
                huisnummer="5",
                email=None,
                telefoon="014123456",
                gsm="0470445566",
                geboortedatum=date(1981, 6, 2),
                geslacht="F",
            ),
            _row("101", "Bo", "Aerts", "KIND", huisnummer="5"),
            _row("102", "Cleo", "Aerts", "KIND", huisnummer="5", email="cleo@example.com"),
        ],
        [_row("200", "Cas", "Boons", "HOOFDLID", huisnummer="2")],
    ]


@pytest.fixture
def imported(db_session):
    seed_postal_code(db_session)
    upsert_families(db_session, _first(), {}, [], apply=True)
    # Someone without a member number in the second household: the report does
    # not list her, so the import removes her from it.
    cas = db_session.query(Person).filter_by(first_name="Cas").one()
    household = db_session.query(MemberPerson).filter_by(person_id=cas.id).one().member_id
    zoe = Person(first_name="Zoë", last_name="Boons", date_of_birth=date(2001, 1, 1))
    db_session.add(zoe)
    db_session.flush()
    db_session.add(MemberPerson(member_id=household, person_id=zoe.id, relation_type="KIND"))
    db_session.commit()
    assert db_session.get(Member, household) is not None


def _lines(db, *, apply: bool) -> list[str]:
    return list(upsert_families(db, _second(), {}, [], apply=apply).lines)


def test_every_change_line_carries_the_old_and_the_new_value(db_session, imported):
    """Red on master: "velden: naam, …", "velden: email, telefoon, gsm"."""
    lines = _lines(db_session, apply=False)
    man, vrouw = code_label("gender", "M"), code_label("gender", "F")
    partner, kind = code_label("relation_type", "PARTNER"), code_label("relation_type", "KIND")
    assert (
        "  ~ update #100  Ann Aerts  Voornaam: An → Ann; "
        f"Geboortedatum: 01-05-1980 → 02-06-1981; Geslacht: {man} → {vrouw}"
    ) in lines
    assert (
        "  ~ adres #100  Ann Aerts  Adres: milostraat 1, 2400 Mol → milostraat 5, 2400 Mol"
    ) in lines
    assert (
        "  ~ contact #100  Ann Aerts  E-mail: an@example.com → (verwijderd); "
        "Telefoon: — → 014 12 34 56; Mobiel: 0470 11 22 33 → 0470 44 55 66"
    ) in lines
    assert f"  ~ update #101  Bo Aerts  Relatie: {partner} → {kind}" in lines
    assert kind == "(meerderjarig) kind", "the relation reads by the code table's own label"
    text = "\n".join(lines)
    assert "velden:" not in text, "a line still names fields without their values"
    for stored in ("0470112233", "0470445566", "014123456", "MOBILE", "gsm", "telefoon"):
        assert stored not in text, f"{stored} reached the line as stored"


def test_a_new_person_shows_the_new_values_only(db_session, imported):
    lines = _lines(db_session, apply=False)
    assert "  + contact #102  Cleo Aerts  E-mail: cleo@example.com" in lines
    assert not [line for line in lines if "#102" in line and "→" in line]


def test_a_removed_person_shows_the_number_it_has_and_no_question_mark(db_session, imported):
    """Red on master: "- verwijderd  #?  Zoë Boons"."""
    lines = _lines(db_session, apply=False)
    assert "  - verwijderd  #201  Dirk Boons" in lines
    assert "  - verwijderd  Zoë Boons" in lines
    assert "#?" not in "\n".join(lines)


def test_the_dry_run_and_the_applied_import_print_the_same_lines(db_session, imported):
    """The old value is read BEFORE the write: an applied import that read it
    after would print "new → new"."""
    dry = _lines(db_session, apply=False)
    applied = _lines(db_session, apply=True)
    assert applied == dry and len(dry) >= 8
    db_session.commit()
    db_session.expire_all()
    again = _lines(db_session, apply=False)
    assert again == [], f"a second run of the same report still changes: {again}"


def test_no_detail_line_reaches_the_application_log(db_session, imported, caplog):
    """The lines hold personal data for the administrator's screen only."""
    with caplog.at_level(logging.DEBUG):
        lines = _lines(db_session, apply=True)
    assert lines
    logged = "\n".join(record.getMessage() for record in caplog.records)
    for secret in ("0470 44 55 66", "0470445566", "an@example.com", "Ann Aerts", "milostraat 5"):
        assert secret not in logged, f"{secret} was written to the log"
