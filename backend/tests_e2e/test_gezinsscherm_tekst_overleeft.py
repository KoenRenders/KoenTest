"""E2E: getypte tekst op het gezinsscherm overleeft een andere deelactie (#1111).

Koens scenario: je opent het adresformulier, typt een straat, en doet dan iets
anders op het scherm. Tot #1111 antwoordde élke deelactie met het hele blok,
opnieuw uit de databank, en htmx verving `#leden-detail` — de adresvelden
kregen hun (lege) databankwaarde terug en het Alpine-`edit` reset mee, dus het
vlak klapte dicht. Het leek alsof er niets gebeurd was.

**Alleen een browser ziet dit.** De servertest
(`tests/test_gezinsscherm_deelacties_1111.py`) bewijst dat het antwoord de
adreskaart niet bevat; dat het getypte er dan óók echt nog staat en het vlak open
blijft, is htmx- en Alpine-gedrag. De deelactie hier is de bestuurslidkeuze: die
post op `change`, dus één keuze in de lijst is de hele handeling.

Kapotgemaakt om te controleren dat deze test rood kan worden: de bestuurslidvorm
weer op `#leden-detail`/`innerHTML` gezet → het veld is leeg en het vlak dicht.
"""
import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (BASE, Ledenscherm, htmx_afgerond,  # noqa: E402
                                login_met_sessie, pagina_klaar)
from tests_e2e.test_beheer_flows import _admin_email, _ontbreekt  # noqa: E402

GETYPT = "Teststraat 1111"


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(base_url=BASE)
        yield p
        browser.close()


def test_een_getypte_straat_overleeft_de_bestuurslidkeuze(page):
    from app.domains.auth.api import make_session_value

    login_met_sessie(page, make_session_value(_admin_email()))
    Ledenscherm(page).open()
    if page.locator("#leden-lijst a").count() == 0:
        _ontbreekt("geen gezin om te openen")
    page.locator("#leden-lijst a").first.click()
    page.wait_for_selector("#adres-kaart", timeout=5000)
    pagina_klaar(page)

    # Het adresvlak open, en iets getypt.
    page.locator("#adres-kaart").get_by_role("button", name="Bewerken").click()
    straat = page.locator("#street")
    expect(straat).to_be_visible()
    straat.fill(GETYPT)

    # Een ándere deelactie: het bestuurslid kiezen — post op `change`.
    keuze = page.locator("#bestuurslid-kaart select")
    opties = keuze.locator("option").all()
    if len(opties) < 2:
        _ontbreekt("geen persoon om als bestuurslid te kiezen")
    with htmx_afgerond(page):
        keuze.select_option(index=1)

    # Het getypte staat er nog, en het vlak is niet dichtgeklapt.
    expect(straat, "de getypte straat is weg — de deelactie verving de adreskaart").to_have_value(GETYPT)
    expect(straat, "het adresvlak klapte dicht").to_be_visible()
    # En de keuze is wél bewaard: de kaart is vervangen door haar nieuwe stand.
    expect(page.locator("#bestuurslid-kaart select")).to_have_value(
        opties[1].get_attribute("value"))
