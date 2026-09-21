"""De naadwachter scant de WAARDEN van een tool-resultaat, niet zijn etiketten (#1154).

Koen stelde op HDEV de vraag waarvoor #1135 gebouwd is — *"Wie is er ingeschreven?"*
— en kreeg geen antwoord maar de weigering van de wachter. Gemeten in
`ai.ai_call_log`: de enige naamtreffer in de hele payload zat in de **kolomtitel**
`{"key": "registrant_source", "name": "Herkomst inschrijver"}`. De rijen eronder
droegen keurig `inschrijving-46`, dus er lekte niets.

Waarom het matchte: sinds #1135 staan ook de contactnamen van inschrijvingen in de
namenlijst, en op HDEV bevat er een het gewone woord *inschrijver*. Dat is geen
eigenaardigheid van één testrij maar een klasse — elke achternaam die ook een
gewoon woord is (bos, mol, dekker, visser) kan een kolomtitel of een sleutel raken.

**De tweede test is de belangrijkste van dit bestand.** Een reparatie die de
etiketten overslaat, is ook een nette manier om de wachter uit te zetten; alleen
`test_een_naam_in_een_waarde_blijft_blokkeren` scheidt die twee. Vandaar ook de
derde: dezelfde naam verhuist van etiket naar waarde en terug, en de uitkomst hoort
mee te bewegen.
"""
from __future__ import annotations

import json

import pytest

from app.domains.chatbot.seam import admin_rules, findings, payload_text

pytestmark = pytest.mark.ui_agnostisch

#: Het woord uit de HDEV-meting: een contactnaam die een gewoon woord bevat, zodat
#: het in de namenlijst belandt én in een kolomtitel voorkomt.
NAAM = "inschrijver"

REGELS = admin_rules(lambda: {NAAM}, capability="rapportage",
                     scan_prompt_names=False)


def _payload(*, kolomtitel: str, waarde: str) -> list[dict]:
    """Een gesprek zoals `run_chat` het opbouwt: vraag, tool-aanroep, tool-resultaat."""
    resultaat = {
        "columns": [{"key": "registrant", "name": "Ingeschreven door"},
                    {"key": "registrant_source", "name": kolomtitel}],
        "rows": [{"registrant": "inschrijving-46", "registrant_source": waarde}],
        "totals": {}, "row_count": 1,
    }
    return [
        {"role": "system", "content": "De catalogus."},
        {"role": "user", "content": "Wie is er ingeschreven?"},
        {"role": "tool", "tool_call_id": "1", "name": "run_report",
         "content": json.dumps(resultaat, ensure_ascii=False)},
    ]


def _naamtreffer(bevindingen: list[str]) -> bool:
    return any("naam uit de ledenadministratie" in b for b in bevindingen)


# ── 1. Het gemelde geval ─────────────────────────────────────────────────────

def test_een_naam_in_een_kolomtitel_blokkeert_niet_meer(db_session=None):
    """Het geval uit de melding, nagebouwd: alleen het etiket draagt het woord.

    De rijen dragen tokens, precies zoals op HDEV. Vóór deze reparatie
    blokkeerde dit; rood bewezen door `_naamscan_tekst` te laten teruggeven wat
    `payload_text` geeft — dan komt de blokkade terug.
    """
    payload = _payload(kolomtitel="Herkomst inschrijver", waarde="Contactgegeven")

    # De meting die de melding onderbouwt: het woord STAAT in de payload…
    assert NAAM in payload_text(payload, include_system=False).lower()
    # …en toch hoort de wachter niets te vinden, want het staat in een etiket.
    assert not _naamtreffer(findings(payload, REGELS)), findings(payload, REGELS)


# ── 2. De bescherming die overeind moet blijven ──────────────────────────────

def test_een_naam_in_een_waarde_blijft_blokkeren():
    """DE test van dit bestand. Zonder haar is de reparatie een uitschakelaar.

    Dit is het kanaal waarlangs een naam kan vertrekken: een rij die geen token
    draagt maar de naam zelf. Dat hoort de wachter tegen te houden, ook nu de
    etiketten erbuiten vallen.
    """
    payload = _payload(kolomtitel="Herkomst", waarde=f"Jan {NAAM.capitalize()}")

    assert _naamtreffer(findings(payload, REGELS)), (
        "een naam in een WAARDE hoort geblokkeerd te worden — deze reparatie mag "
        "de wachter niet uitzetten")


# ── 3. De tegenproef op de vorm ──────────────────────────────────────────────

def test_dezelfde_naam_beweegt_mee_van_etiket_naar_waarde():
    """Verhuis het woord en de uitkomst hoort te kantelen.

    Een test die alleen het eerste geval dekt, staat ook groen als de hele
    naamcontrole verdwijnt. Deze twee samen sluiten dat af: dezelfde payload,
    dezelfde namenlijst, alleen de PLAATS van het woord verschilt.
    """
    als_etiket = _payload(kolomtitel=f"Herkomst {NAAM}", waarde="Contactgegeven")
    als_waarde = _payload(kolomtitel="Herkomst", waarde=NAAM)

    assert not _naamtreffer(findings(als_etiket, REGELS))
    assert _naamtreffer(findings(als_waarde, REGELS))


# ── Wat de reparatie NIET mag verruimen ──────────────────────────────────────

def test_wat_de_beheerder_typt_blijft_onverkort_gescand():
    """Het andere kanaal blijft zoals het was.

    In een getypte vraag is een woord dat toevallig een naam is, niet te
    onderscheiden van de naam zelf — daar geldt de afweging van dit issue niet.
    """
    payload = [{"role": "user", "content": f"Wat weten we over {NAAM}?"}]

    assert _naamtreffer(findings(payload, REGELS))


def test_een_tool_resultaat_dat_geen_json_is_wordt_volledig_gescand():
    """Liever een vals alarm dan een blinde vlek.

    Een tool die ooit platte tekst teruggeeft, mag niet stilzwijgend buiten de
    scan vallen omdat het ontleden mislukt.
    """
    payload = [{"role": "tool", "tool_call_id": "1", "name": "run_report",
                "content": f"kon niets vinden voor {NAAM}"}]

    assert _naamtreffer(findings(payload, REGELS))


def test_een_onbekend_veld_in_een_tool_resultaat_wordt_wel_gescand():
    """De eigenschap van `payload_text` die behouden moest blijven.

    De reparatie verwijdert de BEKENDE etiketvelden; ze scant niet alleen de
    bekende waardevelden. Krijgt een tool-antwoord er morgen een veld bij, dan
    wordt dat gelezen in plaats van overgeslagen.
    """
    resultaat = {"columns": [{"key": "x", "name": "X"}], "rows": [],
                 "verzonnen_nieuw_veld": f"Jan {NAAM.capitalize()}"}
    payload = [{"role": "tool", "tool_call_id": "1", "name": "run_report",
                "content": json.dumps(resultaat, ensure_ascii=False)}]

    assert _naamtreffer(findings(payload, REGELS)), (
        "een veld dat deze code niet kent, hoort gescand te worden")


def test_de_patroon_controles_lezen_nog_de_volle_payload():
    """Alleen de NAAM-controle slaat etiketten over.

    Een e-mailadres in een kolomtitel is geen vals alarm maar een fout die je wil
    zien, dus die controle blijft op de volle tekst kijken.
    """
    resultaat = {"columns": [{"key": "x", "name": "post@example.org"}], "rows": []}
    payload = [{"role": "tool", "tool_call_id": "1", "name": "run_report",
                "content": json.dumps(resultaat, ensure_ascii=False)}]

    assert any("e-mailadres" in b for b in findings(payload, REGELS))
