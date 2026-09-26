"""E2E #1200 — de teller knipt niets meer af en is lichter op desktop.

Koen meldde vier punten op `ui.stepper` (#1171) na zijn HDEV-ronde. Twee zijn
fouten — de `+` werd afgeknipt en de ingebouwde pijltjes stonden er nog bij — en
twee zijn opmaak: drie kaders waar er één volstaat, en te zwaar op een desktop.

**Twee dingen uit de meting die het issue anders inschatte. Ze bepalen allebei
hoe deze tests eruitzien.**

**1. Klikken is het verkeerde meetinstrument.** De eerste versie van deze test
klikte op de `+` en keek of het aantal klom. Dat slaagde óók met de reparatie
eruit — gemeten: zonder `shrink-0` is de doos op 390 px **20 px** breed terwijl
haar knoppen tot x=379 doorlopen, en de klik gaf nog steeds 1 → 2. De reden is
`overflow-hidden`: dat maakt van de doos een scrollcontainer, en Playwright
scrollt een element daarbinnen netjes in beeld vóór het klikt. **Een mens kan dat
niet** — er is geen scrollbalk en geen scrollbare richting. Deze tests meten
daarom of de knoppen *binnen hun doos liggen*, niet of een robot ze kan raken.

**2. Een lange productnaam, en niet die van Koen.** Zijn geval was *"aantal
deelnemers — ter plaatse te betalen (eigen budget)"*, en dat knipte af zolang de
teller 144 px breed was (44 + 56 + 44). Punt 4 brengt die op desktop naar 120, en
dáármee past zijn tekst ook zónder `shrink-0`. Een test op zijn eigen zin zou dus
groen staan met de belangrijkste reparatie eruit. De fixture gebruikt daarom een
lange onbreekbare productnaam: die knijpt de doos wél, en dan bijt de tegenproef.

Dat de teller na een klik het **totaal** laat meebewegen — de val van #1171 — is
niet hier getest maar in `test_inschrijf_teller.py`, waar die keten al bewaakt
wordt. Een tweede kopie zou uit de pas lopen met de eerste.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
- **`shrink-0` van de buitenste doos gehaald**: op 1440 px valt de `−` links
  buiten de doos (knop 803–839, doos 850–924) en op 390 px vallen ze allebei
  erbuiten (doos 334–354, knoppen tot 379). Test 1 valt om op beide breedtes.
- **de `.teller-veld`-regel uit build-css.sh gehaald** en de css herbouwd: de
  browser meldt `appearance: auto` in plaats van `textfield` — test 2 valt om.
- **`border-0` van het veld gehaald**: de basislaag zet dan haar eigen
  `border:1px solid` terug en test 4 meet 1px in plaats van 0px.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE  # noqa: E402

BREED, SMAL = 1440, 390
MIN_RAAKVLAK = 44          # #804, en de reden dat deze teller bestaat
DESKTOP_HOOGTE = 36        # punt 4: lichter zodra er een muis is

# Eén lang, onbreekbaar woord. Zie de kop: Koens eigen zin knijpt de doos niet
# meer zodra de desktopmaat gedaald is, en dan bewijst de tegenproef niets.
LANGE_NAAM = "deelnemersaantalvoorhetavondprogramma"

METING = """() => {
  const veld = document.querySelector("input[name^='product_']");
  if (!veld) return null;
  const doos = veld.parentElement;
  const knoppen = [...doos.querySelectorAll('button')];
  const d = doos.getBoundingClientRect();
  const buiten = knoppen.map(k => {
    const a = k.getBoundingClientRect();
    // Een halve pixel speling: de rand van de doos telt mee in haar rechthoek.
    const links = Math.round(d.left - a.left), rechts = Math.round(a.right - d.right);
    return {label: k.getAttribute('aria-label'),
            breedte: Math.round(a.width), hoogte: Math.round(a.height),
            steekt_links_uit: links > 1 ? links : 0,
            steekt_rechts_uit: rechts > 1 ? rechts : 0};
  });
  const stijl = getComputedStyle(veld);
  return {
    knoppen: buiten,
    doos: {breedte: Math.round(d.width), inhoud: doos.scrollWidth,
           zichtbaar: doos.clientWidth},
    veld: {breedte: Math.round(veld.getBoundingClientRect().width),
           hoogte: Math.round(veld.getBoundingClientRect().height)},
    randen: ['Top', 'Right', 'Bottom', 'Left']
        .map(z => stijl['border' + z + 'Width']),
    appearance: stijl.appearance,
    spin_binnen: getComputedStyle(veld, '::-webkit-inner-spin-button').appearance,
    spin_buiten: getComputedStyle(veld, '::-webkit-outer-spin-button').appearance,
  };
}"""


@pytest.fixture(scope="module")
def lange_naam():
    """Een eigen activiteit met één product met een lange, onbreekbare naam.

    Eigen en niet de gedeelde seed, om dezelfde reden als
    `test_inschrijf_teller.py`: in CI draait de hele suite tegen één databank en
    zetten andere tests er activiteiten bij, dus selecteren op volgorde is
    onbetrouwbaar. Hier selecteren we op de `hx-get` van precies dit onderdeel.
    """
    from datetime import date, timedelta
    from decimal import Decimal

    import app.models  # noqa: F401  configureert alle mappers
    from app.database import SessionLocal
    from app.domains.activities.api import (Activity, ActivityDate,
                                            ActivityProduct,
                                            ActivitySubRegistration)

    db = SessionLocal()
    activiteit = Activity(name="E2E Teller met lange naam")
    db.add(activiteit)
    db.flush()
    db.add(ActivityDate(activity_id=activiteit.id,
                        start_date=date.today() + timedelta(days=30)))
    onderdeel = ActivitySubRegistration(activity_id=activiteit.id, name="Deelname",
                                        price=Decimal("0"), is_free=True)
    db.add(onderdeel)
    db.flush()
    # `pay_on_site`: dat geeft het langste bijschrift naast de naam, en zo zag
    # Koens geval eruit.
    db.add(ActivityProduct(component_id=onderdeel.id, name=LANGE_NAAM,
                           price=Decimal("0"), is_free=False, pay_on_site=True))
    db.commit()
    ids = (activiteit.id, onderdeel.id)
    db.close()
    return ids


def _meet(lange_naam, breedte: int) -> dict:
    activiteit_id, onderdeel_id = lange_naam
    exe = os.environ.get("E2E_CHROMIUM_PATH")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": breedte, "height": 900})
        page.goto("/activiteiten")
        page.click(
            f'button[hx-get="/activiteiten/{activiteit_id}/inschrijven/{onderdeel_id}"]')
        page.wait_for_selector("input[name^='product_']", timeout=10_000)
        stand = page.evaluate(METING)
        browser.close()
    assert stand is not None, "geen tellerveld op het inschrijfformulier"
    assert len(stand["knoppen"]) == 2, f"twee tellerknoppen verwacht: {stand['knoppen']}"
    return stand


# ── 1. Niets wordt nog afgeknipt ────────────────────────────────────────────

@pytest.mark.parametrize("breedte", [BREED, SMAL])
def test_both_buttons_lie_inside_their_box(lange_naam, breedte):
    """De belangrijkste test: wat buiten de doos valt, is voor een mens weg.

    Gemeten, niet geklikt — zie de kop van dit bestand voor waarom een klik hier
    niets bewijst.
    """
    stand = _meet(lange_naam, breedte)

    afgeknipt = [k for k in stand["knoppen"]
                 if k["steekt_links_uit"] or k["steekt_rechts_uit"]]
    assert not afgeknipt, (
        f"op {breedte} px valt er een knop buiten de teller: {afgeknipt} — de doos "
        f"is {stand['doos']['breedte']} px en draagt `overflow-hidden`, dus wat "
        "erbuiten valt is onzichtbaar en onbereikbaar (#1200 punt 1)")
    assert stand["doos"]["inhoud"] <= stand["doos"]["zichtbaar"] + 1, (
        f"op {breedte} px loopt de teller over: inhoud {stand['doos']['inhoud']} px "
        f"in een zichtbare breedte van {stand['doos']['zichtbaar']} px")


# ── 2. Geen tweede bediening ────────────────────────────────────────────────

def test_the_number_field_shows_no_native_arrows(lange_naam):
    """De teller bestaat omdat iOS Safari die pijltjes nooit toont; op een
    desktop stonden er dan twee bedieningen voor hetzelfde ding.

    Gemeten op de computed style van het veld én van de twee spin-pseudo-elementen.
    Een pixelmeting kan niet: de spinknop leeft in de shadow-DOM en heeft geen
    bereikbare geometrie. `auto` is de stand mét pijltjes, `textfield` die zonder —
    nagemeten door de regel uit build-css.sh te halen.
    """
    stand = _meet(lange_naam, BREED)

    assert stand["appearance"] == "textfield", (
        f"het getalveld staat op appearance {stand['appearance']!r}; met `auto` "
        "toont een desktopbrowser zijn eigen pijltjes naast onze − en + "
        "(#1200 punt 2)")
    for naam, waarde in (("inner", stand["spin_binnen"]),
                         ("outer", stand["spin_buiten"])):
        assert waarde != "auto", (
            f"de {naam} spin-button staat nog op {waarde!r}")


# ── 3. Eén kader, niet drie ─────────────────────────────────────────────────

def test_the_field_has_no_border_of_its_own(lange_naam):
    """Koen: *"die − + knoppen en dan nog een kader rond het getal (vooral dit)
    wel heel zwaar"*. De doos heeft een rand; het veld erbinnen hoort er geen te
    hebben.

    Let op waaróm `border-0` er expliciet staat: de basislaag in build-css.sh zet
    op élke `type=number` een volledige `border:1px solid`. Alleen `border-x`
    weglaten zou dus VIER randen geven in plaats van twee.
    """
    stand = _meet(lange_naam, BREED)

    assert stand["randen"] == ["0px"] * 4, (
        f"het getalveld draagt nog een eigen rand: {stand['randen']} "
        "(boven/rechts/onder/links)")


# ── 4. Lichter op desktop, ongewijzigd op een telefoon ──────────────────────

def test_the_touch_target_stays_44_on_a_phone(lange_naam):
    """De ondergrens voor een vinger (#804) — en de hele reden dat deze teller
    bestaat. Een opmaakronde mag hem niet meenemen."""
    stand = _meet(lange_naam, SMAL)

    for knop in stand["knoppen"]:
        assert knop["breedte"] >= MIN_RAAKVLAK and knop["hoogte"] >= MIN_RAAKVLAK, (
            f"knop {knop['label']!r} meet {knop['breedte']}×{knop['hoogte']} px, "
            f"minimaal {MIN_RAAKVLAK} px (#804)")


def test_the_stepper_is_lighter_on_a_desktop(lange_naam):
    """Punt 4. De maat zakt naar ~36 px zodra er een muis is; dat scheelt op een
    regel met een productnaam en een prijs ernaast.

    Samen met de vorige test is dit het paar dat telt: één maat alleen zou je
    kunnen halen door overal te verkleinen, en dan sneuvelt het aanraakvlak.
    """
    stand = _meet(lange_naam, BREED)

    for knop in stand["knoppen"]:
        assert knop["hoogte"] == DESKTOP_HOOGTE, (
            f"knop {knop['label']!r} is {knop['hoogte']} px hoog op een desktop, "
            f"verwacht {DESKTOP_HOOGTE}")
    assert stand["veld"]["hoogte"] == DESKTOP_HOOGTE, (
        f"het getalveld is {stand['veld']['hoogte']} px hoog, verwacht "
        f"{DESKTOP_HOOGTE}")
    assert stand["doos"]["breedte"] < 144, (
        f"de teller is {stand['doos']['breedte']} px breed; op een desktop hoort "
        "hij smaller te zijn dan de 144 px van vóór dit issue")
