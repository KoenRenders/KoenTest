"""Omschrijving, bestuursnotities en organisatoren in de rapportering (#1077).

Koen wil een activiteitenverslag uit de rapportering kunnen halen en doorsturen.
De drie velden die hij daarvoor nodig heeft, bestonden wel op de activiteit maar
niet in `d_activity` — en Raakje rapporteert over diezelfde verzameling, dus wat
daar niet in staat, kent hij niet.

**De organisatoren komen twee keer, en dat is de bedoeling** (Koen, 20 september
2026): *"Ik wil de lijst kunnen afdrukken met één rij per activiteit maar ik wil
wel dat Raakje kan vertellen wie een activiteit organiseert."* Dus één
samengevoegde kolom op de activiteit (één rij per activiteit, niet naar een model)
en één dimensie met een eigen korrel (één rij per organisator, getokeniseerd).

**De blootstelling is per veld beslist en wordt hier op de ECHTE weg getoetst.**
Een test die de enum-waarde vergelijkt, blijft groen als niemand die waarde nog
leest; daarom loopt elke toets hier langs de dispatcher of langs de tokenisatie.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):

- de twee blootstellingen verwisselen — notities op TOKENISED en organisator op
  NONE — → **beide** weigeringstesten vallen om, elk aan hun eigen kant. Valt er
  maar één om, dan toetst de andere de blootstelling niet echt;
- de nieuwe arm uit `_LABEL_SQL["persoon"]` halen → de terugvertaaltest valt om en
  het antwoord houdt een kaal `persoon-<id>`;
- de samengevoegde kolom op `string_agg` zonder filter op `is_contact` zetten →
  de test die telt wie er in de regel staat, valt om.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from app.domains.reporting.api import BY_KEY, Selection, run_validated

TENANT = 8811


@pytest.fixture
def activiteit(db_session):
    """Eén activiteit met twee organisatoren, waarvan één niet op de affiche."""
    from app.domains.activities.api import Activity
    from app.domains.activities.models import ActivityOrganiser
    from app.domains.mdm.api import Person

    a = Activity(tenant_id=TENANT, name="Brood en Spelen",
                 description="Een namiddag vol brood en spelen.",
                 board_notes="Zaal vragen aan de parochie. Niet doorsturen.")
    db_session.add(a)
    db_session.flush()

    mensen = {}
    for voornaam, contact, orde in (("Jan", True, 0), ("Marie", True, 1),
                                    ("Stil", False, 2)):
        persoon = Person(tenant_id=TENANT, first_name=voornaam,
                         last_name="Trekker", date_of_birth=date(1980, 1, 1),
                         gender_code="M")
        db_session.add(persoon)
        db_session.flush()
        db_session.add(ActivityOrganiser(tenant_id=TENANT, activity_id=a.id,
                                         person_id=persoon.id,
                                         is_contact=contact, sort_order=orde))
        mensen[voornaam] = persoon
    db_session.commit()
    return {"activiteit": a, "mensen": mensen}


def _rij(db, *objecten) -> dict:
    # `layout="detail"`: deze drie velden zijn DETAILS en geen dimensies — je
    # groepeert niet op een omschrijving. De detailvorm somt de rijen op zoals ze
    # zijn, en dat is precies de vorm van Koens verslag.
    # `activity_last_date` erbij omdat een lijst minstens één veld van het FEIT
    # zelf nodig heeft: de drie nieuwe velden en de naam staan allemaal op de
    # dimensie `d_activity`, en uit alleen dimensies valt geen lijst te maken.
    resultaat = run_validated(
        db, Selection(object_keys=tuple(objecten) + ("activity_last_date",),
                      layout="detail"),
        tenant_id=TENANT)
    assert resultaat.rows, "geen rij — draaide de migratie?"
    return resultaat.rows[0]


# ── De drie velden komen door ────────────────────────────────────────────────

def test_de_omschrijving_staat_in_het_rapport(db_session, activiteit):
    rij = _rij(db_session, "activity", "activity_description")

    assert rij["activity_description"] == "Een namiddag vol brood en spelen."


def test_de_interne_nota_staat_in_het_rapport(db_session, activiteit):
    """Zichtbaar voor de bestuurder die het rapport zelf opvraagt — de belofte op
    het scherm zegt dat sinds #1077 ook met zoveel woorden."""
    rij = _rij(db_session, "activity", "activity_board_notes")

    assert "parochie" in rij["activity_board_notes"]


