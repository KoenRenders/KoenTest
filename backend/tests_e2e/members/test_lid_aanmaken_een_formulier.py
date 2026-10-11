"""E2E: een lid aanmaken is één formulier met één opslaan-actie (#1110).

De servertests bewijzen wat er na één POST in de databank staat. Wat alleen een
browser kan tonen: dat het scherm ook écht één formulier is — een gezinslid
erbij is een kaart erbij zonder iets te bewaren en zonder iets te vervangen,
en pas Opslaan schrijft, waarna je op de gezinspagina staat. Dat was de klacht:
tot #1110 waren het vier opslag-acties, en elke deelactie kon je typwerk wissen.

Since #1899 the screen is the form of the public Word lid on the person card:
the extra member is a card from the page's own template (no request), with its
relation, and the address is a section of a kit form — so on a phone its fields
stack like every other field of that form (Koen, 9 October 2026, on the address
in a form of the kit), which the second test measures. The quarter grid of
#1854 went with the old form.

Proven red (locally, restored): `disabled` put on the "+ Gezinslid toevoegen"
button of the kit's repeating group → no second card: the first test falls in
its click, which waits for a button that never becomes enabled, before the
assertion on the second card — one defect, the card does not come. `grid
grid-cols-4` put around the address fields → the second fails on "the address
fields do not stack: [1098, 1119, 1098, 1161]".
"""

import os
import sys
import time

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402
from tests_e2e.test_beheer_flows import _admin_email, _ontbreekt  # noqa: E402


@pytest.fixture(scope="module")
def page():
    from app.domains.auth.api import make_session_value

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(base_url=BASE)
        login_met_sessie(p, make_session_value(_admin_email()))
        yield p
        browser.close()


def test_hoofdlid_en_gezinslid_in_een_keer_bewaard(page):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto("/admin/leden/nieuw")
    pagina_klaar(page)

    achternaam = f"E2E{int(time.time())}"
    page.fill("#h-n0-first_name", "Hoofd")
    page.fill("#h-n0-last_name", achternaam)
    page.fill("#h-n0-date_of_birth", "1980-01-01")
    page.select_option("#h-n0-gender_code", index=1)
    page.fill("#e-n0e-value", f"e2e-nieuwlid-{achternaam.lower()}@example.com")
    page.fill("#h-n0-mobile", "0470000000")
    page.fill("#address-street", "Teststraat")
    page.fill("#address-house_number", "1")

    postcode = page.locator("#address-postal_code")
    if postcode.locator("option").count() < 2:
        _ontbreekt("geen postcode in de keuzelijst")
    postcode.select_option(index=1)

    # Een gezinslid erbij: een lege kaart, geen opslag — wat hierboven staat blijft.
    first_names = page.locator("#lid-nieuw-form input[name$='.first_name']")
    assert first_names.count() == 1, "the page does not start with the main member alone"
    page.get_by_role("button", name="Gezinslid toevoegen").click()
    expect(first_names, "de tweede persoonskaart kwam niet").to_have_count(2)
    expect(
        page.locator("#h-n0-first_name"), "het hoofdlid is leeggemaakt door een kaart toe te voegen"
    ).to_have_value("Hoofd")

    first_names.nth(1).fill("Partner")
    page.locator("#lid-nieuw-form input[name$='.last_name']").nth(1).fill(achternaam)
    page.locator("#lid-nieuw-form input[name$='.date_of_birth']").nth(1).fill("1981-02-02")
    page.locator("#lid-nieuw-form select[name$='.gender_code']").nth(1).select_option(index=1)
    page.locator("#lid-nieuw-form select[name$='.relation_type']").first.select_option("PARTNER")

    # Eén opslaan-actie; de server stuurt door naar de gezinspagina.
    page.locator("[data-form-save]").first.click()
    page.wait_for_url("**/admin/leden/gezin/**", timeout=10000)
    pagina_klaar(page)

    record = page.locator("main")
    expect(record, "het hoofdlid staat niet op de gezinspagina").to_contain_text(
        f"Hoofd {achternaam}"
    )
    expect(record, "het tweede gezinslid is niet mee bewaard").to_contain_text(
        f"Partner {achternaam}"
    )
    expect(record, "het adres is niet mee bewaard").to_contain_text("Teststraat 1")


def test_on_a_phone_the_address_stacks_and_nothing_scrolls_sideways(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/admin/leden/nieuw")
    pagina_klaar(page)

    seen = page.evaluate(
        """() => {
          const top = id => Math.round(document.getElementById(id).getBoundingClientRect().top);
          const width = id => Math.round(document.getElementById(id).getBoundingClientRect().width);
          const ids = ['address-street', 'address-house_number', 'address-bus_number',
                       'address-postal_code'];
          return {tops: ids.map(top), widths: ids.map(width),
                  sideways: document.documentElement.scrollWidth - window.innerWidth};
        }"""
    )

    print("MEASURE", seen)
    assert seen["tops"] == sorted(set(seen["tops"])), (
        f"the address fields do not stack: {seen['tops']}"
    )
    assert len(set(seen["widths"])) == 1 and seen["widths"][0] >= 280, (
        f"the address fields are {seen['widths']} px wide"
    )
    assert seen["sideways"] <= 0, f"the page scrolls sideways by {seen['sideways']} px"
