"""De basisregel voor formuliercontrols moet Tailwinds preflight verslaan (#614).

`scripts/build-css.sh` geeft elk tekst-input/select/textarea één basisstijl (#482).
Met enkel `:where(...)` stond die op specificiteit 0,0,0 en verloor ze van preflight
(`button,input,optgroup,select,textarea{padding:0;font-size:100%}`, 0,0,1): rand en
radius kwamen door, padding en font-size niet — controls met een kader maar zonder
hoogte (#611).

De opmaak zelf toetsen we niet; wél de twee cascade-eigenschappen die stuk wáren en
die bij een volgende bewerking van build-css.sh makkelijk opnieuw sneuvelen.
"""

import pytest
pytestmark = pytest.mark.ui_serverrendered
import re
from pathlib import Path

APP_CSS = Path(__file__).resolve().parents[1] / "app" / "static" / "app.css"
BASIS = re.compile(r"html :where\(input\[type=[\"']?text[\"']?\][^{]*\)\{([^}]*)\}")
PREFLIGHT = "button,input,optgroup,select,textarea{"


def _css() -> str:
    return APP_CSS.read_text()


def test_de_basisregel_draagt_een_typeselector():
    """Zonder de `html `-prefix is de regel 0,0,0 en krachteloos tegen preflight."""
    css = _css()
    assert BASIS.search(css), (
        "De basisregel mist de `html `-prefix (of is verdwenen). Met enkel "
        ":where(...) verliest ze van preflight — zie #614."
    )


def test_de_basisregel_staat_na_preflight():
    """Bij gelijke specificiteit (0,0,1) beslist de volgorde."""
    css = _css()
    assert css.index(PREFLIGHT) < BASIS.search(css).start(), (
        "De basisregel staat vóór preflight; bij gelijke specificiteit wint dan "
        "preflight en is padding/font-size opnieuw weg."
    )


def test_de_regel_zet_de_eigenschappen_die_preflight_afpakte():
    """padding en font-size zijn precies wat preflight overschreef."""
    inhoud = BASIS.search(_css()).group(1)
    assert "padding:" in inhoud and "font-size:" in inhoud


def test_utilities_blijven_winnen():
    """De hele reden voor :where(): een scherm dat bewust afwijkt (px-2, w-28)
    moet de basisregel kunnen overschrijven. Een utility is 0,1,0 en verslaat de
    0,0,1 van `html :where(...)`; een kale `input[type=text]`-selector zou 0,1,1
    zijn en die utility juist verslaan."""
    css = _css()
    selector = BASIS.search(css).group(0).split("{")[0]
    assert ":where(" in selector, (
        "De selector staat niet meer in :where() — dan is hij 0,1,1 en verslaat "
        "hij .px-2 (0,1,0), precies wat we niet willen."
    )
    assert ".px-2{" in css
