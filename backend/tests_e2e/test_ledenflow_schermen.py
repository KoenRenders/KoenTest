"""E2E #1183: de schermen die de schermafdruk-tool van de ledenflow vastlegt.

`tests_e2e/screenshots.py` is gereedschap en geen test — het wordt niet door
pytest verzameld en het bewijst dus niets over wat er op de beelden staat. Deze
tests staan ernaast en bewaken precies dat: **toont het scherm werkelijk wat de
afdruk moet tonen?**

Zonder hen legt de tool een leeg scherm vast en merkt niemand het. Dat is geen
theoretisch gevaar: de e2e-seed maakt een gezin met een lidmaatschap voor het
LOPENDE jaar, en dat gezin toont geen vernieuwknop. Een afdruk "verlengen" van
dat gezin zou een portaal zonder knop zijn, en op de uitlegpagina zou die
afbeelding iets beloven wat er niet staat.

Vandaar twee extra seed-gezinnen (#1183), elk voor één toestand die het eerste
niet kan tonen. De test hieronder toetst alle drie de toestanden náást elkaar —
dat de knop er is bij het verlopen gezin bewijst pas iets als je ook ziet dat hij
er níét is bij het gezin dat in orde is.
"""
import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie  # noqa: E402

VERLENGKNOP = "Lidmaatschap vernieuwen"


def _sessie(email: str) -> str:
    from app.domains.auth.api import make_session_value

    return make_session_value(email)


@pytest.fixture(scope="module")
def browser_page():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
        yield page
        browser.close()


def _portaal(page, email: str):
    page.context.clear_cookies()
    login_met_sessie(page, _sessie(email))
    page.goto("/leden/gezin")
    page.wait_for_selector("main", timeout=5000)
    return page


def _zet_venster(waarde):
    """Zet `membership_renewal_start_md` in de databank van de afdrukomgeving.

    Kan van buiten het serverproces: `tenant_config` cachet niets, het leest de
    instelling bij elk verzoek opnieuw (nagegaan tijdens het bouwen van #1238 — er
    staat geen enkele cache in dat bestand). Vandaar dat deze test het venster echt
    open en dicht kan doen tussen twee paginaweergaven.
    """
    from app.database import SessionLocal
    from app.domains.registry import load_all_models
    from app.kernel.tenant_config import set_setting

    load_all_models()
    db = SessionLocal()
    try:
        set_setting(db, "membership_renewal_start_md", waarde)
        db.commit()
    finally:
        db.close()


def test_de_drie_ledentoestanden_tonen_elk_iets_anders(browser_page):
    """De kern van #1183, uitgebreid met punt 5 van #1238 (gevonden door Koen).

    Drie toestanden naast elkaar, want "de knop staat er" bewijst pas iets als je ook
    ziet wanneer hij er níét staat:

    - het seed-gezin, lidmaatschap loopt, **venster open** → wél een vernieuwknop.
      Dat is wat een lid op de echte site ziet: daar staat
      `membership_renewal_start_md` gezet, en de afdrukomgeving heeft het nu ook;
    - hetzelfde gezin met het **venster dicht** → geen knop. Dit is precies de
      tegenproef die #1238 vraagt: ze bewijst dat de knop aan díé instelling hangt en
      niet aan iets anders;
    - het verlopen gezin, ook met het venster dicht → tóch een knop. Zonder dekking
      staat `renewal_available` onvoorwaardelijk op True, en dat is een andere tak dan
      de eerste twee.

    Tegenproef op de derde: het lidmaatschap van het verlopen gezin op het LOPENDE jaar
    gezet → die knop verdwijnt.
    """
    from seed_e2e import MARKER_EMAIL, MARKER_EMAIL_VERLOPEN

    page = _portaal(browser_page, MARKER_EMAIL)
    expect(page.get_by_role("button", name=VERLENGKNOP)).to_be_visible()

    # Het venster dicht doen en weer openzetten: een `finally`, want elke andere e2e
    # die na deze draait leest dezelfde instelling.
    _zet_venster(None)
    try:
        page = _portaal(browser_page, MARKER_EMAIL)
        expect(page.get_by_role("button", name=VERLENGKNOP)).to_have_count(0)

        page = _portaal(browser_page, MARKER_EMAIL_VERLOPEN)
        expect(page.get_by_role("button", name=VERLENGKNOP)).to_be_visible()
    finally:
        _zet_venster("01-01")

    page = _portaal(browser_page, MARKER_EMAIL)
    expect(page.get_by_role("button", name=VERLENGKNOP)).to_be_visible()


