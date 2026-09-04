"""Template-variabelen-gate (#643 E): het `tsc --noEmit` van deze stack.

Jinja controleert niets vooraf. Een template die `totaal` leest terwijl de route
`total` doorgeeft, faalt pas bij het renderen — en alleen als er een test langs dat
scherm komt. Deze gate bewijst statisch, per (template, view-model), dat de
template niets vraagt wat het view-model niet belooft.

`jinja2.meta.find_undeclared_variables` werkt per bronbestand: variabelen uit een
`{% extends %}`-schil of een `{% include %}` zitten er niet bij. Fragmenten staan
daarom **apart** in het register — wat sowieso beter is, want juist een fragment
wordt vanuit meerdere routes gerenderd.

Het register groeit met elk scherm dat op een view-model overgaat (#635 raakt die
routes toch). Een scherm dat er nog niet in staat, wordt hier niet gecontroleerd;
dat is zichtbaar aan de lengte van dit register.
"""
import pytest
from jinja2 import meta

from app.domains.payment.viewmodels import BetalingenView
from app.ui import templates

pytestmark = pytest.mark.ui_serverrendered

# (template, view-model). Eén regel per omgezet scherm.
VIEWMODELS = {
    "betalingen.html": BetalingenView,
    "_betalingen_lijst.html": BetalingenView,
}

# Namen die niet uit het view-model komen maar altijd bestaan:
#  - de env-globals (`_`, `omgeving`, `confirm_attrs`, `css_version`, …),
#  - `request`, dat Starlette zelf in elke context zet,
#  - `ui`, de macro-import bovenaan elke template,
#  - `caller`, dat Jinja binnen een {% call %} zelf levert.
ALTIJD_BESCHIKBAAR = set(templates.env.globals) | {"request", "ui", "caller"}


def _toegewezen_namen(boom) -> set[str]:
    """Namen die de template zichzelf geeft met `{% set %}`.

    `find_undeclared_variables` telt die mee zodra de toewijzing binnen een `{% if %}`
    of `{% for %}` staat: Jinja kan dan niet bewijzen dat de naam op elk pad bestaat.
    Voor deze gate zijn het geen ontbrekende velden — de template maakt ze zelf.
    """
    from jinja2 import nodes

    namen: set[str] = set()
    for soort in (nodes.Assign, nodes.AssignBlock):
        for knoop in boom.find_all(soort):
            doel = knoop.target
            if isinstance(doel, nodes.Name):
                namen.add(doel.name)
            elif isinstance(doel, nodes.Tuple):
                namen.update(item.name for item in doel.items
                             if isinstance(item, nodes.Name))
    return namen


def _gevraagde_namen(bestandsnaam: str) -> set[str]:
    bron = templates.env.loader.get_source(templates.env, bestandsnaam)[0]
    boom = templates.env.parse(bron)
    return meta.find_undeclared_variables(boom) - _toegewezen_namen(boom)


@pytest.mark.parametrize("bestandsnaam,model", sorted(
    VIEWMODELS.items(), key=lambda kv: kv[0]))
def test_de_template_vraagt_niets_wat_het_view_model_niet_belooft(bestandsnaam, model):
    from dataclasses import fields

    beloofd = {veld.name for veld in fields(model)} | ALTIJD_BESCHIKBAAR
    gevraagd = _gevraagde_namen(bestandsnaam)

    ontbreekt = gevraagd - beloofd
    assert not ontbreekt, (
        f"{bestandsnaam} gebruikt {sorted(ontbreekt)}, maar {model.__name__} heeft "
        f"dat niet. Zet het veld in het view-model, of gebruik |default(...) met "
        f"een reden als het echt optioneel is."
    )


def test_het_register_dekt_beide_kanten_van_het_betalingenscherm():
    """De pagina én haar fragment: het fragment wordt los gerenderd bij zoeken en
    filteren, en juist dáár ontbrak vroeger een variabele (#617)."""
    assert "betalingen.html" in VIEWMODELS
    assert "_betalingen_lijst.html" in VIEWMODELS
