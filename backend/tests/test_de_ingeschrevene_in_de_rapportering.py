"""De ingeschrevene in de rapportering, uit twee bronnen (#1135).

Koen vroeg Raakje op een activiteit *"Wie is ingeschreven?"* en kreeg *"Sorry, dat
lukt me even niet."* — na acht aanroepen naar Mistral in dertig seconden, alle acht
`ok`. Het universum kón die vraag niet beantwoorden: `f_registrations` draagt wel
`person_id`, maar niets ontsloot de ingeschrevene.

**Het getal dat deze tests stuurt.** Op PROD dragen van 132 inschrijvingen er 3 een
gekoppelde persoon en 129 alleen een contactnaam. Een test die alleen gekoppelde
personen zaait, bewijst dus niets over het gewone geval; élke test hieronder die
over namen gaat, zaait beide soorten.

**Wat hier NIET gemeten kan worden, en dat hoort erbij.** Het issue vraagt het
aantal modelaanroepen te meten. Het "vóór"-getal (acht) komt van Mistral op HDEV;
in deze suite is het model een nepprovider, dus wat een test kan tonen is dat de
lus eindigt zodra het model de weigering gebruikt — niet dat Mistral dat ook doet.
`test_een_model_dat_de_weigering_leest_is_na_twee_aanroepen_klaar` zegt dat
expliciet in zijn eigen docstring. Wat wél hard gemeten is, is de INHOUD van de
weigering: die noemt nu wat er wél bestaat.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.domains.chatbot.providers.base import AssistantMessage, ToolCall
from app.domains.reporting.assistant import (
    detokenise, dispatcher, scan_names, scrub_question,
)

pytestmark = pytest.mark.ui_serverrendered

TENANT = 2


def _activiteit_met_twee_soorten(db):
    """Eén activiteit, twee inschrijvingen: één met persoon, één met contactnaam.

    Dat is het 3-tegen-129-geval in het klein. Een opstelling met alleen een
    gekoppelde persoon zou elke test hieronder groen laten terwijl het gewone
    geval stuk is.
    """
    from datetime import date, timedelta

    from app.domains.activities.api import (Activity, ActivityDate,
                                            Registration)
    from app.domains.mdm.api import Person

    activiteit = Activity(tenant_id=TENANT, name="Wandeling")
    db.add(activiteit)
    db.flush()
    db.add(ActivityDate(tenant_id=TENANT, activity_id=activiteit.id,
                        start_date=date.today() + timedelta(days=7)))

    persoon = Person(tenant_id=TENANT, first_name="Mira", last_name="Vandenbulcke")
    db.add(persoon)
    db.flush()

    met_lid = Registration(tenant_id=TENANT, activity_id=activiteit.id,
                           person_id=persoon.id, registration_type="INDIVIDUAL")
    zonder_lid = Registration(tenant_id=TENANT, activity_id=activiteit.id,
                              person_id=None, registration_type="INDIVIDUAL",
                              contact_name="Joris Verlinden")
    db.add_all([met_lid, zonder_lid])
    db.flush()
    db.commit()
    return activiteit, persoon, met_lid, zonder_lid


def _rijen(db, activiteit_id):
    return db.execute(text(
        "SELECT registration_id, registrant_name, registrant_source "
        "FROM reporting.f_registrations WHERE activity_id = :a "
        "ORDER BY registration_id"), {"a": activiteit_id}).all()


# ── 1. Beide soorten leveren een naam, met de juiste herkomst ────────────────

def test_beide_soorten_inschrijving_leveren_een_naam_met_herkomst(db_session):
    """Test 1 uit het issue, en de reden dat de view de twee bronnen samenvoegt."""
    activiteit, _p, met_lid, zonder_lid = _activiteit_met_twee_soorten(db_session)

    per_id = {r[0]: (r[1], r[2]) for r in _rijen(db_session, activiteit.id)}

    assert per_id[met_lid.id] == ("Mira Vandenbulcke", "Lid")
    assert per_id[zonder_lid.id] == ("Joris Verlinden", "Contactgegeven")


def test_de_herkomst_volgt_de_naam_en_niet_de_koppeling(db_session):
    """Een inschrijving kan naar een verwijderde persoon wijzen.

    Dan levert `d_person` geen rij, valt de naam terug op de contactnaam, en zou
    'Lid' een zekerheid suggereren die er niet is. De kolom beschrijft dus waar de
    NAAM vandaan komt.
    """
    from app.domains.activities.api import Activity, Registration
    from app.domains.mdm.api import Person
    from app.soft_delete import soft_delete

    activiteit = Activity(tenant_id=TENANT, name="Quiz")
    db_session.add(activiteit)
    db_session.flush()
    weg = Person(tenant_id=TENANT, first_name="Weg", last_name="Gehaald")
    db_session.add(weg)
    db_session.flush()
    reg = Registration(tenant_id=TENANT, activity_id=activiteit.id,
                       person_id=weg.id, registration_type="INDIVIDUAL",
                       contact_name="Joris Verlinden")
    db_session.add(reg)
    db_session.flush()
    soft_delete(weg)
    db_session.commit()

    naam, herkomst = {r[0]: (r[1], r[2])
                      for r in _rijen(db_session, activiteit.id)}[reg.id]

    assert (naam, herkomst) == ("Joris Verlinden", "Contactgegeven")


# ── 2 en 3. Het model ziet een token, de beheerder leest een naam ────────────

def test_het_model_krijgt_een_token_voor_allebei_de_soorten(db_session):
    """Test 2: nooit een naam naar Mistral, ook niet voor een contactnaam.

    Getokeniseerd op de INSCHRIJVING en niet op de persoon: een contactnaam heeft
    geen persoons-id, dus tokeniseren op de persoon zou 98% van de rijen hun naam
    ongewijzigd laten meegeven.

    Tegenproef (uitgevoerd): `ai_exposure` van `registrant` op PLAIN gezet → de
    #1132-poort viel om mét het object en de kolom in de melding, en deze test
    kreeg de kale namen terug.
    """
    activiteit, _p, met_lid, zonder_lid = _activiteit_met_twee_soorten(db_session)

    uit = dispatcher(tenant_id=TENANT, max_rows=50)("run_report", {
        "objects": ["registrant", "registration_count"],
        "filters": [{"object": "activity_id", "operator": "eq",
                     "values": [str(activiteit.id)]}],
    }, db_session)
    payload = json.loads(uit) if isinstance(uit, str) else uit

    tekst = json.dumps(payload, ensure_ascii=False)
    assert "Vandenbulcke" not in tekst and "Verlinden" not in tekst, tekst
    assert f"inschrijving-{met_lid.id}" in tekst, tekst
    assert f"inschrijving-{zonder_lid.id}" in tekst, tekst


def test_de_beheerder_leest_een_naam_geen_token(db_session):
    """Test 3: de terugvertaling haalt de naam uit de persoon óf uit de contactnaam.

    Eén opzoeking, want de samenvoeging gebeurt in de weergave. Tegenproef
    (uitgevoerd): `registrant_name` uit `_LABEL_SQL["inschrijving"]` vervangen door
    een lege string → beide tokens bleven staan.
    """
    _act, _p, met_lid, zonder_lid = _activiteit_met_twee_soorten(db_session)

    uit = detokenise(
        db_session,
        f"Ik zie inschrijving-{met_lid.id} en inschrijving-{zonder_lid.id}.",
        tenant_id=TENANT)

    assert "Mira Vandenbulcke" in uit and "Joris Verlinden" in uit, uit
    assert "inschrijving-" not in uit, uit


# ── 4. De naadwachter kent de contactnamen ───────────────────────────────────

def test_de_naadwachter_kent_nu_ook_een_contactnaam(db_session):
    """Test 4 — met de nuance die het issue niet maakt, en die gemeten is.

    `person_name_parts` kent iedereen in de ledenadministratie. Een contactnaam
    staat op de INSCHRIJVING en zat in geen enkele lijst — behalve wanneer diezelfde
    naam toevallig óók in `mdm.persons` staat; dát deel was al gedekt. Deze test
    zaait daarom een contactnaam die NERGENS als persoon bestaat, want alleen die
    meet de winst.
    """
    from app.domains.mdm.api import person_name_parts

    _activiteit_met_twee_soorten(db_session)

    alleen_persoon = person_name_parts(db_session)
    met_inschrijvingen = scan_names(db_session)

    assert "verlinden" not in alleen_persoon, (
        "de opstelling deugt niet: deze naam bestaat blijkbaar óók als persoon, "
        "en dan meet deze test het oude gedrag")
    assert "verlinden" in met_inschrijvingen
    # En de oude bron blijft: dit is een uitbreiding, geen vervanging.
    assert "vandenbulcke" in met_inschrijvingen


def test_een_getypte_contactnaam_wordt_een_token(db_session):
    """Het gevolg voor de vraag die de beheerder typt.

    Vóór #1135 bleef zo'n naam staan en blokkeerde de naadwachter de oproep: de
    naam lekte niet, de vraag mislukte. Nu vertrekt er een token.
    """
    _act, _p, _met, zonder_lid = _activiteit_met_twee_soorten(db_session)

    schoon = scrub_question(db_session, "Wat weten we over Verlinden?",
                            tenant_id=TENANT)

    assert "Verlinden" not in schoon
    assert f"inschrijving-{zonder_lid.id}" in schoon, schoon


# ── 5. Een vraag die het universum niet kan beantwoorden ─────────────────────

def test_een_verzonnen_sleutel_krijgt_te_horen_wat_er_wel_bestaat(db_session):
    """De kern van punt 4, en het deel dat hard te meten is.

    Het model kreeg zijn weigeringen al letterlijk (#680) — daarom bleef het een
    andere sleutel proberen. De melding zei dat DEZE sleutel niet bestond, niet
    wat er wél was.

    Tegenproef (uitgevoerd): `_wat_bestaat_er_wel` laten teruggeven wat het kreeg
    → deze test viel om op de ontbrekende opsomming, terwijl de kale
    "Onbekend object"-melding gewoon bleef staan. Dat is precies het verschil
    tussen de oude en de nieuwe weigering.
    """
    uit = dispatcher(tenant_id=TENANT, max_rows=50)("run_report", {
        "objects": ["component", "wie_schreef_in"],
    }, db_session)
    payload = json.loads(uit) if isinstance(uit, str) else uit

    fout = payload["error"]
    assert "Onbekend object" in fout and "wie_schreef_in" in fout
    assert "Op dit onderwerp bestaan wél" in fout, fout
    # En het noemt het object dat de vraag écht beantwoordt.
    assert "registrant" in fout, fout


def test_zonder_enkel_herkenbaar_object_noemt_de_weigering_de_klassen(db_session):
    """Herkent er niets, dan is er geen onderwerp af te leiden.

    Dan blijven de klassen over — grover, maar nog altijd meer dan een kale
    "bestaat niet", en het zegt het model met zoveel woorden dat het mag stoppen.
    """
    uit = dispatcher(tenant_id=TENANT, max_rows=50)("run_report", {
        "objects": ["helemaal_verzonnen"],
    }, db_session)
    payload = json.loads(uit) if isinstance(uit, str) else uit

    fout = payload["error"]
    assert "zeg dat dan" in fout and "Leden" in fout, fout


def test_een_model_dat_de_weigering_leest_is_na_twee_aanroepen_klaar(db_session):
    """Het aantal aanroepen — met een eerlijke grens aan wat dit bewijst.

    Het "vóór"-getal uit het issue (acht aanroepen) komt van Mistral op HDEV. Hier
    is het model een nepprovider, dus deze test kan NIET aantonen dat Mistral na
    één weigering stopt. Wat ze wel meet is de lus: een model dat de weigering
    gebruikt, komt tot een eigen eindantwoord binnen twee aanroepen — en valt dus
    niet terug op de algemene verontschuldiging, wat vóór dit issue het enige
    mogelijke einde was zolang het bleef raden.

    De inhoud van de weigering is wat hard gemeten is; die staat in de test
    hierboven.
    """
    from app.domains.chatbot.providers.base import LLMProvider
    from app.domains.chatbot.service import run_chat
    from app.domains.reporting.assistant import tool_specs

    class LeestDeWeigering(LLMProvider):
        """Vraagt één keer iets dat niet bestaat, en antwoordt dan met wat het las."""

        name = "nep"

        def __init__(self):
            self.aanroepen = 0
            self.gezien = ""

        def complete(self, messages, tools=None, **kwargs):
            self.aanroepen += 1
            if self.aanroepen == 1:
                return AssistantMessage(tool_calls=[ToolCall(
                    id="1", name="run_report",
                    arguments={"objects": ["component", "wie_schreef_in"]})])
            self.gezien = " ".join(str(m.get("content") or "") for m in messages)
            return AssistantMessage(content="Dat kan ik niet uit de cijfers halen.")

    provider = LeestDeWeigering()
    antwoord = run_chat(
        db_session,
        [{"role": "user", "content": "Wie schreef in?"}],
        provider, max_rounds=6, tools=tool_specs(),
        dispatch=dispatcher(tenant_id=TENANT, max_rows=50))

    assert provider.aanroepen == 2, provider.aanroepen
    assert "Sorry, dat lukt me even niet" not in antwoord, antwoord
    assert "Op dit onderwerp bestaan wél" in provider.gezien, (
        "de weigering met de opsomming bereikte het model niet")
