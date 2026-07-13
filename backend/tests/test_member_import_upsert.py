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
from app.models.member import Membership
from app.domains.mdm.api import Member, Person, MemberPerson
from app.domains.mdm.api import ContactDetail
from app.domains.mdm.api import ExternalNumber
from app.models.history import (
    MembershipHistory,
)
from app.domains.mdm.api import (
    PersonHistory,
    MemberHistory,
    MemberPersonHistory,
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
    # En leesbaar in de Wijzigingen-feed: "Lidnummer gekoppeld" (#229), niet enkel de naam.
    from app.services.member_changes import member_changes_since
    feed = member_changes_since(db_session, date(2000, 1, 1))
    assert any(r["entity"] == "Persoon" and r["summary"] == "Lidnummer gekoppeld" for r in feed)


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
    from app.domains.auth.api import User, UserRole
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


def test_commit_creates_admin_login_for_board_member_end_to_end(db_session):
    """End-to-end (#226): de volledige import (`upsert_families`, apply=True) met een
    gevulde bestuurslid-index maakt de admin-login aan — inclusief het propageren van
    `_person_id` naar de bestuurslid-rij en de gezin-koppeling — zonder crash."""
    from app.services.member_import import _norm
    from app.domains.auth.api import User, UserRole
    seed_postal_code(db_session)

    head = _row("100", "Mon", "Essers", "HOOFDLID", email="mon@example.com",
                geboortedatum=date(1980, 5, 1), geslacht="M")
    head["bestuurslid"] = "Mon Essers"            # dit gezin heeft een verantwoordelijk bestuurslid
    key = _norm("Mon Essers")
    # De bestuurslid-index verwijst naar dezelfde rij-objecten als de gezinnen,
    # zoals de parser ze aanlevert — zo erft de rij het _person_id na verwerking.
    report = upsert_families(db_session, [[head]], {key: [head]}, [key],
                             apply=True, actor="admin@raak.be")

    assert head["_person_id"] is not None                  # persoon aangemaakt + gepropageerd
    assert report.admins_created == 1

    user = db_session.query(User).filter(User.email == "mon@example.com").first()
    assert user is not None and user.is_active
    assert any(r.role_code == "ADMIN"
               for r in db_session.query(UserRole).filter(UserRole.user_id == user.id))

    # Het gezin is aan dat bestuurslid gekoppeld (board_member_id).
    member = db_session.query(Member).filter(
        Member.board_member_id == head["_person_id"]).first()
    assert member is not None

    # In de Wijzigingen-feed staat de bestuurslid-wijziging met de naam (#228),
    # niet enkel "Gezin".
    from app.services.member_changes import member_changes_since
    feed = member_changes_since(db_session, date(2000, 1, 1))
    assert any(r["entity"] == "Gezin" and r["summary"] == "Bestuurslid: Mon Essers"
               for r in feed)


def test_import_reverts_manually_changed_board_member(db_session):
    """De import zet het verantwoordelijke bestuurslid terug volgens het rapport,
    ook als het manueel gewijzigd was — en logt dat leesbaar (#228)."""
    from app.services.member_import import _norm
    from app.services.member_changes import member_changes_since
    seed_postal_code(db_session)
    member, hoofd, _mp, _en = _seed_imported(db_session, "100", "Mon", "Essers", date(1956, 5, 8))
    other = Person(first_name="Andere", last_name="Persoon",
                   date_of_birth=date(1990, 1, 1), gender_code="M")
    db_session.add(other)
    db_session.flush()
    member.board_member_id = other.id            # manueel "fout" gezet
    db_session.flush()

    head = _row("100", "Mon", "Essers", "HOOFDLID", geboortedatum=date(1956, 5, 8))
    head["bestuurslid"] = "Essers Mon"           # zoals kol 13 ("NAAM Voornaam")
    key = _norm("Essers Mon")
    upsert_families(db_session, [[head]], {key: [head]}, [key], apply=True)

    db_session.refresh(member)
    assert member.board_member_id == hoofd.id    # teruggezet naar het rapport
    feed = member_changes_since(db_session, date(2000, 1, 1))
    assert any(r["entity"] == "Gezin" and r["summary"] == "Bestuurslid: Mon Essers"
               for r in feed)


def test_person_field_change_shows_old_to_new(db_session):
    """#230: een persoonswijziging die de naam niet raakt (geboortedatum) toont
    'geb. oud → nieuw' in de Details — niet langer de ongewijzigde naam."""
    from app.services.member_changes import member_changes_since
    seed_postal_code(db_session)
    # Eerste import maakt de persoon (geb. 1980-05-01).
    upsert_families(db_session, [[
        _row("100", "Jan", "Janssens", "HOOFDLID", geboortedatum=date(1980, 5, 1)),
    ]], {}, [], apply=True)
    # Tweede import met een andere geboortedatum → persoonswijziging.
    upsert_families(db_session, [[
        _row("100", "Jan", "Janssens", "HOOFDLID", geboortedatum=date(1981, 6, 2)),
    ]], {}, [], apply=True)

    feed = member_changes_since(db_session, date(2000, 1, 1))
    persoon = [r for r in feed if r["entity"] == "Persoon"
               and "geb." in r["summary"] and "→" in r["summary"]]
    assert any("1980-05-01" in r["summary"] and "1981-06-02" in r["summary"]
               for r in persoon), persoon


# ── #227: soft-deleted persoon/gezin herleeft bij her-import ─────────────────────

def _seed_imported(db, lidnr, voornaam, naam, dob, *, relatie="HOOFDLID", member=None):
    """Een eerder geïmporteerd lid mét lidnummer (ExternalNumber)."""
    if member is None:
        member = Member()
        db.add(member)
        db.flush()
    person = Person(first_name=voornaam, last_name=naam, date_of_birth=dob, gender_code="M")
    db.add(person)
    db.flush()
    mp = MemberPerson(member_id=member.id, person_id=person.id, relation_type=relatie)
    en = ExternalNumber(person_id=person.id, source=LEGACY_SOURCE, external_id=lidnr)
    db.add_all([mp, en])
    db.flush()
    return member, person, mp, en


def test_soft_deleted_person_revived_on_reimport(db_session):
    """Scenario 2 (#227): een soft-deleted lid dat met hetzelfde lidnummer terugkomt,
    wordt hersteld (de-soft-deleted), niet gedupliceerd."""
    from app.soft_delete import soft_delete
    seed_postal_code(db_session)
    member, person, mp, en = _seed_imported(db_session, "100", "Jan", "Janssens", date(1980, 5, 1))
    pid = person.id
    for o in (person, mp, en):
        soft_delete(o)
    db_session.flush()

    report = upsert_families(db_session, [[
        _row("100", "Jan", "Janssens", "HOOFDLID", geboortedatum=date(1980, 5, 1)),
    ]], {}, [], apply=True)

    assert report.persons_revived == 1
    assert report.persons_added == 0
    persons = (db_session.query(Person).execution_options(include_deleted=True)
               .filter(Person.first_name == "Jan", Person.last_name == "Janssens").all())
    assert len(persons) == 1                                # geen duplicaat
    assert persons[0].id == pid and persons[0].deleted_at is None   # hersteld

    # In de Wijzigingen-feed staat de heractivering leesbaar in Details (#227).
    from app.services.member_changes import member_changes_since
    feed = member_changes_since(db_session, date(2000, 1, 1))
    assert any(r["entity"] == "Persoon" and r["summary"] == "Heractivering" for r in feed)


def test_soft_deleted_family_revived_on_reimport(db_session):
    """Scenario 3 (#227): een volledig soft-deleted gezin dat integraal terugkomt via
    het rapport wordt hersteld, niet als nieuw gezin gedupliceerd."""
    from app.soft_delete import soft_delete
    seed_postal_code(db_session)
    member, hoofd, mp1, en1 = _seed_imported(db_session, "200", "Mon", "Essers", date(1956, 5, 8))
    _m, kind, mp2, en2 = _seed_imported(db_session, "201", "Tom", "Essers", date(2010, 1, 1),
                                        relatie="KIND", member=member)
    mid = member.id
    for o in (member, mp1, mp2, en1, en2, hoofd, kind):
        soft_delete(o)
    db_session.flush()

    report = upsert_families(db_session, [[
        _row("200", "Mon", "Essers", "HOOFDLID", geboortedatum=date(1956, 5, 8)),
        _row("201", "Tom", "Essers", "KIND", geboortedatum=date(2010, 1, 1)),
    ]], {}, [], apply=True)

    assert report.persons_revived == 2
    # Geen duplicaat-gezin: het oorspronkelijke gezin is hersteld.
    active = [m for m in db_session.query(Member).execution_options(include_deleted=True).all()
              if m.deleted_at is None]
    assert len(active) == 1 and active[0].id == mid

    # De gezin-heractivering staat als eigen, leesbare rij in de feed (#227).
    from app.services.member_changes import member_changes_since
    feed = member_changes_since(db_session, date(2000, 1, 1))
    assert any(r["entity"] == "Gezin" and r["summary"] == "Heractivering gezin" for r in feed)


def test_absent_family_left_untouched(db_session):
    """Een gezin dat niet in het rapport staat, wordt niet aangeraakt: de import wist
    enkel personen bínnen aanwezige gezinnen, nooit een volledig afwezig gezin (#179)."""
    seed_postal_code(db_session)
    _member, person = _seed_selfreg(db_session, "Wim", "Weg", date(1970, 1, 1))
    pid = person.id

    report = upsert_families(db_session, [[
        _row("300", "Ander", "Lid", "HOOFDLID", geboortedatum=date(1990, 1, 1)),
    ]], {}, [], apply=True)

    assert report.persons_removed == 0
    persoon = db_session.query(Person).filter(Person.id == pid).first()
    assert persoon is not None and persoon.deleted_at is None         # ongemoeid
    assert db_session.query(MemberPerson).filter(MemberPerson.person_id == pid).first() is not None
