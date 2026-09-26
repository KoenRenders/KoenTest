"""E2E #1197: de knop *AI · Betalingen* staat op één lijn met de filters.

Koen meldde op 26 september 2026 met een schermafdruk dat die knop hoger staat dan
het zoekveld, de statuskeuzelijst en *Export* op diezelfde regel.

**Heropend op 27 september 2026, en de reden staat in dit bestand.** De eerste
ronde haalde 12 px weg (zie hieronder) en liet de rest staan: de knop is 34 px
hoog, de controls 38, en de rij lijnt op de bovenkant. Dat gaf 2 px verschil — en
de assertie stond op *"binnen een pixel of twee"*, dus de suite keurde precies de
stand goed die Koen opnieuw zag. **Die tolerantie is weg.** Een knop is uitgelijnd
of hij is het niet; wat overblijft is een halve pixel voor afronding.

De tweede reparatie geeft de wrapper van de knop dezelfde hoogte als het formulier
(inclusief diens `mb-4`, want de wrapper draagt dezelfde marge) en centreert de
knop daarbinnen. Er staat dus nergens een hoogte: 38 px is de maat van een control
en die heeft één plek, de basislaag in `build-css.sh`. Afgeleid uit het formulier
kan ze niet verouderen. Gemeten na de reparatie op 1440 px: verschil **exact 0**.

Alleen vanaf `md`. Op 390 px is de knop juist HOGER dan de controls (44 tegen 38,
het aanraakvlak van #804) en wrapt de filterbalk tot 194 px; centreren zou de knop
dan midden in een blok van drie regels zetten. Die stand is ongewijzigd en is ook
nooit gemeld.

**De oorzaak is een andere dan uit de opmaak te lezen valt, en dat is de reden dat
deze test op twee schermen meet.** Het issue vermoedde ongelijke hoogtes bij
`items-start`. Nagemeten op 1440 px klopt dat niet:

| | `/admin/betalingen` | de activiteit-tab |
|---|---|---|
| formulier `#bt-filter` | top 395, hoogte 38 | top 456, hoogte **50** |
| controls-regel | top 395 | top **468** |
| zoekveld-midden | 414 | 487 |
| knop-midden | 412 (−2) | 473 (**−14**) |

Op het losse betalingenscherm is er niets aan de hand; het gebrek zit op de
**activiteit-tab**, en daar begint de controls-regel 12 px onder de bovenkant van
zijn eigen formulier. Dat is `space-y-3` op `filter_bar`: die zet `margin-top` op
elk kind behalve het eerste, en deze tab rendert **verborgen scope-inputs vóór**
de controls. Een `display:none`-element levert geen box op maar telt wél als
sibling, dus de controls-regel is `* + *` en krijgt 12 px mee. De knop lijnt met
`items-start` op het formulier, 12 px boven waar de controls echt beginnen; de
resterende 2 px is het hoogteverschil tussen knop (34) en veld (38).

14 = 12 + 2, en geen van beide getallen komt uit de `mb-4`.

**Daarom meet deze test op BEIDE schermen.** Alleen op `/admin/betalingen` stond
ze groen vóór de reparatie — dat is een test die niets bewijst, en precies de val
waar dit bestand tegen geschreven is.

De valkuil uit het issue blijft staan en is nagemeten: `items-center` op de
buitenste rij centreert de knop tegen het formulier **inclusief zijn `mb-4`**
(hoogte 38 + 16 = 54), en zet hem dan 8 px te laag. Daarom meet test 1 tegen het
ZOEKVELD en niet tegen het formulier, en daarom is de reparatie niet
`items-center`.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden. Drie proeven,
met wat er werkelijk omviel — niet met wat ik verwachtte:
- **de verborgen velden vóór de controls-div** (de toestand vóór de reparatie):
  2 failed, 4 passed. Beide uitlijningstests vielen op de **activiteit-tab**
  ("14 px hoger dan het zoekveld") en bleven groen op `/admin/betalingen`. Dat is
  ook het bewijs dat deze test op één scherm niets zou aantonen.
- **`items-start` → `items-center`** op de buitenste rij: 4 failed — béide
  uitlijningstests op béide schermen, telkens met de knop **8 px te laag**
  (`/admin/betalingen` 422 tegen 414; de tab 483 tegen 475). De val uit het issue,
  nu een meting.
- **de tweede reparatie teruggedraaid** (`md:items-stretch` en de
  `wrapper_cls` eruit): beide uitlijningstests vielen op **beide** schermen met
  "2 px hoger dan het zoekveld" — de stand die met de oude tolerantie groen
  stond, en nu niet meer.
- **`min-h-11` uit de `sm`-maat van de knopmacro gehaald** (dus de knop op de
  desktopmaat, ook op een telefoon): 1 failed, "het aanraakvlak is **42 px**,
  onder de 44 px van #804". Het moest deze weg en niet `size="md"`: die maat
  draagt `min-h-11` óók, dus daarmee zou de proef groen gebleven zijn en niets
  bewezen hebben.
"""
import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402
from tests_e2e.test_beheer_flows import _admin_email, _ontbreekt  # noqa: E402

