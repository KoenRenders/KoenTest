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

import re
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


# ── 4. De zoeksuggestie belooft precies wat het veld doet (#1167) ───────────
#
# Deze twee tests staan bewust in DIT bestand en niet bij de schermtests: de
# grijze suggestie is een belofte over de `OR` hierboven. Zet je ze uit elkaar,
# dan verandert ooit die `OR` en blijft de copy stil achter — en dat is precies
# wat #1167 kwam repareren nadat #1165 de straatnaam toevoegde.

PLACEHOLDER = re.compile(r"placeholder=_\('([^']+)'\)")

# Per begrip uit de suggestie: een waarde die ALLEEN via die tak te vinden is.
# Bewust geen overlap tussen de drie — zou het e-mailadres de achternaam
# bevatten, dan slaagde "e-mail" via de naamtak en bewees hij niets.
BEGRIPPEN = {
    "naam": "Vandevelde",
    "straatnaam": "Populierendreef",
    "e-mail": "penningmeester@example.com",
}


def _suggestie() -> str:
    """De grijze tekst in het zoekveld van /admin/leden, uit het sjabloon."""
    from pathlib import Path

    pad = (Path(__file__).resolve().parents[1] / "app" / "domains" / "mdm"
           / "templates" / "leden.html")
    treffers = PLACEHOLDER.findall(pad.read_text())
    assert len(treffers) == 1, (
        f"één zoeksuggestie verwacht in leden.html, {len(treffers)} gevonden: "
        f"{treffers} — de test leest het verkeerde veld of er staan er nu twee")
    return treffers[0]


def _begrippen_uit(suggestie: str) -> set[str]:
    """De opgesomde velden uit *Zoek op A, B of C…* als losse begrippen."""
    kern = suggestie.removeprefix("Zoek op ").removesuffix("…").strip()
    delen = [d.strip() for stuk in kern.split(",") for d in stuk.split(" of ")]
    return {d for d in delen if d}


def test_the_search_hint_names_exactly_the_fields_that_are_searched(
        db_session, postcode):
    """Het punt van #1167: de suggestie mag niets beloven wat niet meezoekt.

    De koppeling loopt langs BEGRIPPEN, en die set moet gelijk zijn aan wat er
    in de suggestie staat. Daardoor breekt deze test in twee richtingen:

    - iemand zet er een veld bij dat niet doorzocht wordt → het begrip zit niet
      in BEGRIPPEN en de gelijkheid faalt;
    - iemand voegt een tak aan de `OR` toe en noemt ze in de copy → idem, tot
      hij hier een waarde bijzet die bewijst dát ze te vinden is.

    Een test die alleen de string vergelijkt zou geen van beide zien. Rood
    bewezen: *"straatnaam"* uit de suggestie gehaald → faalt op het verschil;
    en *"telefoon"* erbij gezet → faalt óók, met dat woord in de melding.
    """
    from app.domains.membership.household_service import SEARCHED_FIELDS

    # #1169: de BRON eerst. Beide beloftes hangen hieraan — de API-omschrijving
    # leidt eruit af, de schermsuggestie wordt ertegen getoetst.
    assert set(SEARCHED_FIELDS) == set(BEGRIPPEN), (
        f"SEARCHED_FIELDS zegt {sorted(SEARCHED_FIELDS)} en bewezen doorzoekbaar "
        f"is {sorted(BEGRIPPEN)}; zet er een probeerwaarde bij die het bewijst, "
        "of haal het veld uit de bron")

    genoemd = _begrippen_uit(_suggestie())
    assert genoemd == set(BEGRIPPEN), (
        f"de suggestie noemt {sorted(genoemd)} en de bewezen velden zijn "
        f"{sorted(BEGRIPPEN)}; een suggestie die meer belooft dan het veld doet "
        "is erger dan een verouderde")

    member, _p = _gezin(db_session, postcode, voornaam="Miet",
                        achternaam="Vandevelde",
                        email="penningmeester@example.com",
                        straat="Populierendreef")
    db_session.commit()

    for begrip, waarde in BEGRIPPEN.items():
        assert member.id in _zoek(db_session, waarde), (
            f"de suggestie noemt {begrip!r}, maar zoeken op {waarde!r} vindt "
            "het gezin niet")


def test_the_members_screen_carries_the_hint(client, db_session):
    """En de tekst staat ook echt op het scherm, niet alleen in het sjabloon."""
    from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                      make_session_value)
    from tests.conftest import SEEDED_ADMIN_EMAIL

    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    csrf_token_for(waarde)

    html = client.get("/admin/leden").text
    assert _suggestie() in html, "de zoeksuggestie staat niet op /admin/leden"



def test_the_api_description_makes_the_same_promise(db_session, postcode):
    """#1169: `GET /families` roept dezelfde `list_families` aan, dus belooft ze
    hetzelfde — en ze doet dat door af te leiden, niet door over te typen.

    De omschrijving beloofde *"naam of e-mail"* terwijl #1165 de straat aan de
    `OR` had toegevoegd. Twee plaatsen voor één feit, en de tweede verouderde
    stil omdat niets haar aan de eerste bond.

    Nu komt ze uit `SEARCHED_FIELDS`. Deze test kijkt daarom niet of de woorden
    er staan — dat kan met een afleiding haast niet misgaan — maar of de
    GERENDERDE omschrijving in het OpenAPI-schema precies de bewezen velden
    noemt. Dat vangt ook een rendering die de lijst stilletjes afkapt.

    Rood bewezen: `family_search_hint()` teruggezet op een vaste string
    *"naam of e-mail"* → deze test faalt op het ontbrekende `straatnaam`.
    """
    from app.main import app

    schema = app.openapi()
    parameters = schema["paths"]["/api/v1/families"]["get"]["parameters"]
    q = next(p for p in parameters if p["name"] == "q")
    omschrijving = q["description"]

    kern = omschrijving.removeprefix("Zoek op ").removesuffix(
        " van een gezinslid").strip()
    genoemd = {d.strip() for stuk in kern.split(",") for d in stuk.split(" of ")}
    assert genoemd == set(BEGRIPPEN), (
        f"de API-omschrijving noemt {sorted(genoemd)} en de bewezen velden zijn "
        f"{sorted(BEGRIPPEN)}; volledige tekst: {omschrijving!r}")


def test_the_screen_and_the_api_promise_the_same_fields():
    """De twee beloftes staan op twee plaatsen; deze poort houdt ze gelijk.

    Eén van beide kón niet afgeleid worden: de schermsuggestie moet als één
    letterlijke string in een `_()`-aanroep staan, anders haalt pybabel er geen
    msgid meer uit en is ze niet vertaalbaar. Dat is de reden dat hier een poort
    staat en geen tweede afleiding — `CLAUDE.md` noemt een poort terecht de
    duurdere oplossing, dus hoort de reden erbij te staan.

    Rood bewezen: één woord uit de schermsuggestie gehaald → faalt met het
    verschil tussen de twee verzamelingen.
    """
    from app.domains.membership.household_service import (SEARCHED_FIELDS,
                                                          family_search_hint)

    assert _begrippen_uit(_suggestie()) == set(SEARCHED_FIELDS), (
        "de zoeksuggestie op het scherm en de API beloven niet dezelfde velden")
    # En de opsomming zelf: komma's, "of" vóór het laatste, geen afsluitende komma.
    assert family_search_hint() == "naam, straatnaam of e-mail"
