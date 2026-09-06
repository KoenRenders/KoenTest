"""#685 — een lege cel in het ledenrapport wist niet wat er al staat.

`_apply_person_fields` overschreef blind, dus één herimport kon een geboortedatum
stilzwijgend op NULL zetten. Juist die twee velden zijn sinds #681 overal élders
verplicht: het formulier weigert ze leeg te laten, en de import kon ze
ondertussen weghalen.

De regel die Koen koos: **een import vult aan en corrigeert, hij wist niet.** Een
leeg vakje in een rapport uit een ander systeem betekent "hier weet ik niets van",
niet "verwijder dit".

**Deze tests kijken naar de opgeslagen persoon na een tweede import, niet naar de
rapporttekst.** Anders meet je de melding en niet de data — en het is de data die
verdween.

**Twee plekken, net als bij #683.** Alleen `_apply_person_fields` repareren zou het
zichtbare verlies stoppen maar `_person_field_changes` een wijziging laten melden
die niet gebeurt: het rapport telt dan `persons_updated` te hoog en
`snapshot_person` schrijft een auditregel voor een verandering van niets. Vandaar
één `_person_field_values` waar beide doorheen gaan — en een test die het bewijst.
"""
from datetime import date

import pytest

from app.domains.mdm.api import Person, PersonHistory
from app.domains.mdm.import_service import upsert_families
from tests.conftest import seed_postal_code

pytestmark = pytest.mark.ui_agnostisch


def _row(lidnr, voornaam, naam, relatie, *, geboortedatum=None, geslacht=None,
         email=None):
    return {
        "lidnr": lidnr, "voornaam": voornaam, "naam": naam,
        "straat": "milostraat", "huisnummer": "40", "busnummer": "",
        "postcode": "2400", "gemeente": "Mol",
        "email": email, "telefoon": None, "gsm": None,
        "geboortedatum": geboortedatum, "geslacht": geslacht,
        "bestuurslid": None, "_relatie": relatie,
    }


def _import(db, rijen, *, apply=True):
    return upsert_families(db, [rijen], {}, [], apply=apply)


def _persoon(db, voornaam):
    return db.query(Person).filter(Person.first_name == voornaam).one()


# ── 1. De kern: een lege cel wist niets ──────────────────────────────────────

def test_een_lege_geboortedatum_laat_de_bestaande_staan(db_session):
    """Test 1 uit het issue. Stond rood vóór deze wijziging."""
    seed_postal_code(db_session)
    _import(db_session, [_row("700", "Jan", "Janssens", "HOOFDLID",
                              geboortedatum=date(1980, 1, 1), geslacht="M",
                              email="jan700@example.com")])
    assert _persoon(db_session, "Jan").date_of_birth == date(1980, 1, 1)

    # Tweede import, zelfde persoon, geboortedatum niet ingevuld.
    _import(db_session, [_row("700", "Jan", "Janssens", "HOOFDLID",
                              geslacht="M", email="jan700@example.com")])

    db_session.expire_all()
    assert _persoon(db_session, "Jan").date_of_birth == date(1980, 1, 1), (
        "de import heeft de geboortedatum gewist")


def test_een_leeg_geslacht_laat_het_bestaande_staan(db_session):
    seed_postal_code(db_session)
    _import(db_session, [_row("701", "An", "Janssens", "HOOFDLID",
                              geboortedatum=date(1980, 1, 1), geslacht="F",
                              email="an701@example.com")])
    _import(db_session, [_row("701", "An", "Janssens", "HOOFDLID",
                              geboortedatum=date(1980, 1, 1),
                              email="an701@example.com")])

    db_session.expire_all()
    assert _persoon(db_session, "An").gender_code == "F"


@pytest.mark.parametrize("leeg", [None, "", "   "])
def test_ook_witruimte_telt_als_leeg(db_session, leeg):
    """Een cel met een spatie is geen waarde. Zonder deze grens zou een rapport
    dat lege cellen als spatie exporteert het probleem terugbrengen."""
    seed_postal_code(db_session)
    _import(db_session, [_row("702", "Piet", "Peeters", "HOOFDLID",
                              geboortedatum=date(1975, 6, 6), geslacht="M",
                              email="piet702@example.com")])
    _import(db_session, [_row("702", "Piet", "Peeters", "HOOFDLID",
                              geboortedatum=date(1975, 6, 6), geslacht=leeg,
                              email="piet702@example.com")])

    db_session.expire_all()
    assert _persoon(db_session, "Piet").gender_code == "M"


# ── 2. Corrigeren blijft wél werken ──────────────────────────────────────────

def test_een_gevulde_cel_corrigeert_nog_altijd(db_session):
    """De keerzijde, en even belangrijk: zonder deze test zou "nooit wijzigen" ook
    slagen — en dan is de import geen bron van waarheid meer."""
    seed_postal_code(db_session)
    _import(db_session, [_row("703", "Marie", "Peeters", "HOOFDLID",
                              geboortedatum=date(1990, 3, 3), geslacht="F",
                              email="marie703@example.com")])
    _import(db_session, [_row("703", "Marie", "Peeters", "HOOFDLID",
                              geboortedatum=date(1991, 4, 4), geslacht="X",
                              email="marie703@example.com")])

    db_session.expire_all()
    persoon = _persoon(db_session, "Marie")
    assert persoon.date_of_birth == date(1991, 4, 4)
    assert persoon.gender_code == "X"