KNOP = "AI · Betalingen"

# Géén tolerantie van twee pixels meer, en dat is de les van de heropening: met
# `<= 2` voldeed een knop die 2 px te hoog stond, en precies die stand meldde Koen
# opnieuw. Gemeten na de reparatie is het verschil EXACT 0 op 1440 px; een halve
# pixel absorbeert alleen afrondingen in de layout-engine en kan niets verbergen
# wat een mens ziet.
HALVE_PIXEL = 0.5

# De twee schermen die `_betalingen_scherm.html` renderen. Beide, en dat is het
# punt: alleen de tweede droeg het gebrek, dus met enkel de eerste bewijst deze
# test niets.
LOS = "/admin/betalingen"
TAB = "activiteit-tab"


@pytest.fixture(scope="module")
def browser_pagina():
    """Eigen browser: deze tests wisselen de vensterbreedte, en een gedeelde
    pagina zou die wijziging aan de volgende test doorgeven."""
    from app.domains.auth.api import make_session_value

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
        login_met_sessie(page, make_session_value(_admin_email()))
        yield page
        browser.close()


def _open(page, scherm: str, breedte: int = 1440):
    page.set_viewport_size({"width": breedte, "height": 900})
    if scherm == TAB:
        page.goto("/admin/activiteiten")
        pad = page.evaluate(
            r"""Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.getAttribute('href'))
                    .find(h => /^\/admin\/activiteiten\/\d+$/.test(h)) || null""")
        if not pad:
            _ontbreekt("geen activiteit om de Betalingen-tab van te openen")
        page.goto(f"{pad}/betalingen")
    else:
        page.goto(scherm)
    pagina_klaar(page)
    if page.get_by_role("button", name=KNOP).count() == 0:
        _ontbreekt(f"geen {KNOP}-knop op {scherm} — staat de beheer-assistent aan "
                   "(ADMIN_CHAT_ENABLED én de tenantschakelaar)?")
    return page.get_by_role("button", name=KNOP).first


def _midden(element, naam: str) -> float:
    doos = element.bounding_box()
    assert doos, f"{naam} is niet zichtbaar"
    return doos["y"] + doos["height"] / 2


def _controls(page):
    return {
        "zoekveld": page.locator("#bt-filter input[type=search]").first,
        "statuskeuzelijst": page.locator("#bt-filter select[name=status]").first,
        "Export": page.get_by_role("link", name="Export (.ods)").first,
    }


