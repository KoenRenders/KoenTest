"""E2E-golden-flows voor de BEHEERschermen (#622, laag 3).

De zes bestaande flows zijn allemaal publiek; op de beheerschermen stond er nul —
precies waar het geld zit en waar bij de v2.0.0-validatie de dode knoppen stonden.

Alleen een echte browser bewijst dat een knop iets **doet**. Dat is de enige laag die
#613-punt-3 zou hebben gevangen: daar zagen server én markup er correct uit en deed
de knop toch niets.

Selectors staan in `schermen.py`, zodat een UI-port één bestand raakt i.p.v. elke flow.
"""
import os
import sys
import time

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (BASE, Adminschil, Betalingenscherm,  # noqa: E402
                                Inschrijvingsdetail, Ledenscherm, login_als_admin)


def _ontbreekt(reden: str) -> None:
    """Ontbrekende data: skip tegen een echte omgeving, fout onder de e2e-seed.

    Tegen HDEV zegt "geen openstaande betaling" iets over die omgeving, niet over
    de code — daar is skippen juist. In CI staat de seed er (E2E_SEEDED=1), dus
    dezelfde melding betekent dat het scherm de geseede data niet toont: een
    bevinding. Een skip is tussen groene runs onzichtbaar en dat is precies hoe
    de drie beheerflows maandenlang niets bewezen (#644).
    """
    if os.environ.get("E2E_SEEDED") == "1":
        pytest.fail(f"e2e-seed geladen maar: {reden}")
    pytest.skip(reden)


def _admin_email() -> str:
    """Het adres van de geseede beheerder (migratie 014).

    Uit tests.conftest i.p.v. hier herhaald: de repo is publiek en dit is een echt
    e-mailadres — het hoort op één plek te staan, niet in elk testbestand.
    """
    override = os.environ.get("E2E_ADMIN_EMAIL")
    if override:
        return override
    from tests.conftest import SEEDED_ADMIN_EMAIL

    return SEEDED_ADMIN_EMAIL


@pytest.fixture(scope="module")
def admin_page():
    """Een browser met een adminsessie."""
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
        page.goto("/admin/betalingen")
        # Niet op de URL controleren: een geweigerde sessie geeft hier een 401-pagina
        # op hetzelfde adres, geen redirect. De AdminShell zelf is het bewijs.
        if page.locator("#betalingen-lijst").count() == 0:
            log = page.content()[:200]
            browser.close()
            pytest.skip(f"adminsessie niet aanvaard door deze omgeving: {log!r}")
        yield page
        browser.close()


def test_betaling_bevestigen(admin_page):
    """De knop die in #616 inert was: doet ze in een echte browser wat ze belooft?"""
    betalingen = Betalingenscherm(admin_page).open()
    kaart = betalingen.kaart_met_knop("Bevestig betaald")
    if kaart.count() == 0:
        _ontbreekt("geen openstaande betaling om te bevestigen")

    ogm = betalingen.ogm_van(kaart)
    if ogm is None:
        _ontbreekt("de openstaande betaling heeft geen OGM om haar aan te herkennen")

    betalingen.bevestig_betaald(kaart)

    assert "Vereffend" in " ".join(betalingen.badges(ogm))


def test_bestelregel_wijzigen_werkt_de_bedragen_bij(admin_page):
    """#613: aantal wijzigen deed niets doordat de attributen ge-escaped waren, en
    de bedragen op de kaart volgden niet."""
    betalingen = Betalingenscherm(admin_page).open()
    kaart = betalingen.kaart_met_knop("Toon inschrijvingsdetails")
    if kaart.count() == 0:
        _ontbreekt("geen inschrijving met details op deze omgeving")

    paneel = betalingen.toon_inschrijvingsdetails(kaart)
    detail = Inschrijvingsdetail(paneel)
    detail.bewerken()
    if detail.aantalvelden().count() == 0:
        _ontbreekt("geen bestelregels om te wijzigen")

    detail.zet_aantal(0, 3)
    detail.opslaan()

    # Het paneel blijft open (#613-3) en toont het herrekende totaal (#613-4).
    assert detail.aantalvelden().first.input_value() == "3"
    assert "Totaal" in detail.totaal()


