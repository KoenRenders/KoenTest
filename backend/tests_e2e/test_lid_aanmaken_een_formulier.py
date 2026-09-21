"""E2E: een lid aanmaken is één formulier met één opslaan-actie (#1110).

De servertests bewijzen wat er na één POST in de databank staat. Wat alleen een
browser kan tonen: dat het scherm ook écht één formulier is — een gezinslid
erbij haalt een lege rij op zonder iets te bewaren en zonder iets te vervangen,
en pas Opslaan schrijft, waarna je op de gezinspagina staat. Dat was de klacht:
tot #1110 waren het vier opslag-acties, en elke deelactie kon je typwerk wissen.

Kapotgemaakt om te controleren dat deze test rood kan worden (gemeten): de
`hx-get` van de "+ Gezinslid toevoegen"-knop weggehaald → de knop start geen
verzoek meer, dus `htmx_afgerond` wacht tevergeefs en de test valt om in die
wachtvoorwaarde, nog vóór de assertie op `m1_first_name`. Beide zijn hetzelfde
gebrek: er komt geen tweede rij.
"""
import os
import sys
import time

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, login_met_sessie, pagina_klaar  # noqa: E402
from tests_e2e.test_beheer_flows import _admin_email, _ontbreekt  # noqa: E402


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(base_url=BASE)
        yield p
        browser.close()


def test_hoofdlid_en_gezinslid_in_een_keer_bewaard(page):
    from app.domains.auth.api import make_session_value

    login_met_sessie(page, make_session_value(_admin_email()))
    page.goto("/admin/leden/nieuw")
    pagina_klaar(page)

    achternaam = f"E2E{int(time.time())}"
    page.fill("#m0_first_name", "Hoofd")
    page.fill("#m0_last_name", achternaam)
    page.fill("#m0_date_of_birth", "1980-01-01")
    page.select_option("#m0_gender_code", index=1)
    page.fill("#m0_email", "e2e-nieuwlid@example.com")
    page.fill("#m0_mobile", "0470000000")
    page.fill("#street", "Teststraat")
    page.fill("#house_number", "1")

    postcode = page.locator("#postal_code")
    if postcode.locator("option").count() < 2:
        _ontbreekt("geen postcode in de keuzelijst")
    postcode.select_option(index=1)

    # Een gezinslid erbij: een lege rij, geen opslag — wat hierboven staat blijft.
    with htmx_afgerond(page):
        page.get_by_role("button", name="+ Gezinslid toevoegen").click()
    expect(page.locator("#m1_first_name"),
           "de tweede persoonsrij kwam niet").to_be_visible()
    expect(page.locator("#m0_first_name"),
           "het hoofdlid is leeggemaakt door een rij toe te voegen").to_have_value("Hoofd")

    page.fill("#m1_first_name", "Partner")
    page.fill("#m1_last_name", achternaam)
    page.fill("#m1_date_of_birth", "1981-02-02")
    page.select_option("#m1_gender_code", index=1)

    # Eén opslaan-actie; de server stuurt door naar de gezinspagina.
    page.get_by_role("button", name="Opslaan").click()
    page.wait_for_url("**/admin/leden/gezin/**", timeout=10000)
    pagina_klaar(page)

    hoofd = page.locator("#leden-detail", has_text=f"Hoofd {achternaam}")
    expect(hoofd, "het hoofdlid staat niet op de gezinspagina").to_be_visible()
    expect(page.locator("#leden-detail", has_text=f"Partner {achternaam}"),
           "het tweede gezinslid is niet mee bewaard").to_be_visible()
    expect(page.locator("#adres-kaart"), "het adres is niet mee bewaard").to_contain_text(
        "Teststraat 1")
