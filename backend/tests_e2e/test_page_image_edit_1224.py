"""E2E #1224 — een ingevoegde afbeelding is nog te bewerken: maat én alt.

Koen: *"Kan je een afbeelding nadat ze is ingevoegd op een webpagina ook nog van
grootte wijzigen?"* Dat kon niet. De knop *Afbeelding* opende altijd een verse
dialoog, dus wijzigen betekende verwijderen en opnieuw invoegen.

**De bewerkknop staat in de werkbalk van de editor zelf**, naast zijn
Remove-knop — de plek die Koen zelf vond zonder dat iemand hem aanwees. Dat
scheelt een tweede bedieningsplek voor hetzelfde ding. Gemeten vorm van die
werkbalk, want dat was de vraag of het überhaupt kon:

    div.attachment__toolbar > div.trix-button-row
      > span.trix-button-group--actions > button.trix-button--remove

Ze wordt pas bij het selecteren aangemaakt en daarna weggegooid, dus de knop
wordt er door een MutationObserver in gehangen.

**Drie dingen die gemeten zijn vóór er iets gebouwd werd**, want ze bepalen het
hele ontwerp:

1. `composition.editingAttachment` geeft exact de aangeklikte bijlage terug, mét
   onze eigen sleutels (`alt`, `size`) erin. Dat is hoe de dialoog weet wélke
   afbeelding ze bewerkt.
2. `attachment.setAttributes(...)` werkt **in place**: één figuur vóór, één erna,
   en de nieuwe waarden staan in de verborgen invoer — mét behoud van dezelfde
   bijlage. (Een `insertAttachment` op een geselecteerde bijlage vervángt haar;
   zie de alinea over de tegenproef verderop.)
3. De attributen komen terug als `{alt, contentType, height, size, url, width}` —
   de maat van #1207 reist dus gewoon mee en hoeft niet apart bewaard te worden.

**De rondgang is de test die telt.** Wijzigen, opslaan, opnieuw openen, iets
bijtypen, nogmaals opslaan — dat is de val waarop de alt eerder sneuvelde en
waarvoor de bijlage-JSON gekozen is.

**De tegenproef uit het issue reproduceert niet, en dat heeft de tests veranderd.**
Het issue verwachtte dat "gewoon opnieuw invoegen" een TWEEDE afbeelding oplevert.
Gemeten: met de bijlage geselecteerd **vervangt** een `insertAttachment` haar, dus
het aantal blijft 1 en een telling ziet geen enkel verschil — de eerste versie van
deze tests stond dan ook gewoon groen met invoegen in de bewerktak.

Wat wél verschilt is de **identiteit**: bijwerken houdt id 188, invoegen maakt er
891 van. En dat is geen detail — een vervangen bijlage is een nieuw object, dus
alles wat we er niet uitdrukkelijk opnieuw op zetten verdwijnt stil. Daarop toetst
`test_bijwerken_wijzigt_DEZELFDE_bijlage` nu.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
- de bewerkknop laten invoegen in plaats van bijwerken: **1 failed**, met "de
  bijlage is vervangen in plaats van bijgewerkt: [188] → [891]";
- `bewerkteBijlage.setAttributes(...)` overslaan: **2 failed** — behalve de
  rondgangtest ("de bijgewerkte alt is bij de tweede bewaring verdwenen", met de
  oude waarden in de melding) valt ook de identiteitstest, want die controleert
  óók dat de maat werkelijk gewijzigd is. Dat is geen ruis maar dezelfde
  bevinding langs twee wegen.
"""

import json
import os
import re
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, Paginascherm, login_met_sessie  # noqa: E402

EERSTE_ALT = "Eerste alternatieve tekst"
NIEUWE_ALT = "Bijgewerkte alternatieve tekst"


def _ontbreekt(reden: str) -> None:
    if os.environ.get("E2E_SEEDED") == "1":
        pytest.fail(f"e2e-seed geladen maar: {reden}")
    pytest.skip(reden)


@pytest.fixture(scope="module")
def editor():
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


def _bijlagen(inhoud: str) -> list[dict]:
    return [
        json.loads(m.replace("&quot;", '"'))
        for m in re.findall(r'data-trix-attachment="([^"]*)"', inhoud)
    ]


