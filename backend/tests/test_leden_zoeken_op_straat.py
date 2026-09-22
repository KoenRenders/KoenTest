"""#1165: het zoekveld op /admin/leden vindt ook een straatnaam.

Alleen de straatnaam — Koen op 22 september 2026: *"Enkel straatnaam is
voldoende."* De zoekterm wordt dus niet opgesplitst: *"Kerkstraat"* vindt het
gezin, *"Kerkstraat 12"* hoeft niet te werken.

**De val is de reden dat dit issue bestaat.** `Address` is zacht verwijderbaar:
een verhuizing laat de oude rij staan met een `deleted_at` (vandaar de PARTIËLE
uniciteit op `person_id`, migratie 050). Zonder een filter in de join vind je een
gezin terug op de straat waar het vróéger woonde, en niets op het scherm
verklaart dat. `test_a_family_is_not_found_on_the_street_it_left` is daarom de
belangrijkste test van dit bestand: het gewone zoekgeval staat óók groen mét de
val erin.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.domains.mdm.api import (Address, ContactDetail, Member, MemberPerson,
                                 Organization, Person)
from app.domains.membership.household_service import list_families
from app.kernel.tenant_config import _actieve_tenant
from app.soft_delete import soft_delete
from tests.conftest import create_test_member, create_test_person, seed_postal_code

pytestmark = pytest.mark.ui_agnostisch

OUD = "Molenstraat"
NIEUW = "Kerkstraat"


@pytest.fixture
def postcode(db_session):
    return seed_postal_code(db_session)


def _gezin(db, postcode, *, voornaam="Tine", achternaam="Peeters",
           email="tine@example.com", straat=NIEUW):
    """Eén gezin met één persoon, een e-mailadres en een adres."""
    member = create_test_member(db)
    person = create_test_person(db, first_name=voornaam, last_name=achternaam,
                                date_of_birth=date(1985, 5, 5))
    db.add(MemberPerson(member_id=member.id, person_id=person.id,
                        relation_type="HOOFDLID"))
    db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL",
                         value=email, is_primary=True))
    db.add(Address(person_id=person.id, street=straat, house_number="12",
                   postal_code_id=postcode.id))
    db.flush()
    return member, person


def _zoek(db, term: str) -> set[int]:
    """De gezins-id's die het ledenscherm bij deze zoekterm toont.

    Via `list_families` en niet via een eigen query: dat is de functie die het
    scherm én `GET /families` aanroepen. Een test die de query nabouwt, blijft
    groen wanneer niemand hem nog aanroept.
    """
    antwoord = list_families(db, q=term)
    return {f.id for f in antwoord.items}


# ── 1. De uitbreiding zelf ──────────────────────────────────────────────────

def test_searching_on_a_street_finds_the_family_living_there(db_session, postcode):
    """Rood vóór de wijziging: zonder de nieuwe tak in de `OR` levert dit niets op.

    De tegenproef is gedraaid met `Address.street.ilike(like)` uit de `OR`
    gehaald — dan faalt deze test op een lege verzameling.
    """
    member, _p = _gezin(db_session, postcode)
    db_session.commit()

    assert member.id in _zoek(db_session, NIEUW)
    # En niet élk gezin komt terug: de zoekterm doet echt iets.
    ander, _q = _gezin(db_session, postcode, voornaam="Bram", achternaam="Claes",
                       email="bram@example.com", straat="Vaartkom")
    db_session.commit()
    treffers = _zoek(db_session, NIEUW)
    assert member.id in treffers and ander.id not in treffers


def test_the_house_number_is_deliberately_not_searchable(db_session, postcode):
    """Koens keuze, hier vastgepind zodat niemand hem later "afmaakt".

    De zoekterm wordt niet opgesplitst. Wie dat ooit wél wil, verandert gedrag
    dat bewust zo gekozen is — en dan hoort deze test rood te worden en niet
    stilletjes mee te bewegen.
    """
    member, _p = _gezin(db_session, postcode)
    db_session.commit()

    assert _zoek(db_session, f"{NIEUW} 12") == set(), (
        "de zoekterm hoort niet opgesplitst te worden; enkel de straatnaam telt")
    assert member.id in _zoek(db_session, NIEUW)


# ── 2. De val (de belangrijkste test van dit bestand) ───────────────────────

def test_a_family_is_not_found_on_the_street_it_left(db_session, postcode):
    """Een verhuisd gezin hoort niet op zijn oude straat te verschijnen.

    Een verhuizing WIST de oude adresrij niet, ze stempelt hem. Zonder
    `deleted_at IS NULL` in de ON-clausule vind je het gezin dus terug op een
    adres waar het niet meer woont, zonder dat iets op het scherm dat verklaart.

    **Wie dat regelt, is nagemeten en het was niet wat verwacht werd.** Het
    issue ging ervan uit dat de join een eigen `deleted_at IS NULL` nodig heeft.
    Dat is in deze codebase niet zo: de GLOBALE filter (`app/soft_delete.py`)
    bereikt ook een subquery binnen een `IN`. Afgelezen van de uitgevoerde SQL:

        LEFT OUTER JOIN mdm.addresses
          ON mdm.addresses.person_id = mdm.persons.id
         AND mdm.addresses.deleted_at IS NULL

    Een eigen filter in de join was dus een tweede plek voor hetzelfde feit —
    en de twee joins ernaast (persons, contact_details) leunen op precies
    dezelfde globale regel.

    **Deze test kan wél rood worden, en dat is los bewezen:** met de
    `with_loader_criteria` in `app/soft_delete.py` uitgeschakeld faalt hij met de
    melding hieronder, als enige van de negen. Hij bewaakt dus een echt gedrag en
    geen vanzelfsprekendheid — wat er ooit aan die globale filter verandert, of
    een `include_deleted` die iemand op deze query zet, komt hier naar boven.
    """
    member, person = _gezin(db_session, postcode, straat=OUD)
    db_session.commit()
    assert member.id in _zoek(db_session, OUD), (
        "opzet klopt niet: het gezin wordt niet eens op zijn eigen straat gevonden")

    # De verhuizing: oude rij stempelen, nieuwe rij erbij — precies wat de
    # partiële uniciteit op `person_id` (migratie 050) toelaat.
    oud_adres = (db_session.query(Address)
                 .filter(Address.person_id == person.id).one())
    soft_delete(oud_adres)
    db_session.add(Address(person_id=person.id, street=NIEUW, house_number="3",
                           postal_code_id=postcode.id))
    db_session.commit()

    assert member.id in _zoek(db_session, NIEUW), (
        "na de verhuizing hoort het gezin op zijn NIEUWE straat gevonden te worden")
    assert member.id not in _zoek(db_session, OUD), (
        "het gezin wordt teruggevonden op de straat waar het vertrokken is — "
        "de join filtert niet op deleted_at")


def test_an_address_of_an_organisation_is_no_family_hit(db_session, postcode):
    """Sinds #924/#945 kan een adres aan een ORGANISATIE hangen (XOR in de DB).

    De join op `person_id` houdt die rijen er vanzelf buiten. Tegenproef:
    de join verbreed tot alle adressen → deze test wordt rood.
    """
    member, _p = _gezin(db_session, postcode, straat=NIEUW)
    # De bestaande tenantorganisatie en geen verzonnen rij: die draagt een `code`
    # en een soort, en het gaat hier juist om een adres dat in de ECHTE vorm aan
    # een organisatie hangt.
    org = (db_session.query(Organization)
           .filter(Organization.id == _actieve_tenant(None))
           .execution_options(include_all_tenants=True).one())
    db_session.add(Address(organization_id=org.id, street="Zetelstraat",
                           house_number="1", postal_code_id=postcode.id))
    db_session.commit()

    assert _zoek(db_session, "Zetelstraat") == set(), (
        "een organisatieadres hoort geen gezinstreffer op te leveren")
    assert member.id in _zoek(db_session, NIEUW), (
        "en de gewone gezinstreffer moet blijven werken")


# ── 3. Wat vandaag gevonden wordt, blijft gevonden ─────────────────────────
#
# Eén test per tak van de `OR`. Samen in één test zou een herschrijving die
# stilzwijgend één kolom laat vallen nog altijd groen staan op de andere drie.

@pytest.mark.parametrize("term, tak", [
    ("Tine", "voornaam"),
    ("Peeters", "achternaam"),
    ("Tine Peeters", "volledige naam"),
    ("tine@example.com", "e-mail"),
])
def test_the_existing_branches_keep_working(db_session, postcode, term, tak):
    """Het is een `OR`, dus de uitbreiding kan alleen resultaten TOEVOEGEN.

    Geen enkele zoekopdracht die vandaag werkt mag stoppen met werken. De
    nieuwe `outerjoin` is het risico: een gewone join zou gezinnen zonder adres
    uit élke treffer gooien.
    """
    member, _p = _gezin(db_session, postcode)
    db_session.commit()

    assert member.id in _zoek(db_session, term), f"de tak {tak} vindt niets meer"


def test_a_family_without_an_address_is_still_found_by_name(db_session, postcode):
    """De reden dat het een OUTER join is, apart getoetst.

    Een gewone join zou elk gezin zonder adresrij uit de resultaten laten vallen
    — en dat is precies het soort regressie dat de takken hierboven niet zien,
    want die gezinnen hébben een adres.
    """
    member = create_test_member(db_session)
    person = create_test_person(db_session, first_name="Adresloos",
                                last_name="Janssens")
    db_session.add(MemberPerson(member_id=member.id, person_id=person.id,
                                relation_type="HOOFDLID"))
    db_session.commit()

    assert (db_session.query(Address)
            .filter(Address.person_id == person.id).count() == 0), "opzet klopt niet"
    assert member.id in _zoek(db_session, "Adresloos"), (
        "een gezin zonder adres verdwijnt uit de zoekresultaten — de join hoort "
        "een OUTER join te zijn")