def test_lidmaatschap_schrappen_geeft_een_terugbetaling(admin_page):
    """#619: het schrappen liet de betaling ongemoeid; nu hoort er een te bevestigen
    terugbetaling te verschijnen.

    Betaald lidgeld is een financieel feit: het record blijft staan en er komt een
    terugbetaling naast — het verdwijnt niet stil uit de boekhouding.
    """
    leden = Ledenscherm(admin_page).open()
    if admin_page.locator("#leden-lijst a").count() == 0:
        _ontbreekt("geen gezinnen op deze omgeving")

    admin_page.locator("#leden-lijst a").first.click()
    admin_page.wait_for_timeout(400)
    assert "Lidmaatschappen" in admin_page.content(), "geen lidmaatschapssectie op het gezinsdetail"

    knop = leden.lidmaatschap_verwijderknop()
    if knop.count() == 0:
        _ontbreekt("geen lidmaatschap om te schrappen")
    # De knop vraagt om bevestiging via de in-app modal (#595), niet via
    # confirm() — het attribuut is wat die modal aanstuurt.
    assert knop.get_attribute("data-confirm"), "verwijderknop zonder bevestiging"

    leden.verwijder_lidmaatschap()

    Betalingenscherm(admin_page).open()
    inhoud = admin_page.content()
    assert "Terug te betalen" in inhoud or "Terugbetaling" in inhoud, (
        "na het schrappen staat er geen terugbetaling op de betalingenpagina")


# ── #634: navigatie zonder herlaad en zichtbaar wachten ──────────────────────
# Alleen een echte browser bewijst dit: de server stuurt in beide gevallen exact
# dezelfde HTML, of htmx nu de pagina swapt of de browser ze herlaadt.


def test_navigeren_bouwt_de_schil_niet_opnieuw_op(admin_page):
    """hx-boost: de zijbalk blijft hetzelfde DOM-element, de tabtitel volgt wel.

    De JS-eigenschap op de <aside> is het bewijs: bij een volledige herlaad is het
    element vervangen en is de markering weg. De titel moet wél mee wisselen —
    anders staat de browsergeschiedenis te liegen over waar je bent.
    """
    fouten = []
    admin_page.on("pageerror", lambda e: fouten.append(str(e)))

    schil = Adminschil(admin_page)
    admin_page.goto("/admin/leden")
    admin_page.wait_for_selector("aside", timeout=5000)
    schil.merk_de_zijbalk()
    admin_page.evaluate("window.__raakVenster = 1")
    titel_voor = admin_page.title()

    # Antwoorden meelezen i.p.v. op één te wachten: blijft de boost uit, dan is er
    # geen XHR en zou expect_response gewoon in een timeout lopen zonder te zeggen
    # waarom.
    antwoorden = []
    admin_page.on("response", lambda r: antwoorden.append(
        (r.request.resource_type, r.url, {k.lower(): v for k, v in r.headers.items()})))

    # Toestand vlak vóór de klik: is htmx geladen, draagt de body de boost, en
    # heeft htmx de link daadwerkelijk verwerkt? Dat onderscheidt "htmx ontbreekt"
    # van "htmx negeert deze link".
    diag = admin_page.evaluate("""(function () {
      var a = document.querySelector('aside a[href="/admin/activiteiten"]');
      return {
        htmx: typeof window.htmx,
        bodyBoost: document.body.getAttribute('hx-boost'),
        linkGevonden: !!a,
        linkVerwerkt: a ? Object.keys(a['htmx-internal-data'] || {}) : null,
        scripts: Array.prototype.map.call(
          document.querySelectorAll('script[src]'), function (s) { return s.getAttribute('src'); })
      };
    })()""")

    schil.klik_in_de_zijbalk("/admin/activiteiten")

    # Eerst de serverkant: kreeg htmx de swap-instructies mee? Zo niet, dan ligt de
    # oorzaak in de middleware en niet in de browser — dat scheelt zoeken.
    nav = [a for a in antwoorden if "/admin/activiteiten" in a[1]]
    soorten = [a[0] for a in nav]
    assert nav, f"geen enkel antwoord voor /admin/activiteiten; gezien: {antwoorden[:5]}"
    xhr = [a for a in nav if a[0] == "xhr"]
    assert xhr, (
        f"geen XHR voor de navigatie → hx-boost sloeg niet aan.\n"
        f"  verzoeksoorten: {soorten}\n  toestand vóór de klik: {diag}\n"
        f"  JS-fouten: {fouten}")
    assert "document" not in soorten, (
        f"na de gebooste XHR volgde alsnog een volledige navigatie "
        f"(verzoeksoorten: {soorten}) — een vangnet in ui.htmx_ux() sloeg ten "
        f"onrechte aan.\n  JS-fouten: {fouten}")
    _soort, _url, kop = xhr[-1]
    assert kop.get("hx-reselect") == "#main", f"geen HX-Reselect op het antwoord: {kop}"
    assert kop.get("hx-retarget") == "#main", f"geen HX-Retarget op het antwoord: {kop}"

    # Dan de browserkant. Overleefde `window` niet, dan was het een volledige
    # herlaad (de boost sloeg niet aan); overleefde `window` wél maar de zijbalk
    # niet, dan swapte htmx te veel.
    venster_leeft = admin_page.evaluate("!!window.__raakVenster")
    assert venster_leeft, f"volledige herlaad i.p.v. een gebooste navigatie; JS-fouten: {fouten}"
    assert schil.zijbalk_is_nog_dezelfde(), "htmx swapte meer dan #main"

    # Is de inhoud echt gewisseld? De zijbalk overleeft ook een swap die niet
    # doorging, dus die assertie alleen bewijst nog niets. Bewust via evaluate en
    # niet via een locator: staat #main er niet meer, dan moet de test dát zeggen
    # i.p.v. dertig seconden op een selector te wachten.
    na = admin_page.evaluate("""(function () {
      var m = document.getElementById('main');
      return {
        mainAanwezig: !!m,
        mainKinderen: m ? m.children.length : null,
        h1: m && m.querySelector('h1') ? m.querySelector('h1').innerText : null,
        bodyLengte: document.body.innerHTML.length,
        titel: document.title
      };
    })()""")
    assert na["mainAanwezig"], f"#main is na de swap verdwenen: {na}"
    assert na["h1"] and "ctiviteiten" in na["h1"], f"#main toont het oude scherm: {na}"
    assert "/admin/activiteiten" in admin_page.url, (
        f"de URL is niet meegegaan: {admin_page.url}")
    assert admin_page.title() != titel_voor, (
        f"de tabtitel volgde de navigatie niet (blijft {titel_voor!r}); {na}")
    assert not fouten, f"JS-fouten tijdens de navigatie: {fouten}"


