"""#1174 — de ledenimport raakt een EXTRA e-mailadres niet aan.

Een lid mag sinds dit issue meerdere e-mailadressen hebben: één hoofdadres —
het adres dat Raak Nationaal in zijn programma heeft, en daar kan er maar één
van zijn — en daarnaast adressen die wij verzameld hebben om iemand te kunnen
herkennen bij het aanmelden.

**`_upsert_contact` zocht "de eerste rij van dat type".** Dat is stil verkeerd
zodra er meer dan één rij is, en die functie draait bij élke ledenimport:

- is die eerste rij toevallig een extra adres, dan overschrijft het rapport het
  met de nationale waarde en blijft het hoofdadres er ongewijzigd naast staan;
- draagt het rapport géén adres voor dat lid, dan **verwijdert** de import die
  eerste rij — mogelijk een van de adressen die net verzameld zijn.

Zonder deze tests verdwijnen die adressen bij de eerstvolgende import en vertelt
niets op het scherm dat het gebeurd is. `test_de_import_verwijdert_geen_extra_adres`
is de belangrijkste van dit bestand.
"""
from datetime import date

import pytest

from app.domains.mdm.api import ContactDetail, Person
from app.domains.mdm.import_service import upsert_families
from tests.conftest import seed_postal_code

pytestmark = pytest.mark.ui_agnostisch

HOOFD = "hoofd@example.com"
EXTRA = "extra@example.com"
NIEUW = "nieuw@example.com"


def _row(lidnr, voornaam, naam, relatie, *, email=None):
    return {
        "lidnr": lidnr, "voornaam": voornaam, "naam": naam,
        "straat": "milostraat", "huisnummer": "40", "busnummer": "",
        "postcode": "2400", "gemeente": "Mol",
        "email": email, "telefoon": None, "gsm": None,
        "geboortedatum": date(1980, 1, 1), "geslacht": "M",
        "bestuurslid": None, "_relatie": relatie,
    }


def _import(db, rij):
    return upsert_families(db, [[rij]], {}, [], apply=True)


def _adressen(db, persoon) -> dict[str, bool]:
    """Elk e-mailadres van deze persoon → is het het hoofdadres?"""
    db.refresh(persoon)
    return {c.value: bool(c.is_primary) for c in persoon.contact_details
            if c.contact_type_code == "EMAIL"}


@pytest.fixture
def lid_met_twee_adressen(db_session):
    """Een lid waarbij het EXTRA adres als eerste rij staat en het hoofdadres erna.

    **Die volgorde is de hele opzet.** De bug is "neem de eerste rij van dit
    type", en die bijt alleen wanneer de eerste rij niet het hoofdadres is. Zet je
    het extra adres ná de import erbij — de volgorde waarin het in het echt
    meestal ontstaat — dan staat het hoofdadres vooraan en slaagt de oude code
    óók. Dat was mijn eerste opzet, en de tegenproef bleef er groen op: vijf
    tests die niets bewezen.

    Beide rijen worden hier RECHTSTREEKS gezet en niet via een import. Anders
    loopt de opzet zelf door de code die getoetst wordt, en dan faalt bij een
    tegenproef de fixture in plaats van de test — met "opzet klopt niet" als
    melding, waar de bevinding hoort te staan.

    De assertie op de volgorde blijft: haalt de databank ze ooit anders terug, dan
    faalt de opzet luid in plaats van de tests stilletjes waardeloos te maken.
    """
    seed_postal_code(db_session)
    _import(db_session, _row("L-1", "Tine", "Peeters", "HOOFDLID", email=None))
    persoon = db_session.query(Person).filter(Person.first_name == "Tine").one()
    # Eerst het extra adres (laagste id), dán het hoofdadres.
    db_session.add(ContactDetail(person_id=persoon.id, contact_type_code="EMAIL",
                                 value=EXTRA, is_primary=False))
    db_session.flush()
    db_session.add(ContactDetail(person_id=persoon.id, contact_type_code="EMAIL",
                                 value=HOOFD, is_primary=True))
    db_session.commit()
    db_session.expire_all()

    persoon = db_session.query(Person).filter(Person.first_name == "Tine").one()
    volgorde = [c.value for c in persoon.contact_details
                if c.contact_type_code == "EMAIL"]
    assert volgorde[:1] == [EXTRA], (
        f"opzet klopt niet: het extra adres hoort vooraan te staan, gekregen "
        f"{volgorde} — zonder die volgorde toetst dit bestand de bug niet")
    return persoon


# ── De belangrijkste: een leeg rapportveld wist het extra adres niet ────────

