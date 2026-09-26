"""#1174 — de nieuwsbrief gaat naar ELK adres van een lid, een tonen-scherm naar het hoofdadres.

Koen, 26 september 2026: *"nieuwsbrief moet naar beiden"*. Je weet niet welke
mailbox iemand leest, en de extra adressen zijn juist verzameld omdat het portaal
ze niet kende. Dat is het omgekeerde van een bevestiging, die naar het ene adres
gaat dat op haar formulier stond.

`email_addresses_of_members` beloofde dat al in zijn docstring — *"every e-mail
address of every person"* — maar riep `_email_of` aan, en die geeft er één terug.
Met één adres per persoon kon niemand het verschil zien. Dat is precies het soort
belofte dat pas onwaar wordt wanneer de wereld verandert, en dan merkt niemand
het, want er staat geen test op het verschil.
"""
from __future__ import annotations

import pytest

from app.domains.mdm.api import ContactDetail
from app.domains.mdm.service import _email_of, email_addresses_of_members
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_agnostisch

HOOFD = "hoofd@example.com"
TWEEDE = "tweede@example.com"
DERDE = "derde@example.com"


def _extra(db, person, waarde, *, primair=False):
    db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL",
                         value=waarde, is_primary=primair))
    db.flush()


# ── De nieuwsbrief: alles ───────────────────────────────────────────────────

def test_de_nieuwsbrief_gaat_naar_elk_adres_van_het_lid(db_session):
    """Het gemelde geval.

    Tegenproef: `email_addresses_of_members` weer op `_email_of` laten draaien →
    alleen het hoofdadres komt terug en deze test faalt op het ontbrekende
    tweede adres.
    """
    member, person = create_test_family(db_session, email=HOOFD)
    _extra(db_session, person, TWEEDE)
    db_session.commit()

    assert email_addresses_of_members(db_session, [member.id]) == [HOOFD, TWEEDE], (
        "de nieuwsbrief hoort naar beide adressen te gaan")


def test_een_gedeelde_mailbox_krijgt_de_brief_een_keer(db_session):
    """Ontdubbelen, en het is niet theoretisch.

    Op PROD staan twaalf adressen bij méér dan één persoon, allemaal binnen
    hetzelfde gezin — een gedeelde mailbox van een koppel. Zonder de verzameling
    valt die brief daar twee keer binnen, en dat heeft niets met een tweede adres
    te maken.

    Hoofdletterongevoelig, want een mens typt zijn eigen adres niet twee keer
    identiek.
    """
    member, person = create_test_family(db_session, email=HOOFD)
    from app.domains.mdm.api import MemberPerson
    from tests.conftest import create_test_person

    partner = create_test_person(db_session, first_name="Partner")
    db_session.add(MemberPerson(member_id=member.id, person_id=partner.id,
                                relation_type="PARTNER"))
    db_session.flush()
    _extra(db_session, partner, HOOFD.upper(), primair=True)
    db_session.commit()

    assert email_addresses_of_members(db_session, [member.id]) == [HOOFD], (
        "een gedeelde mailbox hoort één keer in de verzendlijst te staan")


def test_de_lijst_is_twee_keer_dezelfde_lijst(db_session):
    """Gesorteerd, zodat twee opvragingen hetzelfde opleveren.

    Zonder deze eigenschap is een verzendlijst niet te vergelijken en kan je een
    verschil tussen twee runs niet van een echte wijziging onderscheiden.
    """
    member, person = create_test_family(db_session, email=DERDE)
    _extra(db_session, person, HOOFD)
    _extra(db_session, person, TWEEDE)
    db_session.commit()

    eerste = email_addresses_of_members(db_session, [member.id])
    assert eerste == sorted(eerste) == email_addresses_of_members(db_session, [member.id])


# ── Eén adres tonen: het hoofdadres ────────────────────────────────────────

def test_een_scherm_toont_het_hoofdadres(db_session):
    """`_email_of` voedt schermen die ÉÉN adres tonen — de vergaderkring, `member_me`.

    "De eerste rij" is daar een willekeurige keuze: de relatie belooft geen
    volgorde, dus hetzelfde scherm kan bij twee bezoeken een ander adres tonen.

    **Het extra adres staat hier met opzet VOORAAN**, en dat is de hele test. Zet
    je het hoofdadres eerst — de volgorde waarin het meestal ontstaat — dan geeft
    "de eerste rij" toevallig het juiste antwoord en bewijst de test niets. Dat
    was mijn eerste opzet, en de tegenproef bleef er groen op.

    Tegenproef met deze volgorde: de `is_primary`-voorkeur eruit → `_email_of`
    geeft het tweede adres terug en de test faalt daarop.
    """
    _member, person = create_test_family(db_session, email=HOOFD)
    # Weg met het adres uit de fixture; opnieuw opbouwen in de gevaarlijke volgorde.
    for c in list(person.contact_details):
        if c.contact_type_code == "EMAIL":
            person.contact_details.remove(c)
    db_session.flush()
    _extra(db_session, person, TWEEDE)              # laagste id, niet primair
    _extra(db_session, person, HOOFD, primair=True)  # hoogste id, wél primair
    db_session.commit()
    db_session.expire_all()
    db_session.refresh(person)

    volgorde = [c.value for c in person.contact_details
                if c.contact_type_code == "EMAIL"]
    assert volgorde[:1] == [TWEEDE], (
        f"opzet klopt niet: het extra adres hoort vooraan te staan, gekregen "
        f"{volgorde} — zonder die volgorde toetst deze test de fout niet")

    assert _email_of(person) == HOOFD


def test_zonder_hoofdadres_toont_het_scherm_toch_iets(db_session):
    """De databank waarborgt HOOGSTENS één hoofdadres, niet minstens één.

    Een persoon van wie het hoofdadres weggehaald is, heeft nog altijd een naam
    om iets naast te zetten; leeg renderen zou erger zijn dan het overgebleven
    adres tonen.
    """
    _member, person = create_test_family(db_session, email=HOOFD)
    for c in list(person.contact_details):
        if c.contact_type_code == "EMAIL":
            person.contact_details.remove(c)
    _extra(db_session, person, TWEEDE)
    db_session.commit()
    db_session.refresh(person)

    assert _email_of(person) == TWEEDE


def test_zonder_enig_adres_is_het_none(db_session):
    """En de ontaarde stand, zodat de twee tests hierboven niet vacuüm slagen."""
    _member, person = create_test_family(db_session, email=HOOFD)
    for c in list(person.contact_details):
        if c.contact_type_code == "EMAIL":
            person.contact_details.remove(c)
    db_session.commit()
    db_session.refresh(person)

    assert _email_of(person) is None
