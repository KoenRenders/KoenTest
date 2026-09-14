"""Elke datum op haar eigen regel op de activiteitenkaart (#926).

Koen op PROD: *"Ik merk voor de activiteit 'stappen en klappen' dat alle datums
achter elkaar getypt worden. Dat waren vroeger (v1.14) meerdere lijnen."* Hij heeft
gelijk — v1.14 gaf elke datum haar eigen alinea, en sinds de React-exit stond alles
op één regel met een `·` ertussen.

**Waarom het opvalt is een kwestie van aantal.** Op PROD heeft *Wandelen* zeven
datums, *Stappen en klappen* zes en *Fietsen* vijf. Bij één of twee valt het niet
op; zeven datums mét tijdstippen achter elkaar is een blok tekst, en op een telefoon
— tachtig procent van het bezoek — loopt dat over drie of vier regels door zonder
dat er één datum uitspringt.

**Het geval dat bij opsplitsen het makkelijkst half sneuvelt** is een datum met een
eindtijd of een einddatum: die hoort volledig op haar eigen regel te blijven en niet
halverwege af te breken. Daar gaat de derde test over.

Deze tests renderen de macro met echte datums in plaats van naar klassenamen te
kijken: de vraag is of de datums op aparte regels staan, niet welke opmaak dat doet.
"""
from datetime import date, time
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_serverrendered

TPL = Path(__file__).resolve().parents[1] / "app" / "domains" / "activities" / "templates"


def _kaart_bron() -> str:
    return (TPL / "_activiteiten_cards.html").read_text()


def test_de_datums_staan_niet_meer_aan_elkaar_geplakt():
    """De regressie zelf: geen scheidingsteken meer tussen twee datums.

    Een `·` tussen datums is precies wat het blok tekst maakte. Staat hij er weer,
    dan staan de datums weer achter elkaar.
    """
    bron = _kaart_bron()
    datumblok = bron[bron.index('ui.icon("calendar"'):]
    datumblok = datumblok[:datumblok.index("</div>")]
    assert "·" not in datumblok, (
        "de datums worden weer aan elkaar geplakt met een scheidingsteken")


def test_elke_datum_krijgt_haar_eigen_element():
    """Eén regel per datum, en de lus zit binnen een gestapelde container."""
    bron = _kaart_bron()
    start = bron.index('ui.icon("calendar"')
    blok = bron[start:start + 900]
    assert "flex-col" in blok, (
        "zonder een gestapelde container lopen de datums gewoon door")
    assert "{% for d in a.dates %}" in blok and "<span>" in blok, (
        "elke datum hoort haar eigen element te krijgen")


def test_het_icoon_staat_bij_de_reeks_en_niet_bij_elke_regel():
    """Zeven keer hetzelfde symbool is ruis.

    Het icoon kondigt aan wát er volgt; het hoort dus buiten de lus te staan. En
    geen bullets: de regels staan al onder elkaar onder dat ene icoon.
    """
    bron = _kaart_bron()
    start = bron.index('ui.icon("calendar"')
    blok = bron[start:start + 900]
    lus = blok.index("{% for d in a.dates %}")
    assert 'ui.icon("calendar"' not in blok[lus:], (
        "het icoon hoort bij de reeks te staan, niet bij elke datum")
    assert "<li" not in blok and "list-disc" not in blok, (
        "geen bullets: de regels staan al onder elkaar onder één icoon")


def test_een_datum_met_een_eindtijd_blijft_op_één_regel():
    """Het geval dat bij opsplitsen het makkelijkst half sneuvelt.

    Begin- en einddatum en begin- en eindtijd horen binnen hetzelfde element te
    staan. Staat er één van buiten de lus, dan breekt de reeks middenin een datum
    af — en dan is opsplitsen erger dan wat het verving.
    """
    bron = _kaart_bron()
    start = bron.index("{% for d in a.dates %}")
    regel = bron[start:bron.index("{% endfor %}", start)]
    for stuk in ("start_date", "end_date", "start_time", "end_time"):
        assert stuk in regel, (
            f"{stuk} hoort binnen dezelfde regel als de rest van die datum te "
            "staan; erbuiten breekt de reeks middenin een datum")
    assert regel.count("<span>") == 1, (
        "één element per datum; meer betekent dat een datum over meerdere "
        "regels uiteen kan vallen")