@pytest.mark.parametrize("scherm", [LOS, TAB])
def test_the_ai_button_shares_its_centre_with_the_search_field(browser_pagina, scherm):
    """Het gebrek dat Koen zag, in één maat: het verticale midden.

    Op `/admin/betalingen` stond dit vóór de reparatie al groen (−2 px); op de
    activiteit-tab was het −14 px. Die tweede is de meting die ertoe doet.
    """
    knop = _open(browser_pagina, scherm)
    midden_knop = _midden(knop, "de knop")
    midden_veld = _midden(_controls(browser_pagina)["zoekveld"], "het zoekveld")

    verschil = midden_knop - midden_veld
    assert abs(verschil) <= HALVE_PIXEL, (
        f"op {scherm} staat de knop {abs(verschil):.0f} px "
        f"{'hoger' if verschil < 0 else 'lager'} dan het zoekveld "
        f"(knopmidden {midden_knop:.0f} px, zoekveldmidden {midden_veld:.0f} px). "
        "Staat hij HOGER, dan zijn er twee oorzaken die dit issue al gehad heeft: "
        "een verborgen veld vóór de controls-div (`space-y-3` geeft de "
        "eerstvolgende zichtbare broer 12 px mee), of de knop die korter is dan "
        "een control (34 tegen 38) zonder dat zijn wrapper de hoogte van het "
        "formulier overneemt — dat laatste geeft precies 2 px. Staat hij LAGER, "
        "dan is hij tegen het formulier inclusief `mb-4` gecentreerd in plaats "
        "van tegen de regel controls; dat geeft 8 px (#1197).")


@pytest.mark.parametrize("scherm", [LOS, TAB])
def test_the_ai_button_lines_up_with_every_control_on_the_row(browser_pagina, scherm):
    """Niet alleen met het zoekveld: de hele regel hoort één lijn te zijn.

    Zonder deze test zou een reparatie die de knop aan het zoekveld gelijkstelt
    maar de keuzelijst laat afwijken, groen staan — en Koen noemde in zijn melding
    alle drie de elementen. Let op dat de statuskeuzelijst op de activiteit-tab
    aanwezig is en de contextkeuzelijst niet (`scope_stil`).
    """
    knop = _open(browser_pagina, scherm)
    midden_knop = _midden(knop, "de knop")

    gemeten, scheef = [], []
    for naam, element in _controls(browser_pagina).items():
        if element.count() == 0:
            continue
        verschil = midden_knop - _midden(element, naam)
        gemeten.append(naam)
        if abs(verschil) > HALVE_PIXEL:
            scheef.append(f"{naam}: {verschil:+.0f} px")

    assert len(gemeten) >= 2, (
        f"maar {len(gemeten)} control gevonden op {scherm} ({gemeten}) — dan meet "
        "deze test de regel niet")
    assert not scheef, (f"op {scherm} ligt de knop niet op één lijn met de regel: "
                        + ", ".join(scheef))


def test_the_touch_target_survives_on_a_phone(browser_pagina):
    """Op smal scherm is er geen gebrek en er mag er ook geen ontstaan.

    `size="sm"` draagt daar `min-h-11` — het aanraakvlak van 44 px uit #804. Een
    reparatie die de knop op de desktopmaat vastzet, zou dat wegnemen; dat is
    precies wat deze test tegenhoudt.
    """
    knop = _open(browser_pagina, TAB, breedte=390)
    doos = knop.bounding_box()

    assert doos, "de knop is op 390 px niet zichtbaar"
    assert doos["height"] >= 44, (
        f"het aanraakvlak is {doos['height']:.0f} px, onder de 44 px van #804")


def test_the_button_stays_outside_the_filter_form(browser_pagina):
    """De reparatie mag de nesting van #1115 niet terugbrengen.

    `filter_bar` rendert een `<form>` en de overlay brengt er zelf een mee; genest
    gooit de browser het binnenste weg, waarna *Vraag* bij de filterbalk hoort —
    die `onsubmit="return false"` draagt — en niets meer doet. Hier getoetst op de
    DOM-verhouding, want dát is de voorwaarde; dat *Vraag* werkt, bewaakt
    `test_raakje_overlay_op_betalingen.py`.
    """
    knop = _open(browser_pagina, TAB)
    expect(knop, "de knop is verdwenen").to_be_visible()

    binnen_de_balk = browser_pagina.evaluate(
        """() => {
            const knoppen = [...document.querySelectorAll('button')]
                .filter(b => b.textContent.includes('AI · Betalingen'));
            if (!knoppen.length) return null;
            return knoppen.some(b => b.closest('#bt-filter') !== null);
        }""")

    assert binnen_de_balk is not None, "geen AI-knop gevonden in de DOM"
    assert binnen_de_balk is False, (
        "de knop staat weer BINNEN de filterbalk — dan gooit de browser het "
        "geneste formulier weg en doet Vraag niets meer (#1115)")
