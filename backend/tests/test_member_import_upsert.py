"""Tests voor de upsert-import van het ledenrapport (#74).

De Excel is bij het opladen de bron van waarheid: bestaande gezinnen worden
bijgewerkt, onbekende lidnummers ingevoegd, en personen die niet meer in de
Excel-adresgroep staan worden uit het gezin verwijderd. Elke insert/update/delete
wordt geauditeerd met source="ledenadministratie".

De service muteert de sessie maar commit niet; we asserten binnen dezelfde sessie.
"""
from datetime import date

from app.services.member_import import upsert_families, LEGACY_SOURCE, IMPORT_YEAR
from app.models.member import Member, Person, MemberPerson, Membership
from app.models.contact import ContactDetail
from app.models.external_number import ExternalNumber
from app.models.history import (
    PersonHistory,
    MemberHistory,
    MemberPersonHistory,
    MembershipHistory,
)
from tests.conftest import seed_postal_code


def _row(lidnr, voornaam, naam, relatie, *, email=None, geboortedatum=None,
         geslacht=None, huisnummer="40", busnummer="", telefoon=None, gsm=None):
    """Eén Excel-rij zoals read_excel + group_families die aanleveren."""
    return {
        "lidnr": lidnr, "voornaam": voornaam, "naam": naam,
        "straat": "milostraat", "huisnummer": huisnummer, "busnummer": busnummer,
        "postcode": "2400", "gemeente": "Mol",
        "email": email, "telefoon": telefoon, "gsm": gsm,
        "geboortedatum": geboortedatum, "geslacht": geslacht,
        "bestuurslid": None, "_relatie": relatie,
    }


def _load(db, families, *, apply=True):
    """Bouw verse dicts per call (de service zet _person_id op de rijen)."""
    return upsert_families(db, families, {}, [], apply=apply)


def _household(db, member_id):
    return (
        db.query(MemberPerson)
        .filter(MemberPerson.member_id == member_id)
        .all()
    )


# ── Insert van een nieuw gezin ───────────────────────────────────────────────

def test_new_family_inserted_with_audit(db_session):
    seed_postal_code(db_session)
    fam = [
        _row("100", "Jan", "Janssens", "HOOFDLID", email="jan@example.com",
             geboortedatum=date(1980, 5, 1), geslacht="M"),
        _row("101", "An", "Janssens", "PARTNER", geboortedatum=date(1982, 3, 3),
             geslacht="F"),
    ]
    report = _load(db_session, [fam])

    assert report.new_families == 1
    assert report.persons_added == 2
    assert report.memberships_created == 1

    member = db_session.query(Member).one()
    assert len(_household(db_session, member.id)) == 2
    # Lidnummer als ExternalNumber bewaard.
    ext = db_session.query(ExternalNumber).filter_by(external_id="100").one()
    assert ext.source == LEGACY_SOURCE
    # Membership voor het importjaar.
    ms = db_session.query(Membership).filter_by(member_id=member.id).one()
    assert ms.year == IMPORT_YEAR
    # Audit: insert-snapshots met de juiste source.
    inserts = db_session.query(PersonHistory).filter_by(
        operation="insert", source=LEGACY_SOURCE).count()
    assert inserts == 2


# ── Update overschrijft bestaande velden ─────────────────────────────────────

def test_existing_member_fields_overwritten(db_session):
    seed_postal_code(db_session)
    _load(db_session, [[_row("100", "Jan", "Janssens", "HOOFDLID",
                             email="oud@example.com", geslacht="M")]])

    # Re-upload met gewijzigde voornaam + e-mail: de Excel wint.
    report = _load(db_session, [[_row("100", "Johan", "Janssens", "HOOFDLID",
                                     email="nieuw@example.com", geslacht="M")]])

    assert report.updated_families == 1
    assert report.persons_added == 0

    person = db_session.query(Person).join(ExternalNumber).filter(
        ExternalNumber.external_id == "100").one()
    assert person.first_name == "Johan"
    email = next(c for c in person.contact_details if c.contact_type_code == "EMAIL")
    assert email.value == "nieuw@example.com"
    # Audit: update-snapshot aangemaakt.
    assert db_session.query(PersonHistory).filter_by(
        operation="update", source=LEGACY_SOURCE).count() >= 1


# ── Onbekend lidnummer wordt toegevoegd aan het bestaande gezin ──────────────

def test_unknown_lidnr_added_to_household(db_session):
    seed_postal_code(db_session)
    _load(db_session, [[_row("100", "Jan", "Janssens", "HOOFDLID")]])
    member = db_session.query(Member).one()

    report = _load(db_session, [[
        _row("100", "Jan", "Janssens", "HOOFDLID"),
        _row("200", "Kind", "Janssens", "KIND"),   # nieuw lidnummer
    ]])

    assert report.persons_added == 1
    assert len(_household(db_session, member.id)) == 2
    assert db_session.query(ExternalNumber).filter_by(external_id="200").count() == 1


