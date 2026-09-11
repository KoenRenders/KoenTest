"""#870 (E from #529) — a person moving between households on import.

The coverage measurement on this tree showed `_sync_family` at 70 covered lines against 16
missing, and the missing ones are one specific branch: `import_service.py:442-462`, where a
person who already belongs to another household is **moved** — the old `MemberPerson` is
removed and a new one created. `_sync_address` (`293-299`) has the same shape for
overwriting an address.

The dry run was tested; this branch was not. It is the category that **corrupts silently**:
a fault here relocates members between households without anybody seeing an error message.

The correction in my own #529 report belongs here too: I first wrote that the writing path
was "largely untested", and that was too broad. It is tested; this one branch is not.

Broken on purpose to check that these tests can go red: the `db.delete(old_mp)` in the move
branch skipped → the first test falls over with the person in two households at once, which
is exactly the silent corruption; and the address overwrite in `_sync_address` skipped → the
second falls over with the old street still there.
"""
from datetime import date

import pytest

from app.domains.mdm.api import Member, MemberPerson, Person
from app.domains.mdm.import_service import upsert_families
from tests.conftest import seed_postal_code

pytestmark = pytest.mark.ui_agnostisch


def _row(lidnr, voornaam, naam, relatie, *, huisnummer="40", straat="milostraat"):
    return {
        "lidnr": lidnr, "voornaam": voornaam, "naam": naam,
        "straat": straat, "huisnummer": huisnummer, "busnummer": "",
        "postcode": "2400", "gemeente": "Mol",
        "email": None, "telefoon": None, "gsm": None,
        "geboortedatum": date(1980, 1, 1), "geslacht": None,
        "bestuurslid": None, "_relatie": relatie,
    }


def _load(db, families):
    return upsert_families(db, families, {}, [], apply=True)


def _households_of(db, person_id):
    return [mp.member_id for mp in db.query(MemberPerson)
            .filter(MemberPerson.person_id == person_id,
                    MemberPerson.deleted_at.is_(None)).all()]


def test_a_person_moving_house_leaves_the_old_household(db_session):
    """The branch that was never executed: an existing person turning up in another
    address group is moved, not copied.

    Copying is the silent version of this failure — no error, and the member counts of both
    households are wrong from then on.
    """
    seed_postal_code(db_session)
    _load(db_session, [
        [_row("1001", "Jan", "Peeters", "HOOFDLID", huisnummer="40")],
        [_row("1002", "Els", "Claes", "HOOFDLID", huisnummer="42")],
    ])
    db_session.flush()
    jan = db_session.query(Person).filter(Person.first_name == "Jan").one()
    oud_gezin = _households_of(db_session, jan.id)
    assert len(oud_gezin) == 1, "de opzet klopt niet — Jan zit niet in één gezin (#678)"

    # Jan duikt op in de adresgroep van Els: hetzelfde lidnummer, ander huisnummer.
    _load(db_session, [
        [_row("1002", "Els", "Claes", "HOOFDLID", huisnummer="42"),
         _row("1001", "Jan", "Peeters", "PARTNER", huisnummer="42")],
    ])
    db_session.flush()

    nieuw_gezin = _households_of(db_session, jan.id)
    assert len(nieuw_gezin) == 1, (
        f"Jan zit in {len(nieuw_gezin)} gezinnen tegelijk — verhuizen werd kopiëren, en "
        f"dat merkt niemand tot de ledenaantallen niet meer kloppen")
    assert nieuw_gezin != oud_gezin, "Jan is niet verhuisd"


def test_an_address_change_overwrites_the_old_one(db_session):
    """`_sync_address`, de tweede ongedekte tak: het rapport is bij het opladen de bron van
    waarheid, dus een gewijzigd adres hoort het oude te vervangen."""
    seed_postal_code(db_session)
    _load(db_session, [[_row("1003", "Mia", "Janssens", "HOOFDLID", straat="milostraat")]])
    db_session.flush()

    _load(db_session, [[_row("1003", "Mia", "Janssens", "HOOFDLID", straat="kerkstraat")]])
    db_session.flush()

    mia = db_session.query(Person).filter(Person.first_name == "Mia").one()
    assert mia.address is not None, "de opzet klopt niet — Mia heeft geen adres"
    assert mia.address.street == "kerkstraat", (
        f"het adres is niet bijgewerkt: {mia.address.street}")


def test_an_unchanged_row_changes_nothing(db_session):
    """De tegenproef die de twee hierboven bruikbaar maakt: zonder haar zou "altijd
    herschrijven" evengoed groen staan, en dan zet elke import een nieuwe audittrail voor
    gegevens die niet veranderd zijn."""
    from app.domains.mdm.api import AddressHistory

    seed_postal_code(db_session)
    _load(db_session, [[_row("1004", "Bo", "Willems", "HOOFDLID")]])
    db_session.flush()
    voor = db_session.query(AddressHistory).count()

    _load(db_session, [[_row("1004", "Bo", "Willems", "HOOFDLID")]])
    db_session.flush()

    assert db_session.query(AddressHistory).count() == voor, (
        "een ongewijzigde rij schreef toch geschiedenis")