def test_de_import_verwijdert_geen_extra_adres(db_session, lid_met_twee_adressen):
    """Het rapport draagt geen e-mailadres. Vroeger verdween dan "de eerste rij".

    Wat er wél gebeurt: het hoofdadres gaat weg — dat is de bestaande regel, het
    rapport is er de bron van — en het extra adres blijft staan, **zonder** dat
    het hoofdadres wordt.

    Dat laatste is Koens beslissing van 27 september 2026. Het hoofdadres is een
    HERKOMST — *"dit is het adres dat Raak Nationaal in zijn programma heeft"* —
    en zelf een ander aanwijzen omdat er toevallig een rij overblijft, verzint
    die herkomst. Nul hoofdadressen is een geldige toestand. Ik had hier eerst
    het oudste laten promoveren; dat is eruit, en mijn argument ervoor vervalt
    omdat geen enkele verzending nog aan het hoofdadres hangt.

    Tegenproef: `_upsert_contact` weer op "de eerste rij" laten zoeken → het extra
    adres is dan weg en deze test faalt met alleen `{}` of alleen het hoofdadres.
    """
    _import(db_session, _row("L-1", "Tine", "Peeters", "HOOFDLID", email=None))

    na = _adressen(db_session, lid_met_twee_adressen)
    assert EXTRA in na, (
        f"het extra adres is verdwenen bij een import zonder e-mailadres: {na}")
    assert na == {EXTRA: False}, (
        f"verwacht: het extra adres blijft staan en wordt GEEN hoofdadres; "
        f"gekregen: {na}")


def test_de_import_werkt_het_hoofdadres_bij_en_laat_het_extra_staan(
        db_session, lid_met_twee_adressen):
    """Het rapport draagt een gewijzigd adres: alleen het hoofdadres volgt.

    Tegenproef: op "de eerste rij" zoeken → afhankelijk van de rijvolgorde
    overschrijft het rapport het EXTRA adres, en dan staat `NIEUW` waar `EXTRA`
    hoorde te staan.
    """
    _import(db_session, _row("L-1", "Tine", "Peeters", "HOOFDLID", email=NIEUW))

    na = _adressen(db_session, lid_met_twee_adressen)
    assert na == {NIEUW: True, EXTRA: False}, (
        f"het hoofdadres hoort te volgen en het extra ongemoeid te blijven: {na}")


def test_een_onveranderd_rapport_laat_alles_staan(db_session, lid_met_twee_adressen):
    """De gewone dagelijkse import: er verandert niets.

    Zonder deze test zou een reparatie die élke import het extra adres laat
    opruimen, groen blijven op de twee tests hierboven — die kijken allebei naar
    een rapport dat iets zegt over het e-mailadres.
    """
    _import(db_session, _row("L-1", "Tine", "Peeters", "HOOFDLID", email=HOOFD))

    assert _adressen(db_session, lid_met_twee_adressen) == {HOOFD: True, EXTRA: False}


# ── Het hoofdadres blijft enkelvoudig ──────────────────────────────────────

def test_het_rapportadres_promoveert_een_bestaand_extra_adres(db_session):
    """Staat het nationale adres al als extra rij, dan wordt die het hoofdadres.

    Anders zou dezelfde waarde twee keer bij één persoon staan — één primair en
    één niet — en mag iemand dat later met de hand opruimen.
    """
    seed_postal_code(db_session)
    _import(db_session, _row("L-2", "Bram", "Claes", "HOOFDLID", email=HOOFD))
    persoon = db_session.query(Person).filter(Person.first_name == "Bram").one()

    # Haal het hoofdadres weg en laat alleen een extra rij met dezelfde waarde staan.
    for c in list(persoon.contact_details):
        if c.contact_type_code == "EMAIL":
            persoon.contact_details.remove(c)
    db_session.add(ContactDetail(person_id=persoon.id, contact_type_code="EMAIL",
                                 value=HOOFD, is_primary=False))
    db_session.commit()

    _import(db_session, _row("L-2", "Bram", "Claes", "HOOFDLID", email=HOOFD))

    na = _adressen(db_session, persoon)
    assert na == {HOOFD: True}, f"één rij verwacht, als hoofdadres; gekregen: {na}"


def test_er_blijft_hoogstens_een_hoofdadres(db_session, lid_met_twee_adressen):
    """De databankregel die dit al bewaakt, hier als gedrag vastgelegd.

    `uq_contact_details_one_primary_per_type` (migratie 053, partieel op
    `is_primary = true AND deleted_at IS NULL`) laat een tweede hoofdadres niet
    toe. Deze test is er niet om de index te toetsen maar om te zien dat de
    import er nooit tegenaan loopt: een import die twee rijen primair maakt,
    faalt met een IntegrityError in plaats van met deze melding.
    """
    _import(db_session, _row("L-1", "Tine", "Peeters", "HOOFDLID", email=NIEUW))

    primair = [v for v, is_primary in _adressen(db_session, lid_met_twee_adressen).items()
               if is_primary]
    assert len(primair) == 1, f"precies één hoofdadres verwacht, gekregen: {primair}"