def test_een_lopende_actie_is_zichtbaar(admin_page):
    """Tijdens het verzoek draagt het verzendende element `htmx-request`.

    De controle gebeurt ín de route-handler: op dat moment is het verzoek echt
    onderweg. Een `wait_for_timeout` ná de klik zou een race zijn.
    """
    betalingen = Betalingenscherm(admin_page).open()
    kaart = betalingen.kaart_met_knop("Bevestig betaald")
    if kaart.count() == 0:
        _ontbreekt("geen openstaande betaling om te bevestigen")

    gezien = {}

    def onderschep(route):
        gezien["wachtstand"] = admin_page.evaluate(
            "document.querySelectorAll('.htmx-request').length > 0")
        gezien["balk"] = admin_page.evaluate(
            "document.body.classList.contains('htmx-loading')")
        route.continue_()

    admin_page.route("**/admin/betalingen/**", onderschep)
    try:
        betalingen.bevestig_betaald(kaart)
    finally:
        admin_page.unroute("**/admin/betalingen/**", onderschep)

    assert gezien.get("wachtstand"), "geen element met .htmx-request tijdens het verzoek"
    assert gezien.get("balk"), "de voortgangsbalk liep niet"


def test_de_export_blijft_een_download(admin_page):
    """hx-boost="false" op de exportknop: klikken levert een bestand, geen swap.

    Zonder die uitzondering zou htmx de .ods-bytes proberen te swappen en gebeurde
    er zichtbaar niets.
    """
    Betalingenscherm(admin_page).open()
    knop = admin_page.get_by_role("link", name="Export")
    if knop.count() == 0:
        _ontbreekt("geen exportknop op dit scherm")

    with admin_page.expect_download(timeout=10000) as download:
        knop.first.click()

    assert download.value.suggested_filename.endswith(".ods")
