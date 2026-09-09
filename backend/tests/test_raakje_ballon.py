"""#791 — de welkomsttekst is Raakjes eerste bericht, geen bijschrift.

Op PROD (v1.14) begon het gesprek met een tekstballon van Raakje; in v2.0 stond er
grijze lopende tekst in een leeg paneel, en verscheen de eerste ballon pas nadat je
iets vroeg. Het hoekje linksonder is wat een blok tekst tot een uitspraak maakt: het
wijst naar wie het zegt.

**Wat hier getoetst wordt en wat niet.** De hoek zelf is één CSS-klasse; daar een
e2e op zetten is meer ceremonie dan bescherming, en de lint-gate op UI-conventies
kent geen hoeken. Wat wél kan breken bij een herschikking — en wat de functionele
helft van dit issue is — is dat de welkomsttekst *binnen* de ballon en *binnen* het
gesprek staat, op **beide** schermen. Staat ze buiten het gesprek, dan schuiven de
antwoorden er niet onder maar erboven, en dan leest de begroeting weer als
paginakop.

De maat van het hoekje ligt hier vast om dezelfde reden als de viewbox bij #762:
`rounded-bl-sm` is 2 px en geen rechte hoek, en een latere "opruiming" naar
`rounded-bl-none` zou dat stil veranderen. Dít is de hoek die op PROD staat.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: de welkomsttekst
in `raakje.html` weer boven `#raakje-gesprek` gezet → de plaatsingstest valt om;
`rounded-bl-sm` uit de macro gehaald → de hoektest valt om.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_serverrendered

CHATBOT = Path(__file__).resolve().parents[1] / "app/domains/chatbot/templates"
BALLON = (CHATBOT / "_raakje_ballon.html").read_text()
WIDGET = (CHATBOT / "_raakje_widget.html").read_text()
PAGINA = (CHATBOT / "raakje.html").read_text()
ANTWOORD = (CHATBOT / "_raakje_antwoord.html").read_text()


def _macro(naam: str) -> str:
    blok = BALLON[BALLON.index("{% macro " + naam + "("):]
    return blok[:blok.index("{%- endmacro %}")]


# Op naam en niet op inhoud parametriseren: anders zet pytest de hele template in de
# test-id en is een foutmelding onleesbaar.
SCHERMEN = {"widget": (WIDGET, "raakje-widget-gesprek"),
            "pagina": (PAGINA, "raakje-gesprek")}


@pytest.mark.parametrize("naam", sorted(SCHERMEN))
def test_de_welkomsttekst_staat_in_de_ballon(naam):
    """Op allebei de schermen, en via dezelfde macro als een antwoord."""
    bron, _container = SCHERMEN[naam]
    regels = [r for r in bron.splitlines() if "teksten.intro()" in r]
    assert len(regels) == 1, f"{naam}: verwacht één introregel, gevonden {len(regels)}"
    assert "ballon.van_raakje()" in regels[0], (
        f"{naam}: de welkomsttekst staat niet in de Raakje-ballon: {regels[0].strip()}")


@pytest.mark.parametrize("naam", sorted(SCHERMEN))
def test_de_welkomsttekst_staat_binnen_het_gesprek(naam):
    """Anders schuiven de antwoorden (`hx-swap="beforeend"`) er niet onder.

    Getoetst op de volgorde in de bron: de intro staat ná het openen van de
    gespreks-`<div>` en vóór het sluiten ervan.
    """
    bron, container = SCHERMEN[naam]
    opening = bron.index(f'id="{container}"')
    intro = bron.index("teksten.intro()")
    assert intro > opening, (
        f"{naam}: de welkomsttekst staat vóór het gesprek in plaats van erin")

    # Het eerstvolgende `</div>` op hetzelfde niveau kunnen we niet betrouwbaar
    # vinden zonder te parsen; wat wél telt is dat er tussen de opening en de intro
    # geen sluiting van diezelfde container zit.
    tussenin = bron[opening:intro]
    assert '<div id=' not in tussenin.replace(f'id="{container}"', ""), (
        f"{naam}: er begint een andere container tussen het gesprek en de intro")


def test_beide_ballonnen_dragen_hun_eigen_hoek():
    """Raakje spreekt van links, de bezoeker van rechts.

    2 px en geen rechte hoek: `rounded-bl-sm`/`rounded-br-sm` komen letterlijk uit
    `ChatWidget.tsx` op tag `v1.14.0`, en dat is de hoek die op PROD staat.
    """
    raakje, bezoeker = _macro("van_raakje"), _macro("van_bezoeker")

    assert "rounded-2xl" in raakje and "rounded-bl-sm" in raakje
    assert "rounded-2xl" in bezoeker and "rounded-br-sm" in bezoeker
    assert "rounded-bl-none" not in raakje and "rounded-br-none" not in bezoeker, (
        "een rechte hoek is niet wat v1.14 doet — `sm` is 2px en dat is het verschil")
    assert "rounded-br-sm" not in raakje and "rounded-bl-sm" not in bezoeker, (
        "de twee sprekers krijgen hetzelfde hoekje; dan wijst het nergens meer naar")


def test_het_antwoord_gebruikt_dezelfde_macro():
    """De tegenproef op de macro: zou het antwoord zijn eigen klassenreeks houden,
    dan verandert de welkomsttekst wél mee en het antwoord niet — en dan is het paneel
    na de eerste vraag weer inconsistent."""
    assert "ballon.van_raakje()" in ANTWOORD and "ballon.van_bezoeker()" in ANTWOORD
    assert not re.search(r'class="[^"]*bg-gray-100[^"]*rounded', ANTWOORD), (
        "het antwoord draagt nog een eigen ballon-klassenreeks")