# ── Persoon afwezig in de Excel wordt uit het gezin verwijderd ───────────────

def test_person_absent_is_removed(db_session):
    seed_postal_code(db_session)
    _load(db_session, [[
        _row("100", "Jan", "Janssens", "HOOFDLID"),
        _row("101", "An", "Janssens", "PARTNER"),
    ]])
    member = db_session.query(Member).one()
    assert len(_household(db_session, member.id)) == 2

    # Re-upload zonder de partner: zij valt weg uit de adresgroep.
    report = _load(db_session, [[_row("100", "Jan", "Janssens", "HOOFDLID")]])

    assert report.persons_removed == 1
    remaining = _household(db_session, member.id)
    assert len(remaining) == 1
    assert remaining[0].person.first_name == "Jan"
    # Snapshot vóór de delete, zodat de wijzigingslijst (#82) haar nog ziet.
    assert db_session.query(MemberPersonHistory).filter_by(
        operation="delete", source=LEGACY_SOURCE).count() == 1


# ── Lidmaatschap wordt niet gedupliceerd bij een re-upload ───────────────────

def test_membership_not_duplicated(db_session):
    seed_postal_code(db_session)
    fam = lambda: [_row("100", "Jan", "Janssens", "HOOFDLID")]
    _load(db_session, [fam()])
    member = db_session.query(Member).one()

    report = _load(db_session, [fam()])

    assert report.memberships_created == 0
    assert db_session.query(Membership).filter_by(member_id=member.id).count() == 1


# ── Persoon verhuist naar een ander gezin ────────────────────────────────────

def test_person_moves_between_households(db_session):
    seed_postal_code(db_session)
    _load(db_session, [[
        _row("100", "Jan", "Janssens", "HOOFDLID"),
        _row("101", "An", "Janssens", "PARTNER"),
    ]])

    # Re-upload: 101 verhuist naar een nieuw gezin B (hoofdlid 200).
    _load(db_session, [
        [_row("100", "Jan", "Janssens", "HOOFDLID")],
        [_row("200", "Bob", "Bakker", "HOOFDLID", huisnummer="99"),
         _row("101", "An", "Janssens", "KIND", huisnummer="99")],
    ])

    # Persoon 101 is niet gedupliceerd en zit in precies één (nieuw) gezin.
    assert db_session.query(ExternalNumber).filter_by(external_id="101").count() == 1
    p101 = db_session.query(Person).join(ExternalNumber).filter(
        ExternalNumber.external_id == "101").one()
    assert len(p101.member_persons) == 1
    new_member_id = p101.member_persons[0].member_id
    p200 = db_session.query(Person).join(ExternalNumber).filter(
        ExternalNumber.external_id == "200").one()
    assert p200.member_persons[0].member_id == new_member_id


# ── Verweesde persoon wordt hergebruikt, niet gedupliceerd ───────────────────

def test_orphan_person_reused_not_duplicated(db_session):
    seed_postal_code(db_session)
    _load(db_session, [[
        _row("100", "Jan", "Janssens", "HOOFDLID"),
        _row("101", "An", "Janssens", "PARTNER"),
    ]])
    # 101 valt weg → verweesde persoon (Person + ExternalNumber blijven bestaan).
    _load(db_session, [[_row("100", "Jan", "Janssens", "HOOFDLID")]])

    # 101 duikt later op als hoofdlid van een nieuw gezin: hergebruik, geen
    # dubbele (source, external_id) — dat zou de unique-constraint schenden.
    _load(db_session, [[_row("101", "An", "Janssens", "HOOFDLID", huisnummer="50")]])

    assert db_session.query(ExternalNumber).filter_by(external_id="101").count() == 1
    p = db_session.query(Person).join(ExternalNumber).filter(
        ExternalNumber.external_id == "101").one()
    assert len(p.member_persons) == 1


# ── Dry-run wijzigt niets maar rapporteert wel ───────────────────────────────

def test_dry_run_makes_no_changes(db_session):
    seed_postal_code(db_session)
    _load(db_session, [[_row("100", "Jan", "Janssens", "HOOFDLID",
                             email="oud@example.com")]])

    persons_before = db_session.query(Person).count()
    history_before = db_session.query(PersonHistory).count()

    report = _load(db_session, [[
        _row("100", "Johan", "Janssens", "HOOFDLID", email="nieuw@example.com"),
        _row("200", "Kind", "Janssens", "KIND"),
    ]], apply=False)

    # Rapport ziet de wijzigingen ...
    assert report.persons_updated == 1
    assert report.persons_added == 1
    # ... maar er is niets weggeschreven.
    assert db_session.query(Person).count() == persons_before
    assert db_session.query(PersonHistory).count() == history_before
    person = db_session.query(Person).join(ExternalNumber).filter(
        ExternalNumber.external_id == "100").one()
    assert person.first_name == "Jan"  # ongewijzigd