def test_een_leeg_veld_wordt_leeg_en_niet_de_vorige_waarde(db_session, activiteit):
    """Tegenproef uit het issue: leegmaken moet de kolom leegmaken.

    Een view die haar kolom uit de verkeerde bron haalt, blijft de oude waarde
    tonen — en dat valt niet op zolang je alleen gevulde velden toetst.
    """
    activiteit["activiteit"].description = None
    db_session.commit()

    assert _rij(db_session, "activity", "activity_description")["activity_description"] is None


# ── De organisatoren, in twee vormen ─────────────────────────────────────────

def test_de_samengevoegde_regel_toont_de_affichenamen_in_volgorde(db_session,
                                                                   activiteit):
    """Eén rij per activiteit, en alleen wie op de affiche komt.

    'Stil' is organisator zonder aangevinkt te zijn: die hoort hier niet in, want
    deze kolom zegt wat er gedrukt wordt.
    """
    rij = _rij(db_session, "activity", "activity_organisers")

    assert rij["activity_organisers"] == "Jan Trekker · Marie Trekker"


def test_de_dimensie_geeft_een_rij_per_organisator(db_session, activiteit):
    """Eigen korrel: hier staat óók wie niet op de affiche komt."""
    resultaat = run_validated(
        db_session, Selection(object_keys=("activity_organiser", "activity_count")),
        tenant_id=TENANT)

    namen = sorted(r["activity_organiser"] for r in resultaat.rows)
    assert namen == ["Jan Trekker", "Marie Trekker", "Stil Trekker"]


def test_zonder_organisatoren_blijft_de_kolom_leeg_zonder_fout(db_session):
    """Toets 4 van het issue: een activiteit zonder organisatoren."""
    from app.domains.activities.api import Activity

    kaal = Activity(tenant_id=TENANT, name="Zonder trekkers")
    db_session.add(kaal)
    db_session.commit()

    resultaat = run_validated(
        db_session,
        Selection(object_keys=("activity", "activity_organisers",
                               "activity_last_date"), layout="detail"),
        tenant_id=TENANT)
    rijen = {r["activity"]: r["activity_organisers"] for r in resultaat.rows}

    assert "Zonder trekkers" in rijen
    assert rijen["Zonder trekkers"] is None


# ── Wat er naar een taalmodel mag ────────────────────────────────────────────

def _dispatch(db):
    from app.domains.reporting.assistant import dispatcher

    return dispatcher(tenant_id=TENANT, max_rows=50)


def _vraag(db, object_key: str) -> str:
    import json

    return _dispatch(db)(
        "run_report",
        {"objects": ["activity", object_key, "activity_last_date"],
         "layout": "detail"}, db)


@pytest.mark.parametrize("object_key,woord", [
    ("activity_board_notes", "parochie"),
    ("activity_organisers", "Trekker"),
])
def test_deze_velden_bereiken_geen_enkel_taalmodel(db_session, activiteit,
                                                    object_key, woord):
    """Langs de ECHTE weg: de dispatcher weigert vóór er een query draait.

    Niet de enum-waarde vergeleken — die blijft kloppen als niemand haar leest.
    De bestuursnotitie is vrije interne tekst; de samengevoegde organisatoren
    dragen namen zonder id, en een naam zonder id laat de naadwachter de hele
    toolaanroep blokkeren in plaats van alleen die kolom.
    """
    antwoord = _vraag(db_session, object_key)

    assert woord not in antwoord
    assert "niet toegelaten" in antwoord.lower() or "error" in antwoord.lower()


def test_een_organisator_reist_als_token_en_niet_als_naam(db_session, activiteit):
    """Toets 3: de dimensie mét eigen korrel mag wél mee, als `persoon-<id>`."""
    import json

    ruw = _dispatch(db_session)(
        "run_report", {"objects": ["activity_organiser", "activity_count"]},
        db_session)
    antwoord = json.loads(ruw)

    waarden = [r["activity_organiser"] for r in antwoord.get("rows", [])]
    assert waarden, antwoord
    assert all(w.startswith("persoon-") for w in waarden), waarden
    assert not any("Trekker" in w for w in waarden)


def test_het_token_wordt_teruggevertaald_naar_de_naam(db_session, activiteit):
    """De helft die anders vergeten wordt.

    Een getokeniseerde waarde die niet terugvertaald kan worden, blijft als
    `persoon-90` in het antwoord staan dat de bestuurder leest — `detokenise`
    laat een onopgelost token bewust staan. Tot #1077 kende de persoon-opzoeking
    alleen BESTUURSLEDEN, dus elke organisator die dat niet is, bleef een token.
    """
    from app.domains.reporting.assistant import detokenise

    jan = activiteit["mensen"]["Jan"]
    tekst = f"De trekker is persoon-{jan.id}."

    assert detokenise(db_session, tekst, tenant_id=TENANT) == "De trekker is Jan Trekker."