def test_het_voorbeeldgezin_staat_volledig_op_de_afdruk(browser_page):
    """#1238 punt 3: geen lege verplichte velden op een publieke uitlegpagina.

    Op de afgeleverde reeks stonden geboortedatum, geslacht en gsm leeg — alle drie met
    een sterretje — en er stond geen adres, niet in de leesweergave en ook niet in het
    bewerkformulier, want die twee hangen aan dezelfde `{% if p.address %}`. Dat leest
    als een half ingevuld formulier.

    De verdeling is die van Koen: de ouders dragen e-mail en gsm, de meerderjarige
    kinderen niet. Die tweede helft is even belangrijk als de eerste — het scherm toont
    dan ook hoe een gezinslid zonder eigen contactgegevens eruitziet — dus deze test
    toetst ze beide en niet alleen "alles gevuld".

    Rood te maken door één van de velden uit `seed_e2e` weg te laten.
    """
    from seed_e2e import HOOFDLID_GSM, JOMMEKE_STRAAT, MARKER_EMAIL, PARTNER_GSM

    page = _portaal(browser_page, MARKER_EMAIL)
    kaarten = page.locator('div.space-y-4 div[x-show="!edit"]')
    teksten = kaarten.all_inner_texts()
    assert len(teksten) == 4, f"verwacht vier gezinsleden, gezien: {len(teksten)}"

    for tekst in teksten:
        assert "°" in tekst, f"geen geboortedatum op de kaart: {tekst!r}"
        assert JOMMEKE_STRAAT in tekst, f"geen adres op de kaart: {tekst!r}"

    ouders = [t for t in teksten if "Theofiel" in t or "Marie" in t]
    kinderen = [t for t in teksten if "Annemieke" in t or "Rozemieke" in t]
    assert len(ouders) == 2 and len(kinderen) == 2, (
        f"de vier kaarten zijn niet twee ouders en twee kinderen: {teksten!r}")

    for tekst, gsm in zip(sorted(ouders), (PARTNER_GSM, HOOFDLID_GSM)):
        assert "@" in tekst, f"de ouder mist een e-mailadres: {tekst!r}"
        assert gsm in tekst, f"de ouder mist zijn gsm-nummer: {tekst!r}"
    for tekst in kinderen:
        assert "@" not in tekst, (
            f"een meerderjarig kind draagt een e-mailadres: {tekst!r} — de verdeling "
            "van Koen geeft die alleen aan de ouders")

    # Geslacht staat niet in de leesweergave; het bewerkformulier toont het, en dat is
    # het scherm van de afdruk `leden-gezin-bewerken`. Via JavaScript gelezen omdat die
    # formulieren dichtgeklapt zijn.
    #
    # Binnen `form[id^="pp-"]` en niet over de hele pagina: het portaal draagt onderaan
    # ook een LEEG formulier om een gezinslid toe te voegen, en dat leverde een vijfde,
    # lege keuzelijst — gemeten toen deze assertie er vijf vond.
    geslachten = page.locator("form[id^='pp-'] select[id$='-gender_code']").evaluate_all(
        "els => els.map(e => e.value)")
    assert len(geslachten) == 4, f"vier keuzelijsten verwacht, gezien: {geslachten!r}"
    assert all(geslachten), f"een gezinslid heeft geen geslacht: {geslachten!r}"


