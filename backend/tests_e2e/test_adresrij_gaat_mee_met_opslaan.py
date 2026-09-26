"""E2E #1223 — de e-mailrij gaat écht mee met Opslaan.

**Dit is de test die #1219 had moeten hebben.** Koen op HDEV: *"Als ik een
mailadres toevoeg met + E-mailadres komt die regel er, ik druk op opslaan en
toch is het er niet."*

De oorzaak was structureel: het adressenblok staat BUITEN het `<form>` van het
lid — het moet wel, want de twee knoppen ernaast sturen hun eigen htmx-verzoek
en een genest formulier bestaat niet in HTML. Zonder `form="<id>"` op de velden
stuurt de browser ze dus niet mee.

**Waarom mijn tests bij #1219 dat niet zagen, en dat is het deel dat telt.** Ze
posten de velden rechtstreeks naar de route. De ene bewees dat de service de
velden juist verwerkt, de andere dat het veld op het scherm staat. Geen van
beide bewijst dat de BROWSER het veld verstuurt — precies de vorm waar
`CLAUDE.md` voor waarschuwt: een test die het onderwerp omzeilt, blijft groen
als je de bedrading weghaalt.

Deze test doet wat de pagina doet: typen in het veld, op Opslaan klikken, en
kijken wat er daarna op het scherm staat. Hij kan dus niet groen blijven met een
veld dat nergens aan hangt.

Kapotgemaakt om te controleren dat hij rood kan worden: `form="<id>"` weer van
het veld gehaald → het nieuwe adres verschijnt niet na het opslaan, en de test
faalt op precies de zin die Koen meldde.
"""
import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie  # noqa: E402

NIEUW = "erbij@example.com"


def _ontbreekt(reden: str) -> None:
    if os.environ.get("E2E_SEEDED") == "1":
        pytest.fail(f"e2e-seed geladen maar: {reden}")
    pytest.skip(reden)


@pytest.fixture(scope="module")
def admin_page():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
        login_met_sessie(page, make_session_value(email))
        yield page
        browser.close()


def _maak_de_verplichte_velden_geldig(page):
    """Vul wat het formulier eist, zodat de browser mag versturen.

    Gemeten toen deze test op nul POSTs bleef staan: de seed-persoon draagt geen
    geboortedatum, geen geslacht en geen gsm, en die drie zijn `required`. De
    browser blokkeert dan de submit — geen verzoek, geen foutmelding, niets. Dat
    leek op de bug die deze test moet vangen en was het niet, en zonder deze
    regels zou de test dus altijd rood staan om de verkeerde reden.
    """
    page.fill("input[name='date_of_birth']", "1980-01-01")
    page.select_option("select[name='gender_code']", "M")
    page.fill("input[name='mobile']", "0470000000")


def _open_het_eerste_gezin(page):
    page.goto("/admin/leden")
    # Op de href en niet op een knoplabel: de lijst linkt met
    # `/admin/leden/gezin/<id>`, en dat adres verandert niet met de opmaak.
    link = page.locator('a[href^="/admin/leden/gezin/"]').first
    link.wait_for(state="visible", timeout=10_000)
    page.goto(link.get_attribute("href"))
    # Op de KNOP en niet op de tekst: "bewerken" staat ook in een verborgen span
    # ("<naam> — bewerken") die bij een tekstzoekopdracht als eerste opduikt.
    knop = page.get_by_role("button", name="Bewerken").first
    knop.wait_for(state="visible", timeout=10_000)
    return knop


def test_een_toegevoegde_rij_overleeft_het_opslaan(admin_page):
    page = admin_page
    _open_het_eerste_gezin(page).click()
    page.locator("input[name^='email_existing_'], button:has-text('+ E-mailadres')").first.wait_for(
        state="visible", timeout=5_000)

    page.get_by_role("button", name="+ E-mailadres").first.click()
    veld = page.locator("input[name^='email_new_']").first
    veld.wait_for(state="visible", timeout=5_000)

    # De kern: het veld moet BIJ een formulier horen, anders verstuurt de browser
    # het niet. Op `el.form` en niet op het `form`-attribuut, want er zijn twee
    # wegen die allebei werken — erin staan, of ernaar verwijzen — en de eis is
    # dat er één van de twee geldt. Dit veld staat in de bewerkvorm van het lid.
    assert veld.evaluate("el => el.form ? el.form.id : null"), (
        "het veld hoort bij geen enkel formulier — de browser stuurt het dan niet "
        "mee met Opslaan, en dat is precies wat er op HDEV misging")

    veld.fill(NIEUW)
    _maak_de_verplichte_velden_geldig(page)
    page.get_by_role("button", name="Opslaan").first.click()
    page.wait_for_function(
        "() => !document.querySelector('.htmx-request, .htmx-swapping, .htmx-settling')",
        timeout=10_000)

    # Na het opslaan staat de kaart weer in leesmodus, en die toont alleen het
    # hoofdadres. Kijken dus zoals Koen keek: opnieuw Bewerken, en staat de rij
    # er? Dat is ook het antwoord op zijn zin "toch is het er niet".
    _open_het_eerste_gezin(page).click()
    rij = page.locator(f"input[value='{NIEUW}']").first
    expect(rij).to_have_count(1, timeout=10_000)


def test_een_gecorrigeerde_tikfout_overleeft_het_opslaan(admin_page):
    """Punt 1 van #1219, langs het echte pad.

    Het adres uit de vorige test staat er nu; dat typen we over. Een tikfout
    corrigeren is de vraag waar #1219 mee begon, en ze liep op hetzelfde gebrek
    stuk: zonder `form=` gaat ook een gewijzigde bestaande rij niet mee.
    """
    page = admin_page
    _open_het_eerste_gezin(page).click()
    page.locator("input[name^='email_existing_'], button:has-text('+ E-mailadres')").first.wait_for(
        state="visible", timeout=5_000)

    veld = page.locator(f"input[value='{NIEUW}']").first
    if veld.count() == 0:
        _ontbreekt(f"{NIEUW} staat niet op de kaart; de vorige test moet eerst slagen")
    assert veld.evaluate("el => el.form ? el.form.id : null"), (
        "ook een bestaande rij hoort bij geen enkel formulier")

    verbeterd = "verbeterd@example.com"
    veld.fill(verbeterd)
    _maak_de_verplichte_velden_geldig(page)
    page.get_by_role("button", name="Opslaan").first.click()
    page.wait_for_function(
        "() => !document.querySelector('.htmx-request, .htmx-swapping, .htmx-settling')",
        timeout=10_000)

    _open_het_eerste_gezin(page).click()
    expect(page.locator(f"input[value='{verbeterd}']").first).to_have_count(
        1, timeout=10_000)