def _voeg_in(page, scherm, *, alt: str, maat: str) -> None:
    page.get_by_role("button", name="Afbeelding").first.click()
    dialoog = page.get_by_role("dialog")
    expect(dialoog, "het dialoogje ging niet open").to_be_visible()
    keuze = dialoog.locator("button[data-url]").first
    if keuze.count() == 0:
        _ontbreekt("geen pagina-afbeelding in de bibliotheek")
    keuze.click()
    dialoog.locator("#cp-alt").fill(alt)
    dialoog.get_by_role("button", name=maat, exact=True).click()
    dialoog.get_by_role("button", name="Invoegen", exact=True).click()
    page.wait_for_function(
        "() => document.querySelector('#cp-trix figure.attachment')", timeout=5000
    )


def _open_de_bewerkdialoog(page):
    """Klik de bijlage aan en dan de knop in de werkbalk van de editor."""
    page.locator("#cp-trix figure.attachment").first.click()
    knop = page.locator("[data-raak-beeld-bewerken]")
    expect(
        knop.first, "de bewerkknop verschijnt niet in de werkbalk van de geselecteerde bijlage"
    ).to_be_visible()
    knop.first.click()
    dialoog = page.get_by_role("dialog")
    expect(dialoog, "de bewerkdialoog ging niet open").to_be_visible()
    return dialoog


@pytest.fixture
def verse_pagina(editor):
    """Een pagina met één ingevoegde afbeelding op 'Half'."""
    scherm = Paginascherm(editor).open_eerste()
    if scherm is None:
        _ontbreekt("geen cms-pagina op deze omgeving")
    # Leegmaken: eerdere tests in deze suite laten hun eigen afbeeldingen staan,
    # en dan telt "hoeveel afbeeldingen staan er" iets anders dan deze test denkt.
    editor.evaluate("() => document.getElementById('cp-trix').editor.loadHTML('')")
    editor.wait_for_function(
        "() => !document.querySelector('#cp-trix figure.attachment')", timeout=5000
    )
    _voeg_in(editor, scherm, alt=EERSTE_ALT, maat="Half")
    return scherm


def test_de_dialoog_opent_met_de_huidige_alt_en_maat(editor, verse_pagina):
    """Punt 1 en 2 van het issue: aanklikbaar én gevuld.

    Leeg openen zou betekenen dat wijzigen alsnog overtypen is — en bij de alt
    zou je die dan opnieuw moeten verzinnen.
    """
    dialoog = _open_de_bewerkdialoog(editor)

    assert dialoog.locator("#cp-alt").input_value() == EERSTE_ALT, (
        "de alt is niet voorgevuld met de huidige waarde"
    )
    gekozen = dialoog.locator("button[data-url]").evaluate_all(
        "els => els.filter(e => e.className.includes('border-blue-700')).length"
    )
    assert gekozen == 1, (
        f"{gekozen} afbeeldingen staan als gekozen gemarkeerd, 1 verwacht — de "
        "dialoog opent niet op de afbeelding die je aanklikte"
    )


def _bijlage_ids(page) -> list[int]:
    return page.evaluate(
        "() => document.getElementById('cp-trix').editor.getDocument()"
        ".getAttachments().map(a => a.id)"
    )


