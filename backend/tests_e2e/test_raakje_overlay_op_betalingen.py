"""E2E: de Raakje-overlay op Betalingen werkt en lijnt uit (#1115).

Koens twee waarnemingen, allebei uit één oorzaak — de overlay stond binnen de
filterbalk, en een `<form>` in een `<form>` gooit de browser weg:

1. *Vraag* deed niets. De submit-knop hoorde na dat weggooien bij de filterbalk,
   en die draagt `onsubmit="return false"`. Geen verzoek, geen fout, geen spoor.
2. De drie controls stonden niet op één lijn, want de opmaakklassen van de
   weggegooide vorm gingen mee.

**Alleen een browser ziet dit.** De servertest (`tests/test_geen_genest_formulier.py`)
bewijst dat er geen nesting meer in de uitvoer zit; dat de knop dáárdoor weer een
verzoek doet en dat veld, microfoon en knop op dezelfde onderrand eindigen, is
browsergedrag.

De tweede test hoort bij dezelfde wijziging: sinds de overlay overal dezelfde is,
kan één pagina er twee dragen — de Betalingen-tab van een activiteit toont Raakje
over de activiteit én over de selectie. Ze delen één voorleesstand, dus beide
knoppen horen die samen te tonen (`tts.js`).

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten): de
overlay-aanroep terug binnen `{% call ui.filter_bar %}` → test 1 valt om, want er
komt geen antwoord; de `paintAll()` in `tts.js` terug naar `paint()` → test 2 valt
om op de tweede knop.
"""
import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402
from tests_e2e.test_beheer_flows import _admin_email, _ontbreekt  # noqa: E402


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(base_url=BASE)
        yield p
        browser.close()


def _als_beheerder(page, pad: str):
    from app.domains.auth.api import make_session_value

    login_met_sessie(page, make_session_value(_admin_email()))
    page.goto(pad)
    pagina_klaar(page)


def _open_overlay(page, label: str):
    knop = page.get_by_role("button", name=label)
    if knop.count() == 0:
        _ontbreekt(f"geen {label}-knop — staat de beheer-assistent aan "
                   "(ADMIN_CHAT_ENABLED én de tenantschakelaar)?")
    knop.first.click()


def test_vraag_op_betalingen_levert_een_antwoord(page):
    _als_beheerder(page, "/admin/betalingen")
    _open_overlay(page, "AI · Betalingen")

    veld = page.locator("#bt-raakje-vraag")
    expect(veld, "de overlay ging niet open").to_be_visible()
    veld.fill("Hoeveel staat er open?")
    # `exact`: de microfoon ernaast heet "Spreek je vraag in" en matcht anders mee.
    page.get_by_role("button", name="Vraag", exact=True).click()

    # Het antwoord komt onderaan het gesprek. De mock-provider antwoordt zonder
    # netwerk, maar de lus doet er even over.
    antwoord = page.locator("#bt-raakje-gesprek [data-raakje-answer]")
    expect(antwoord.first,
           "Vraag leverde geen antwoord — doet de knop weer niets? (#1115)").to_be_visible(
        timeout=30000)


def test_de_drie_controls_eindigen_op_dezelfde_onderrand(page):
    _als_beheerder(page, "/admin/betalingen")
    _open_overlay(page, "AI · Betalingen")

    veld = page.locator("#bt-raakje-vraag")
    expect(veld).to_be_visible()
    mic = page.locator("[data-stt-target='#bt-raakje-vraag']")
    knop = page.get_by_role("button", name="Vraag", exact=True)

    onder = []
    for naam, element in (("veld", veld), ("microfoon", mic), ("knop", knop)):
        doos = element.bounding_box()
        assert doos, f"{naam} is niet zichtbaar"
        onder.append((naam, doos["y"] + doos["height"]))

    hoogste = min(y for _n, y in onder)
    laagste = max(y for _n, y in onder)
    assert laagste - hoogste <= 2, (
        "veld, microfoon en knop eindigen niet op dezelfde onderrand: "
        + ", ".join(f"{naam} {y:.0f}px" for naam, y in onder))


def _toggle_van(page, gesprek_id: str):
    """De voorleesknop van één overlay: de knop in de kop van díé modal."""
    modal = page.locator(f"#{gesprek_id}").locator("xpath=ancestor::div[@role='dialog']")
    return modal.locator("[data-tts-toggle]")


def test_twee_raakjes_op_een_pagina_delen_een_voorleesstand(page):
    """De Betalingen-tab van een activiteit draagt er twee (#1115).

    Het scenario is dat van een gebruiker: zet voorlezen aan in de ene overlay,
    sluit ze, open de andere — die hoort dezelfde stand te tonen. De knoppen zitten
    in de kop van hun modal en zijn dus alleen zichtbaar wanneer die open staat;
    daarom de omweg langs openen en sluiten in plaats van twee knoppen naast elkaar.
    """
    from tests_e2e.schermen import Activiteitdetail

    from app.domains.auth.api import make_session_value

    login_met_sessie(page, make_session_value(_admin_email()))
    if not Activiteitdetail(page).open_eerste():
        _ontbreekt("geen activiteit om te openen")
    # Rechtstreeks naar de tab en niet via een link met die naam: de linkerbalk
    # draagt óók een "Betalingen", en die staat eerder in de DOM.
    page.goto(page.url.split("?")[0].rstrip("/") + "/betalingen")
    pagina_klaar(page)

    if page.get_by_role("button", name="AI · Betalingen").count() == 0:
        _ontbreekt("deze pagina draagt geen twee Raakje-ingangen")

    _open_overlay(page, "AI · Activiteit")
    van_activiteit = _toggle_van(page, "aa-raakje-gesprek")
    expect(van_activiteit).to_be_visible()
    voor = van_activiteit.get_attribute("aria-pressed")
    van_activiteit.click()
    na = van_activiteit.get_attribute("aria-pressed")
    assert na != voor, "de aangeklikte knop wisselde niet van stand"
    page.keyboard.press("Escape")

    _open_overlay(page, "AI · Betalingen")
    van_betalingen = _toggle_van(page, "bt-raakje-gesprek")
    expect(van_betalingen).to_be_visible()
    assert van_betalingen.get_attribute("aria-pressed") == na, (
        "de tweede voorleesknop staat op de oude stand; één pagina, één stand (#1115)")
