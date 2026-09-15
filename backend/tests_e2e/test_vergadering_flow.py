"""E2E-golden-flow voor de vergadermodule (CR-09, #258): aanmaken → notuleren.

Waarom een browser en niet de pytest-suite, die dezelfde routes al raakt: de
schermtests bewijzen dat de server het juiste HTML teruggeeft. Wat ze níét kunnen
bewijzen is dat de knoppen in een echte browser iets dóén — en juist dit scherm
leunt zwaar op htmx en op een WYSIWYG-editor: typen, focus verliezen, de rij die
zichzelf vervangt. Precies het soort dode knop dat in #613/#616 door de
serverkant heen glipte.

**Geen data-afhankelijke skips meer** (#939, na een melding uit een ander spoor).
De eerste versie sloeg over wanneer ze geen vergadering of geen punten vond, en
precies dat gebeurde: nadat het tekstvak een Trix-editor werd, vond ze geen
`textarea[name=notes]` meer en sloeg ze zichzelf over. Twee groene runs lang
bewees deze flow niets. Een golden flow die zichzelf overslaat wanneer de data
niet klopt, dekt het geval af waarvoor hij bestaat — dus maakt hij nu zelf aan
wat hij nodig heeft, en faalt hij als dat niet lukt.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin  # noqa: E402


def _admin_email() -> str:
    override = os.environ.get("E2E_ADMIN_EMAIL")
    if override:
        return override
    from tests.conftest import SEEDED_ADMIN_EMAIL

    return SEEDED_ADMIN_EMAIL


@pytest.fixture(scope="module")
def admin_page():
    try:
        from app.domains.auth.api import make_session_value

        email = _admin_email()
    except Exception as exc:  # pragma: no cover - alleen in een kale omgeving
        pytest.skip(f"backend niet importeerbaar voor de sessiewaarde: {exc}")

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE)
        login_als_admin(page, email, make_session_value(email))
        page.goto("/admin/vergaderingen")
        if page.locator("#vg-lijst").count() == 0:
            inhoud = page.content()[:200]
            browser.close()
            pytest.skip(f"adminsessie niet aanvaard door deze omgeving: {inhoud!r}")
        yield page
        browser.close()


def _nieuwe_vergadering(page, datum: str) -> str:
    """Maak een vergadering aan en geef haar adres terug.

    Elke test maakt zijn eigen vergadering in plaats van de eerste uit de lijst te
    openen: dan hangt de flow niet af van wat een vorige run heeft achtergelaten,
    en is "er valt niets te notuleren" een echte fout in plaats van een reden om
    over te slaan.
    """
    page.goto("/admin/vergaderingen/nieuw")
    page.fill("#vg-datum", datum)
    page.click("button[type=submit]")
    # Op het document wachten en NIET op een URL-patroon: `**/admin/vergaderingen/**`
    # matcht ook `/admin/vergaderingen/nieuw`, dus dat wachten was meteen voorbij
    # en de test keek naar het aanmaakscherm. Het fragment is het bewijs.
    page.wait_for_selector("#vg-document", timeout=10_000)
    return page.url


def _vul_de_kring(page) -> None:
    """Zet de eerste gevonden persoon in de vergaderkring, via het scherm zelf."""
    page.goto("/admin/vergaderingen/kring")
    page.wait_for_selector("#vg-kring")
    page.fill("input[name=q]", "e")
    page.wait_for_timeout(800)
    toevoegen = page.locator("#vg-kring form[hx-post='/admin/vergaderingen/kring'] button")
    if toevoegen.count() == 0:
        return
    toevoegen.first.click()
    page.wait_for_timeout(800)


def test_een_vergadering_aanmaken_en_notuleren(admin_page):
    """Aanmaken levert een ingevulde agenda; aanwezigheid blijft staan na de swap."""
    page = admin_page
    url = _nieuwe_vergadering(page, "2026-10-01")

    # De agenda is samengesteld: de vijf vaste secties in hun vaste volgorde, met
    # Varia als laatste daarvan. Niet "de laatste h2 op de pagina": Aanwezigheid
    # en Bijlagen zijn ook koppen, en die staan er bewust omheen.
    koppen = [k.strip() for k in page.locator("#vg-document h2").all_text_contents()]
    secties = [k for k in koppen if k in ("Evaluatie voorbije activiteiten",
                                          "Volgende activiteiten", "Leden",
                                          "Programma-ideeën", "Varia")]
    assert secties == ["Evaluatie voorbije activiteiten", "Volgende activiteiten",
                       "Leden", "Programma-ideeën", "Varia"], koppen

    # Aanwezigheid: één klik, en de knop komt als 'aanwezig' terug uit de swap.
    knoppen = page.locator("#vg-document form[hx-post*='aanwezigheid'] button")
    if knoppen.count() == 0:
        # De kring is leeg in deze omgeving: hem hier aanleggen in plaats van de
        # test over te slaan — dat toetst meteen het kringscherm.
        _vul_de_kring(page)
        page.goto(url)
        page.wait_for_selector("#vg-document")
        knoppen = page.locator("#vg-document form[hx-post*='aanwezigheid'] button")
    assert knoppen.count() > 0, "geen enkele persoon om in de vergaderkring te zetten"

    naam = knoppen.first.text_content().strip()
    knoppen.first.click()
    page.wait_for_timeout(700)
    aangevinkt = page.locator("#vg-document form[hx-post*='aanwezigheid'] button").first
    assert "bg-green-50" in (aangevinkt.get_attribute("class") or ""), \
        f"'{naam}' kleurde niet als aanwezig na de swap"


def test_een_notitie_overleeft_de_swap(admin_page):
    """Typen in de editor en wegklikken bewaart de notitie.

    Drie schakels achter elkaar: de editor schrijft naar een verborgen veld,
    `trix-blur` post het formulier, en de rij vervangt zichzelf. Breekt er één,
    dan is het verslag na de vergadering leeg — en dat merkt niemand tot het te
    laat is.
    """
    page = admin_page
    url = _nieuwe_vergadering(page, "2026-11-05")

    editors = page.locator("#vg-document trix-editor")
    assert editors.count() > 0, (
        "geen enkel punt met een notitie-editor op een verse agenda — de seed "
        "hoort minstens één activiteit te leveren")

    editor = editors.first
    editor.click()
    editor.type("Uitverkocht — 300 tickets.")
    # Focus weghalen: dát vuurt `trix-blur` af en start dus het opslaan.
    page.locator("#vg-document h2").first.click()
    page.wait_for_timeout(1200)

    # HERLADEN, en niet kijken naar het veld dat er al staat. Trix schrijft zijn
    # inhoud bij élke toetsaanslag naar dat verborgen veld — puur in de browser.
    # Een assertie daarop slaagt dus ook wanneer er niets verstuurd is; gemeten
    # met de trigger kapotgemaakt bleef de test groen. Na een herlaad kan de tekst
    # alleen van de server komen.
    page.goto(url)
    page.wait_for_selector("#vg-document")
    bewaard = page.locator("#vg-document input[name=notes]").first
    assert "300 tickets" in (bewaard.get_attribute("value") or ""), \
        "de notitie is niet bewaard: na een herlaad staat ze er niet meer"