def test_bijwerken_wijzigt_DEZELFDE_bijlage(editor, verse_pagina):
    """Punt 3, en het toetst de IDENTITEIT en niet het aantal.

    Het issue verwachtte dat "gewoon opnieuw invoegen" een tweede afbeelding zou
    opleveren. **Dat reproduceert niet**, en dat is gemeten: met de bijlage
    geselecteerd VERVANGT een `insertAttachment` haar, dus het aantal blijft
    gewoon 1 en een telling ziet geen verschil. Wat wél verschilt is de identiteit
    van de bijlage — gemeten: bijwerken houdt id 188, invoegen maakt er 891 van.

    Dat verschil is niet cosmetisch. Een vervangen bijlage is een nieuw object:
    alles wat wij er niet uitdrukkelijk opnieuw op zetten — breedte, hoogte,
    contentType, en elke sleutel die een volgend issue toevoegt — verdwijnt
    stilletjes. Daarom werkt de bewerkweg de bestaande bij met
    `setAttributes(Object.assign({}, huidige, wijzigingen))`.
    """
    ids_voor = _bijlage_ids(editor)
    assert len(ids_voor) == 1, f"opstelling klopt niet: {ids_voor}"

    dialoog = _open_de_bewerkdialoog(editor)
    dialoog.get_by_role("button", name="Klein", exact=True).click()
    dialoog.get_by_role("button", name="Bijwerken", exact=True).click()

    ids_na = _bijlage_ids(editor)
    assert ids_na == ids_voor, (
        f"de bijlage is vervangen in plaats van bijgewerkt: {ids_voor} → {ids_na}. "
        "Een nieuw object verliest elke eigenschap die we niet opnieuw meegeven"
    )

    bijlagen = _bijlagen(verse_pagina.editorinhoud())
    assert len(bijlagen) == 1, f"{len(bijlagen)} afbeeldingen op de pagina, 1 verwacht: {bijlagen}"
    assert bijlagen[0].get("size") == "klein", f"de maat is niet bijgewerkt: {bijlagen[0]}"
    assert bijlagen[0].get("alt") == EERSTE_ALT, (
        "de alt is onbedoeld meegewijzigd toen alleen de maat aangepast werd"
    )
    for sleutel in ("width", "height", "contentType"):
        assert sleutel in bijlagen[0], f"{sleutel} is verdwenen bij het bijwerken: {bijlagen[0]}"


def test_de_nieuwe_alt_overleeft_een_rondgang(editor, verse_pagina):
    """De belangrijkste test: opslaan, opnieuw openen, iets anders wijzigen,
    nogmaals opslaan.

    Dat is de val waarop de alt eerder sneuvelde en de reden dat deze waarden in
    de bijlage-gegevens staan in plaats van op de `<img>`.
    """
    dialoog = _open_de_bewerkdialoog(editor)
    dialoog.locator("#cp-alt").fill(NIEUWE_ALT)
    dialoog.get_by_role("button", name="Bijwerken", exact=True).click()
    verse_pagina.opslaan()

    paginaid = re.search(r"/admin/paginas/(\d+)", editor.url)
    assert paginaid, editor.url
    editor.goto(f"/admin/paginas/{paginaid.group(1)}")
    editor.wait_for_selector("#cp-trix", timeout=10000)
    editor.evaluate("() => document.getElementById('cp-trix').editor.insertString('zz')")
    editor.wait_for_function(
        "() => document.getElementById('cp-content-input').value.includes('zz')", timeout=5000
    )
    verse_pagina.opslaan()

    bijlagen = _bijlagen(verse_pagina.editorinhoud())
    assert len(bijlagen) == 1, f"niet één afbeelding na de rondgang: {bijlagen}"
    assert bijlagen[0].get("alt") == NIEUWE_ALT, (
        f"de bijgewerkte alt is bij de tweede bewaring verdwenen: {bijlagen[0]}"
    )


def test_bijwerken_kan_niet_met_een_lege_alt(editor, verse_pagina):
    """De alt blijft verplicht, ook langs deze nieuwe weg.

    Zonder deze test zou bewerken een omweg zijn rond een toegankelijkheidsregel
    die bij het invoegen wél afgedwongen wordt.
    """
    dialoog = _open_de_bewerkdialoog(editor)
    dialoog.locator("#cp-alt").fill("")

    knop = dialoog.get_by_role("button", name="Bijwerken", exact=True)
    assert knop.is_disabled(), (
        "Bijwerken is klikbaar met een lege alt — dan is bewerken een weg om de "
        "verplichte alternatieve tekst heen"
    )


def test_annuleren_laat_alles_zoals_het_was(editor, verse_pagina):
    """Punt 4. Zonder deze test zou een dialoog die bij het openen al schrijft,
    er net zo goed uitzien."""
    voor = _bijlagen(verse_pagina.editorinhoud())

    dialoog = _open_de_bewerkdialoog(editor)
    dialoog.locator("#cp-alt").fill("Dit mag niet blijven staan")
    dialoog.get_by_role("button", name="Klein", exact=True).click()
    dialoog.get_by_role("button", name="Annuleren", exact=True).click()

    na = _bijlagen(verse_pagina.editorinhoud())
    assert na == voor, f"annuleren heeft toch iets gewijzigd:\nvoor {voor}\nna   {na}"
