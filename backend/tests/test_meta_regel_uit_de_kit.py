"""De meta-regel van Betalingen komt uit `ui.list_meta` (#1103).

Betalingen is het referentiescherm van §2.3 en schreef als enige nog zijn eigen
versie van een regel die de kit sinds #1083 levert. De opdracht was expliciet:
**er mag niets veranderen aan wat je ziet** — alleen de herkomst van de markup.

Daarom toetst dit bestand geen nieuw gedrag maar GELIJKWAARDIGHEID, en wel op de
enige manier die dat echt bewijst: de markup van vóór de wijziging staat hier
letterlijk, en de macro moet er byte voor byte hetzelfde uit produceren. Een test
die "er staat een meta-regel" toetst, zou ook groen blijven bij een regel die
anders oogt.

**Het meten kwam eerst en veranderde de uitkomst.** De macro droeg twee dingen die
de referentie niet had — `flex-wrap` op de buitenste div en
`flex items-center gap-2` op de rechter span. Bij een naïeve overzetting waren die
stilletjes op het referentiescherm beland. Gemeten bleken ze allebei inert (één
flex-item; en de rij past ook op 320px), dus is de MACRO naar de referentie
bewogen en niet omgekeerd.

Rood gemaakt om te bewijzen dat de vergelijking meet: `flex-wrap` teruggezet in
`list_meta` → `test_de_macro_rendert_exact_de_oude_markup` viel om met het
klassenverschil in de diff. Weggehaald → groen.
"""
import re
from pathlib import Path

import pytest

from app.ui import templates

pytestmark = pytest.mark.ui_serverrendered

BETALINGEN_LIJST = (Path(__file__).resolve().parents[1] / "app" / "domains"
                    / "payment" / "templates" / "_betalingen_lijst.html")

# De markup zoals ze vóór #1103 in `_betalingen_lijst.html` stond, letterlijk.
# Dit is het ijkpunt: niet "wat de macro nu doet", maar wat het scherm toonde.
OUDE_MARKUP = """\
<div class="my-2.5 flex items-center justify-between gap-3 text-[11px] text-ink-soft">
  <span>{{ records|length }} {{ _("boekingen") }} · {{ _("recentste eerst, gegroepeerd per inschrijving") }}</span>
  <span>EUR · {{ _("alleen FINANCE kan bevestigen") }}</span>
</div>"""

# Dezelfde regel, zoals het scherm hem sinds #1103 aanroept.
NIEUWE_AANROEP = """\
{% call ui.list_meta(_("%(aantal)s boekingen", aantal=records|length),
                     _("recentste eerst, gegroepeerd per inschrijving")) %}EUR · {{ _("alleen FINANCE kan bevestigen") }}{% endcall %}"""


def _render(body: str, **ctx) -> str:
    return templates.env.from_string(
        "{% import '_macros.html' as ui %}" + body).render(**ctx)


def test_de_macro_rendert_exact_de_oude_markup():
    """Byte voor byte, niet "ziet er hetzelfde uit".

    Met een echte telling, want `records|length` is het enige bewegende deel:
    staat er straks een vast getal in de macro, dan valt deze test om.
    """
    records = list(range(7))

    oud = _render(OUDE_MARKUP, records=records)
    nieuw = _render(NIEUWE_AANROEP, records=records)

    assert nieuw == oud, (
        "de macro-aanroep is niet gelijkwaardig aan de markup die ze vervangt:\n"
        f"  oud:    {oud!r}\n  nieuw:  {nieuw!r}")
    # En hij toetst echt iets: de telling staat er.
    assert "7 boekingen" in nieuw


def test_het_betalingenscherm_gebruikt_de_macro():
    """Zonder deze test bewijst de vergelijking hierboven niets OVER HET SCHERM:
    ze zou groen blijven terwijl het sjabloon zijn eigen kopie hield."""
    bron = BETALINGEN_LIJST.read_text()

    assert "ui.list_meta(" in bron, "Betalingen roept de kit-macro niet aan"
    assert 'flex items-center justify-between gap-3 text-[11px]' not in bron, \
        "de handgeschreven meta-regel staat er nog"


def test_de_kit_kent_de_meta_regel_maar_een_keer():
    """De reden dat dit issue bestond: dezelfde regel op twee plaatsen.

    Gezocht op de klassenreeks die de regel definieert — die hoort alleen nog in
    `_macros.html` te staan, en nergens in een scherm.

    Twee beweringen en niet één: nul treffers bewijst NIET dat de regel maar op
    één plek staat, het bewijst dat deze test niets meer vindt om naar te kijken
    (bijvoorbeeld omdat iemand de klassen herschikte). Dat is de absentie-valkuil,
    en zonder de eerste assertie zou ze hier als "te veel plekken: []" langskomen.
    """
    app = Path(__file__).resolve().parents[1] / "app"
    handtekening = "my-2.5 flex items-center justify-between gap-3"

    treffers = sorted(
        pad.relative_to(app) for pad in app.rglob("*.html")
        if handtekening in pad.read_text())

    assert treffers, (
        f"de klassenreeks {handtekening!r} komt nergens meer voor — deze test "
        "kijkt dus naar niets; pas de handtekening aan of herstel de macro")
    assert treffers == [Path("ui/templates/_macros.html")], (
        f"de meta-regel staat op meer dan één plek: {treffers}")
