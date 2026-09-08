"""#735 — bedragen staan overal in nl-BE-notatie: `€ 35,00`, niet `€ 35.00`.

Het beheer schreef met een punt, de publieke site met een komma (`cms/render.py`
deed daar zijn eigen `.replace(".", ",")`). Die `.replace` is het bewijs dat de
komma de bedoeling was; ze was alleen op één plek gebeurd. En in het Nederlands is
de punt een duizendtalteken, dus `€ 1342.00` naast `€ 25,00` op hetzelfde scherm is
niet alleen inconsistent maar ook verkeerd te lezen.

**De uitzondering van #735 was te breed, en #769 heeft haar scherper gezet.** Toen
bleven de invoervelden met een punt staan omdat een komma in een `<input
type="number">` stilzwijgend leeg wordt. Dat klopt — maar gemeten is **geen enkel
bedragveld `type="number"`**: het zijn tekstvelden met `inputmode="decimal"`, en
beide parsers (`_ingetypt_bedrag`, `_decimal`) aanvaarden al komma én punt.

De regel luidt nu: een invoerveld volgt de notatie van het scherm, **tenzij** het
`type="number"` is. De laatste test bewaakt precies die voorwaarde — niet "deze twee
velden houden een punt", maar "geen bedragveld is een number-veld". Verandert dat,
dan valt ze om vóór er stilzwijgend een prijs verdwijnt.

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

    Sinds #769 zonder uitzondering: ook de invoervelden volgen de notatie van het
    scherm, want geen ervan is een `type="number"`-veld. Die voorwaarde staat als
    eigen test hieronder.
    """
    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(pad.read_text().splitlines(), 1):
            if '"%.2f"|format' not in regel:
                continue
            fouten.append(f"{pad.name}:{nr}: {regel.strip()[:100]}")
    assert not fouten, (
        "Bedragen horen door het `geld`-filter te gaan (#735):\n  " + "\n  ".join(fouten))


def test_geen_enkel_bedragveld_is_een_number_veld():
    """De voorwaarde onder de regel, en dus de plek waar het stil kan misgaan.

    Een komma in een `<input type="number">` is een ongeldige waarde: de browser
    toont het veld leeg en verstuurt niets. Zolang alle bedragvelden tekstvelden met
    `inputmode="decimal"` zijn, is de komma veilig — en die voorwaarde toetst deze
    test, niet de notatie zelf.
    """
    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(pad.read_text().splitlines(), 1):
            if 'inputmode="decimal"' in regel and 'type="number"' in regel:
                fouten.append(f"{pad.name}:{nr}")
    assert not fouten, (
        "een bedragveld is een number-veld geworden; een komma wordt daar "
        "stilzwijgend leeg (#769):\n  " + "\n  ".join(fouten))


def test_de_bedragvelden_volgen_de_notatie_van_het_scherm():
    """#769: vier plekken vulden een bedragveld nog met een punt.

    Twee daarvan vullen dezelfde Alpine-toestand — bij het renderen én via de
    statuskeuze die het veld met het volle bedrag vult. Wordt er maar één omgezet,
    dan toont hetzelfde veld twee schrijfwijzen naargelang hoe de waarde erin kwam.
    """
    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(pad.read_text().splitlines(), 1):
            if '"%.2f"|format' in regel or "'%.2f'|format" in regel:
                fouten.append(f"{pad.name}:{nr}: {regel.strip()[:90]}")
    assert not fouten, (
        "een bedrag wordt nog met de hand opgemaakt; gebruik het `geld`-filter "
        "(#735/#769):\n  " + "\n  ".join(fouten))


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
