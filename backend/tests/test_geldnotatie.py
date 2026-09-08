"""#735 — bedragen staan overal in nl-BE-notatie: `€ 35,00`, niet `€ 35.00`.

Het beheer schreef met een punt, de publieke site met een komma (`cms/render.py`
deed daar zijn eigen `.replace(".", ",")`). Die `.replace` is het bewijs dat de
komma de bedoeling was; ze was alleen op één plek gebeurd. En in het Nederlands is
de punt een duizendtalteken, dus `€ 1342.00` naast `€ 25,00` op hetzelfde scherm is
niet alleen inconsistent maar ook verkeerd te lezen.

**De laatste test is de gevaarlijke kant.** Twee van de plekken die `%.2f`
uitschrijven zijn geen weergave maar de **inhoud van een invoerveld** — daar hoort
een machineleesbare waarde. Ze werken vandaag toevallig ook met een komma (het zijn
tekstvelden met `inputmode="decimal"` en `_decimal()` doet `.replace(",", ".")`),
maar dat is een keten van drie feiten. Maakt iemand er ooit een `type="number"` van,
dan is een komma een ongeldige waarde: het veld toont leeg, er wordt niets
verstuurd, en een prijs is stil weg.

Zonder die tegenproef staat de gate hieronder ook groen wanneer iemand een komma in
een prijsveld zet — en dan bewaakt ze precies het omgekeerde van wat ze belooft.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (lokaal):
  * `.replace(".", ",")` uit `kernel/geld.py` gehaald → de vier filtertests vallen om;
  * `{{ rij.due|geld }}` in `_betalingen_lijst.html` terug op `{{ "%.2f"|format(...) }}`
    → de gate valt om met bestand en regelnummer;
  * de `value=` op regel 236 van `_aa_detail.html` op `|geld` gezet → de laatste test
    valt om, en de gate blijft groen.
"""
import re
from decimal import Decimal
from pathlib import Path

import pytest

from app.kernel.geld import bedrag

pytestmark = pytest.mark.ui_serverrendered

TEMPLATES = sorted((Path(__file__).resolve().parents[1] / "app").rglob("*.html"))


# ── Het filter zelf ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("waarde, verwacht", [
    (35, "35,00"),
    (0, "0,00"),
    (Decimal("1342.5"), "1342,50"),
    (Decimal("-20.00"), "-20,00"),
    (None, "0,00"),
])
def test_het_filter_schrijft_nl_be(waarde, verwacht):
    """Ook het negatieve geval: terugbetalingen dragen een minteken en dat hoort
    zichtbaar te blijven. En een `Decimal`, want dat is wat de records dragen."""
    assert bedrag(waarde) == verwacht


# ── De gate ──────────────────────────────────────────────────────────────────

def test_geen_handgeschreven_bedragen_meer_in_de_sjablonen():
    """`{{ "%.2f"|format(x) }}` naast een euroteken hoort `{{ x|geld }}` te zijn.

    De uitzondering is precies afgebakend: een `value=` van een invoerveld draagt
    een machineleesbare waarde en blijft met een punt. Zie de laatste test.
    """
    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(pad.read_text().splitlines(), 1):
            if '"%.2f"|format' not in regel or "value=" in regel:
                continue
            fouten.append(f"{pad.name}:{nr}: {regel.strip()[:100]}")
    assert not fouten, (
        "Bedragen horen door het `geld`-filter te gaan (#735):\n  " + "\n  ".join(fouten))


def test_de_prijsvelden_dragen_nog_een_machineleesbare_waarde():
    """De tegenproef, en de reden dat de gate een uitzondering heeft.

    Een komma in de `value` van een prijsveld is vandaag nog te verwerken, maar dat
    hangt aan drie losse feiten. Deze test legt vast dat die twee velden een punt
    houden — niet omdat het mooier is, maar omdat er een prijs stil kan verdwijnen.
    """
    bron = (Path(__file__).resolve().parents[1]
            / "app/domains/activities/templates/_aa_detail.html").read_text()
    # Enkel de BEWERK-velden vullen een bestaande prijs in; de aanmaakvelden staan
    # leeg of op "0" en hebben geen opmaak nodig.
    prijsvelden = [r for r in bron.splitlines()
                   if ('ui.input_control("price"' in r or 'ui.input_control("member_price"' in r)
                   and "%.2f" in r]
    assert len(prijsvelden) == 2, (
        f"verwacht twee ingevulde prijsvelden, gevonden {len(prijsvelden)}")
    for regel in prijsvelden:
        assert "value=" in regel and "|geld" not in regel, (
            "een prijsveld gaat door het geld-filter; een komma kan daar een prijs "
            f"stil laten verdwijnen:\n  {regel.strip()[:110]}")


def test_de_melding_van_de_servicelaag_gebruikt_dezelfde_notatie():
    """De weigering bij een te hoge terugbetaling komt sinds #723 op het scherm.

    Die zin staat in de servicelaag en heeft geen Jinja-filter; ze leest dezelfde
    helper. Zonder deze test schrijft de melding het bedrag anders dan de kaart
    erboven — precies de tweespalt die dit issue wegneemt.
    """
    bron = (Path(__file__).resolve().parents[1]
            / "app/domains/payment/service.py").read_text()
    assert not re.search(r'€ \{[a-z_]+:\.2f\}', bron), (
        "er staat nog een handgeschreven bedrag in een melding")