def test_een_nieuwe_persoon_krijgt_gewoon_wat_de_rij_zegt(db_session):
    """De regel geldt alleen voor bestaande personen: bij een nieuwe is er niets
    om te behouden. Een onvolledige rij komt binnen en wordt gemeld (#681)."""
    seed_postal_code(db_session)
    rapport = _import(db_session, [_row("704", "Nieuw", "Persoon", "HOOFDLID",
                                        email="nieuw704@example.com")])

    persoon = _persoon(db_session, "Nieuw")
    assert persoon.date_of_birth is None and persoon.gender_code is None
    assert any("Nieuw Persoon" in w for w in rapport.warnings)


# ── 3. Het rapport en de audit melden geen wijziging die niet gebeurt ────────

def test_een_lege_cel_telt_niet_als_wijziging(db_session):
    """De tweede plek. Zou alleen het toepassen gerepareerd zijn, dan meldde het
    rapport hier een update die niet plaatsvond."""
    seed_postal_code(db_session)
    _import(db_session, [_row("705", "Stil", "Janssens", "HOOFDLID",
                              geboortedatum=date(1980, 1, 1), geslacht="M",
                              email="stil705@example.com")])
    persoon = _persoon(db_session, "Stil")
    voor = (db_session.query(PersonHistory)
            .filter(PersonHistory.person_id == persoon.id).count())

    rapport = _import(db_session, [_row("705", "Stil", "Janssens", "HOOFDLID",
                                        email="stil705@example.com")])

    assert rapport.persons_updated == 0, (
        "het rapport meldt een wijziging die niet gebeurt")
    na = (db_session.query(PersonHistory)
          .filter(PersonHistory.person_id == persoon.id).count())
    assert na == voor, "er is een lege auditregel geschreven"


def test_een_bestaande_persoon_wordt_niet_meer_als_onvolledig_gemeld(db_session):
    """De melding kijkt naar wat er ná de import staat, niet naar de rij.

    Anders noemt het rapport bij élke herimport dezelfde mensen zonder dat er iets
    aan te vullen valt — en een waarschuwing die je altijd ziet, lees je niet meer.
    """
    seed_postal_code(db_session)
    _import(db_session, [_row("706", "Volledig", "Janssens", "HOOFDLID",
                              geboortedatum=date(1980, 1, 1), geslacht="M",
                              email="vol706@example.com")])

    rapport = _import(db_session, [_row("706", "Volledig", "Janssens", "HOOFDLID",
                                        email="vol706@example.com")])
    assert not [w for w in rapport.warnings if "Volledig" in w]


# ── 4. De asymmetrie met contactgegevens is bedoeld ─────────────────────────

def test_een_leeg_gsm_nummer_verwijdert_wel(db_session):
    """`_upsert_contact` blijft op leeg verwijderen, en dat is geen slordigheid.

    Een gsm-nummer kan ophouden te bestaan — iemand geeft zijn nummer op, of wil
    het niet meer delen — en dan is een lege cel een mededeling. Een geboortedatum
    houdt niet op te bestaan. Wie deze twee gelijktrekt uit netheid, trekt ze de
    verkeerde kant op; deze test staat er zodat dat opvalt.
    """
    from app.domains.mdm.api import ContactDetail

    seed_postal_code(db_session)
    rij = _row("707", "Bel", "Janssens", "HOOFDLID",
               geboortedatum=date(1980, 1, 1), geslacht="M",
               email="bel707@example.com")
    rij["gsm"] = "0470000000"
    _import(db_session, [rij])
    persoon = _persoon(db_session, "Bel")
    assert [c for c in persoon.contact_details if c.contact_type_code == "MOBILE"]

    zonder = _row("707", "Bel", "Janssens", "HOOFDLID",
                  geboortedatum=date(1980, 1, 1), geslacht="M",
                  email="bel707@example.com")
    _import(db_session, [zonder])

    db_session.expire_all()
    mobiel = (db_session.query(ContactDetail)
              .filter(ContactDetail.person_id == persoon.id,
                      ContactDetail.contact_type_code == "MOBILE").all())
    assert not mobiel, "een leeg gsm-veld hoort het nummer wél te verwijderen"
    assert _persoon(db_session, "Bel").date_of_birth == date(1980, 1, 1), (
        "maar de geboortedatum blijft")


# ── 5. Eén plek voor de regel ────────────────────────────────────────────────

def test_bepalen_en_toepassen_delen_dezelfde_regel(db_session):
    """Een bronregel, omdat gedrag hier niets bewijst: twee kopieën die vandaag
    hetzelfde doen, geven dezelfde uitkomst. Wat ze onderscheidt is of ze morgen
    nog samen wijzigen (#683 leerde dat op de harde manier)."""
    import inspect

    from app.domains.mdm import import_service

    for functie in (import_service._apply_person_fields,
                    import_service._person_field_changes):
        bron = inspect.getsource(functie)
        assert "_person_field_values" in bron, (
            f"{functie.__name__} bepaalt de waarden zelf i.p.v. via de gedeelde "
            "regel — dan kunnen melden en toepassen uiteenlopen (#685)")
