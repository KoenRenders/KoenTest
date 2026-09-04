"""Strikte templates: een onbestaande variabele is een fout, geen lege plek (#643).

In React ving TypeScript een verkeerde propnaam vóór de browser. Jinja rendert een
verkeerde variabelenaam standaard als lege string — daarom kon een route `totaal`
doorgeven terwijl de template `total` las, met alle tests groen en een leeg vak op
het scherm. Dat is de structurele oorzaak achter #613 en #616.

Twee dingen worden hier vastgelegd: dat de teststand strikt draait (anders bewijst
de hele suite niets over dit soort typo's) en dat autoescaping aan staat. Dat
laatste is geen detail: `Jinja2Templates` zet autoescape zelf wanneer je
`directory=` meegeeft, maar niet wanneer je een eigen `env=` meegeeft. Met de
overstap naar een eigen environment moest die vlag expliciet aan, en zonder deze
test zou het wegvallen ervan nergens opvallen — tot iemand een `<script>` in een
activiteitnaam zet.
"""
from pathlib import Path

import pytest
from jinja2 import StrictUndefined, UndefinedError

from app.ui import templates

APP = Path(__file__).resolve().parents[1] / "app"


def test_de_teststand_draait_strikt():
    assert templates.env.undefined is StrictUndefined, (
        "de testsuite draait niet strikt; typo's in templates blijven dan onzichtbaar")


def test_een_onbestaande_variabele_faalt():
    sjabloon = templates.env.from_string("{{ bestaat_niet }}")
    with pytest.raises(UndefinedError):
        sjabloon.render()


def test_een_optionele_variabele_mag_met_default():
    """De ontsnapping die wél mag: expliciet zeggen dat iets optioneel is."""
    assert templates.env.from_string("{{ misschien|default('-') }}").render() == "-"
    assert templates.env.from_string(
        "{% if misschien is defined %}x{% else %}-{% endif %}").render() == "-"


def test_autoescaping_staat_aan():
    """XSS-kritisch: met een eigen env zet Starlette autoescape niet meer zelf."""
    assert templates.env.autoescape is True
    uit = templates.env.from_string("{{ naam }}").render(naam="<script>alert(1)</script>")
    assert "<script>" not in uit and "&lt;script&gt;" in uit


def test_de_vlag_staat_letterlijk_in_de_opbouw():
    """Een gate-regel op de bron: wie de environment herschrijft, moet de vlag
    bewust overnemen i.p.v. hem stil te verliezen."""
    bron = (APP / "ui" / "__init__.py").read_text()
    assert "autoescape=True" in bron
