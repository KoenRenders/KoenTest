"""#762 — drie restpunten aan de Raakje-widget na #570.

**De welkomsttekst.** #570 zette de doorgeef-zin terug maar niet de begroeting, dus
de widget stelde zich niet voor. De emoji hoort erbij: #698 verbood losse tekens als
BESTURINGSELEMENT — een knop die per lettertype anders rendert — en in lopende tekst
is 👋 gewoon een woord. Koen heeft bevestigd dat dit de enige plek is waar het mag.

**Het stopvierkantje.** In dezelfde 24-eenhedendoos spant `mic` 20 eenheden (83%) en
`square` er 18 (75%), dus het vierkantje oogde kleiner dan de microfoon die het
vervangt. Zelfde klasse als #744: gelijke vakjes, ongelijk gevulde tekening.
`2 2 20 20` en niet de omhullende `3 3 18 18` — dat laatste is gerenderd en bekeken,
en toen domineerde het vierkant de microfoon. De getallen wezen de richting, het
beeld besliste.

Die waarde ligt hier vast om dezelfde reden als bij #744: een latere opruiming die
alles terugzet op `0 0 24 24` laat het verschil stil terugkeren.

**De derde melding — de knop bleef leeg na het stoppen — is NIET gereproduceerd.**
Gemeten met een nagebootst native pad, op `/raakje` én in de zwevende widget: de
knop gaat microfoon (361 tekens) → vierkant (292) → microfoon (361), en
`data-icon-idle` staat er de hele tijd op. De e2e hieronder legt dat gedrag vast, en
`stt.js` leest de iconen nu bij elke wissel opnieuw uit in plaats van ze bij het
laden vast te leggen — dat is de enige plausibele bron van een lege waarde die ik
kon bedenken.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: de begroeting weer
uit de tekst gehaald → de eerste test valt om; `viewboxes` leeggemaakt → de tweede.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_serverrendered

WIDGET = (Path(__file__).resolve().parents[1]
          / "app/domains/chatbot/templates/_raakje_widget.html").read_text()
MACROS = (Path(__file__).resolve().parents[1] / "app/ui/templates/_macros.html").read_text()


def test_de_widget_stelt_zich_voor():
    """Zonder begroeting begint het gesprek met een opdracht in plaats van een naam."""
    assert "Hallo, ik ben Raakje!" in WIDGET, "de begroeting ontbreekt"
    assert "👋" in WIDGET, "de emoji hoort bij de begroeting (lopende tekst, geen knop)"
    assert "doorgeven aan het bestuur" in WIDGET, (
        "de doorgeef-zin uit #570 mag niet sneuvelen — die vertelt dát dat kan")


def test_het_stopvierkantje_houdt_zijn_bijgesneden_viewbox():
    """Anders oogt het weer kleiner dan de microfoon die het vervangt."""
    assert '"square": "2 2 20 20"' in MACROS, (
        "de viewBox van `square` staat niet meer bijgesneden (#762)")


def test_de_andere_iconen_blijven_op_de_standaarddoos():
    """De tegenproef: dit is een uitzondering per icoon, geen nieuwe standaard.

    Zonder haar zou "geef alles een eigen viewBox" ook groen staan, en dan is de
    doos geen gedeelde maat meer.
    """
    blok = MACROS[MACROS.index("{%- set viewboxes"):]
    blok = blok[:blok.index("-%}")]
    assert blok.count(":") == 1, f"er staan meer uitzonderingen dan bedoeld: {blok}"
