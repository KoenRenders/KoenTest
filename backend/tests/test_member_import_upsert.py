"""Tests voor de upsert-import van het ledenrapport (#74, #192, #214).

Het ledenrapport is bij het opladen de bron van waarheid: bestaande gezinnen
worden bijgewerkt, onbekende lidnummers ingevoegd, en personen die niet meer in
de adresgroep van het rapport staan worden uit het gezin verwijderd. Een onbekend
lidnummer dat op identiteit (naam+geboortedatum) een bestaand lidnummer-loos lid
matcht, krijgt dat lidnummer gehecht i.p.v. een duplicaat (#192). Elke
insert/update/delete wordt geauditeerd met source="ledenadministratie" en een
optionele actor (#214).

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
    """Eén rij zoals read_ledenrapport + group_families die aanleveren."""
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

    # Re-upload met gewijzigde voornaam + e-mail: het rapport wint.
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


# ── Persoon afwezig in het rapport wordt uit het gezin verwijderd ────────────

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


# ── #192: identiteitsmatch van een lidnummer-loos bestaand lid ───────────────

def _seed_selfreg(db, voornaam, naam, dob, *, geslacht="M", huisnummer="40"):
    """Een zelf-geregistreerd lid: Person + gezin, maar GEEN lidnummer."""
    member = Member()
    db.add(member)
    db.flush()
    person = Person(first_name=voornaam, last_name=naam, date_of_birth=dob,
                    gender_code=geslacht)
    db.add(person)
    db.flush()
    db.add(MemberPerson(member_id=member.id, person_id=person.id,
                        relation_type="HOOFDLID"))
    db.flush()
    return member, person


def test_identity_match_attaches_lidnr_no_duplicate(db_session):
    seed_postal_code(db_session)
    member, person = _seed_selfreg(db_session, "Jan", "Janssens", date(1980, 5, 1))
    members_before = db_session.query(Member).count()

    report = _load(db_session, [[
        _row("100", "Jan", "Janssens", "HOOFDLID",
             geboortedatum=date(1980, 5, 1), geslacht="M"),
    ]])

    # Geen nieuwe persoon, geen nieuw gezin.
    assert report.persons_added == 0
    assert db_session.query(Person).count() == 1
    assert db_session.query(Member).count() == members_before
    # Lidnummer gehecht aan het bestaande lid.
    ext = db_session.query(ExternalNumber).filter_by(external_id="100").one()
    assert ext.person_id == person.id
    # Bestaand gezin hergebruikt.
    assert _household(db_session, member.id)[0].person_id == person.id
    # Audit: lidnr_attached-snapshot.
    assert db_session.query(PersonHistory).filter_by(
        action="lidnr_attached", source=LEGACY_SOURCE).count() == 1


def test_identity_ambiguous_not_linked(db_session):
    seed_postal_code(db_session)
    # Twee lidnummer-loze personen met identieke naam + geboortedatum.
    _seed_selfreg(db_session, "Jan", "Janssens", date(1980, 5, 1), huisnummer="40")
    _seed_selfreg(db_session, "Jan", "Janssens", date(1980, 5, 1), huisnummer="42")

    report = _load(db_session, [[
        _row("100", "Jan", "Janssens", "HOOFDLID",
             geboortedatum=date(1980, 5, 1), geslacht="M"),
    ]])

    # Ambigu → niet automatisch gekoppeld, als nieuw behandeld.
    assert report.persons_added == 1
    assert db_session.query(ExternalNumber).filter_by(external_id="100").count() == 1
    assert any("meerdere bestaande leden" in w for w in report.warnings)


def test_identity_match_requires_birthdate(db_session):
    seed_postal_code(db_session)
    # Bestaand lid zonder geboortedatum → komt niet in de identiteitsindex.
    _seed_selfreg(db_session, "Jan", "Janssens", None)

    report = _load(db_session, [[
        _row("100", "Jan", "Janssens", "HOOFDLID", geboortedatum=date(1980, 5, 1)),
    ]])

    # Geen match op naam alleen → nieuw lid aangemaakt.
    assert report.persons_added == 1


def test_identity_match_dry_run_no_changes_or_removal(db_session):
    seed_postal_code(db_session)
    _seed_selfreg(db_session, "Jan", "Janssens", date(1980, 5, 1))

    report = _load(db_session, [[
        _row("100", "Jan", "Janssens", "HOOFDLID",
             geboortedatum=date(1980, 5, 1), geslacht="M"),
    ]], apply=False)

    # Match herkend zonder duplicaat, en het bestaande lid wordt NIET als
    # 'verwijderd' gerapporteerd (processed_person_ids dekt de dry-run).
    assert report.persons_added == 0
    assert report.persons_removed == 0
    assert db_session.query(ExternalNumber).count() == 0   # niets weggeschreven


# ── #214: actor in de audit ──────────────────────────────────────────────────

def test_actor_recorded_in_history(db_session):
    seed_postal_code(db_session)
    upsert_families(
        db_session,
        [[_row("100", "Jan", "Janssens", "HOOFDLID",
               geboortedatum=date(1980, 5, 1), geslacht="M")]],
        {}, [], apply=True, actor="admin@raak.be",
    )
    rows = db_session.query(PersonHistory).filter_by(source=LEGACY_SOURCE).all()
    assert rows
    assert all(r.actor == "admin@raak.be" for r in rows)


def test_actor_defaults_to_none(db_session):
    seed_postal_code(db_session)
    _load(db_session, [[_row("100", "Jan", "Janssens", "HOOFDLID")]])
    rows = db_session.query(MemberHistory).filter_by(source=LEGACY_SOURCE).all()
    assert rows
    assert all(r.actor is None for r in rows)


# ── #226: admin-login voor bestuurslid mag het commit-pad niet doen crashen ──────

def test_admin_user_created_for_board_member(db_session):
    """Een bestuurslid met e-mail krijgt bij commit een admin-login. User heeft géén
    person_id-kolom (User↔Person koppelt via e-mail); het apply-pad mag dus niet
    crashen op een person_id-kwarg (#226 — droogloop OK maar 'Definitief importeren' 500)."""
    from app.services.member_import import _create_admin_users, ImportReport
    from app.models.user import User, UserRole
    from tests.conftest import create_test_person

    person = create_test_person(db_session, first_name="Mon", last_name="Essers")
    row = {"lidnr": "100", "voornaam": "Mon", "naam": "Essers",
           "email": "mon@example.com", "_person_id": person.id}
    report = ImportReport()
    _create_admin_users(db_session, ["mon essers"], {"mon essers": [row]},
                        apply=True, report=report)

    user = db_session.query(User).filter(User.email == "mon@example.com").first()
    assert user is not None and user.is_active
    roles = db_session.query(UserRole).filter(UserRole.user_id == user.id).all()
    assert any(r.role_code == "ADMIN" for r in roles)