def test_de_voettekst_toont_geen_plaatshouders(browser_page):
    """#1238 punt 4: «Naam van de vereniging» hoort niet op een publieke afdruk.

    Dat is de zaai-inhoud van migratie 027, die op een testomgeving nooit ingevuld
    raakt. Ze staat onderaan élk beeld van de reeks, dus ze staat ook onderaan elke
    afbeelding op de uitlegpagina.

    Getoetst op het teken zelf en niet op de volledige zin: de plaatshouders zijn de
    enige plek waar deze site dubbele aanhalingstekens zo gebruikt, en zo faalt de test
    ook als er een andere plaatshouder bijkomt. Rood te maken door
    `VOETTEKST_HTML` uit de seed te halen.
    """
    browser_page.context.clear_cookies()
    browser_page.goto("/")
    browser_page.wait_for_selector("footer", timeout=5000)
    voet = browser_page.locator("footer").inner_text()
    for teken in ("\u00ab", "\u00bb"):
        assert teken not in voet, (
            f"de voettekst draagt nog een plaatshouder: {voet!r}")


def test_er_staat_geen_naam_uit_de_ledenadministratie_op(browser_page):
    """#1183, punt 4 — de reden dat deze beelden niet met de hand genomen worden.

    HDEV draagt echte ledenrecords; een afdruk daarvan zet naam en adres van een
    echt lid op een publieke pagina, en dat is een lek dat geen grep ooit vindt
    omdat het in een afbeelding zit. De tool weigert al een niet-lokale host; deze
    test controleert de andere kant — dat wat er op het scherm staat uit de seed
    komt.

    Toetst op de HERKOMST en niet op een lijst echte namen: zo'n lijst zou zelf een
    ledenlijst in de repo zijn. Elk gezinslid op het portaal draagt een achternaam
    die déze seed maakt; staat er een andere, dan komt hij uit de
    ledenadministratie.

    #1208: dat was een voorvoegselcontrole ("heet het E2E …?") zolang de
    seed-gezinnen "E2E Seed" en "E2E Verlopen" heetten. Die namen lazen op een
    publieke uitlegpagina als een foutmelding en zijn Jommeke en Gobelijn geworden,
    waarmee het gedeelde voorvoegsel verdween. De lijst komt daarom uit
    `seed_e2e.SEED_ACHTERNAMEN` en niet uit dit bestand — een eigen kopie zou na de
    volgende hernoeming groen blijven staan zonder nog iets te toetsen.
    """
    from seed_e2e import MARKER_EMAIL, MARKER_EMAIL_VERLOPEN, SEED_ACHTERNAMEN

    for email in (MARKER_EMAIL, MARKER_EMAIL_VERLOPEN):
        page = _portaal(browser_page, email)
        # De naam staat in een `span.font-semibold` binnen de LEESweergave van de
        # gezinslidkaart; er is geen kop-element. Gevonden doordat de assertie
        # hieronder een lege lijst betrapte in plaats van vacuüm te slagen.
        #
        # `div[x-show="!edit"] >` erbij sinds #1174: het adresbeheer in de
        # bewerkweergave draagt een "hoofdadres"-badge, en de badge-macro gebruikt
        # óók `font-semibold`. Zonder die grens las deze test die badge als een
        # naam en viel ze om op tekst die geen naam is. De test deed zijn werk —
        # hij betrapte onverwachte tekst waar namen gelezen worden — maar hij moet
        # wel de juiste plek lezen.
        namen = page.locator(
            'div.space-y-4 div[x-show="!edit"] > span.font-semibold').all_inner_texts()
        assert namen, f"geen gezinslid op het portaal van {email}"
        for naam in namen:
            assert any(naam.strip().endswith(a) for a in SEED_ACHTERNAMEN), (
                f"{naam!r} draagt geen achternaam uit de seed "
                f"({', '.join(SEED_ACHTERNAMEN)}) — dit portaal toont iemand uit "
                "de ledenadministratie en hoort niet op een publieke pagina")
