"""E2E #1230 — de bewerkknop leest als een knop, en de maat is in de editor te zien.

Twee meldingen van Koen op HDEV, allebei over wat je in de editor ziet.

**1.** *"De 'Bewerken' knop is wel heel moeilijk te vinden."* Gemeten vóór de
reparatie: het verwijderkruisje is 20 × 20 met `background-color:
rgb(255, 255, 255)` en `border-radius: 50%`; onze knop was 73 × 20 met
`rgba(0, 0, 0, 0)` — dus kale tekst over het beeld. De werkbalk zweeft over de
afbeelding, en die kan licht of donker zijn.

**2.** *"Kan je de afbeelding in de edit-modus ook 'sizen'?"* De maat werd pas bij
het tonen van de pagina op de `<img>` gezet, dus in de editor stond alles op
volle breedte: je koos *klein* en zag *groot*.

**Het aanraakvlak van 44 px uit het issue is NIET gehaald, en dat is een
meting.** De werkbalk van de editor is **21 px hoog** en de twee knoppen raken
elkaar — gemeten: kruisje van x=793 tot 814, Bewerken van 814 tot 887. Een
klikvlak van 44 px past daar niet in en zou over het **verwijderkruisje** heen
liggen. Een onzichtbaar groter trefvlak boven een knop die iets wist, is erger
dan een kleine knop. De knop houdt dus de hoogte van het kruisje; of beide
knoppen naar 44 px moeten, is een keuze over de eigen bediening van de editor en
ligt bij Koen.

**De maat in de editor is een BENADERING.** De tekstkolom van de editor is niet
die van de publieke pagina, dus *half* is hier niet dezelfde pixelbreedte. Het
doel is dat je het verschil ziet tussen klein, half en vol — deze tests meten dus
de verhouding en niet een absolute breedte.

**De editor ververst het bijlage-attribuut niet na een wijziging, en dat kostte
een omweg.** De opmaakregels lezen `data-trix-attachment` van de figuur — dezelfde
opgeslagen waarde als de publieke weergave, zodat er geen tweede vertaling
ontstaat. Maar na een `setAttributes` bleek, gemeten: **model** `klein`,
**verborgen invoer** `klein`, **DOM-attribuut** nog `half`. Wie de maat wijzigde,
zag dus niets veranderen tot een herlaadbeurt. `updatePageImage` schrijft die ene
waarde daarom zelf op de figuur terug; het model blijft de bron.

**De UI-poort ziet deze knop niet**, en dat is de val van dit issue: zij leest
sjablonen, en deze knop ontstaat in JavaScript. Groen betekent daar dus niets
over dit ding. Daarom staat hier ook een test op de toegankelijke naam.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
- `background-color` uit `.raak-beeld-bewerken` gehaald → de knopstijltest valt
  om met `rgba(0, 0, 0, 0)`, precies de waarde die Koen zag;
- de twee `figure.attachment[data-trix-attachment…]`-regels weggehaald → **2
  failed**: de maattest met "klein 963, half 963, vol 963" in een editor van
  982 px, én de wijzigtest, want zonder regels valt er ook niets te zien
  veranderen;
- `bewerkteFiguur.setAttribute(...)` overgeslagen → *de maat wijzigen verandert de
  weergave meteen* valt om, en alleen die: het opslaan blijft immers correct, want
  het model klopt wél. Dat is precies het verschil tussen "bewaard" en "zichtbaar"
  waar dit issue over gaat.
"""

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, Paginascherm, login_met_sessie  # noqa: E402


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


def _leeg(page):
    page.evaluate("() => document.getElementById('cp-trix').editor.loadHTML('')")
    page.wait_for_function(
        "() => !document.querySelector('#cp-trix figure.attachment')", timeout=5000
    )


def _voeg_in(page, maat: str, alt: str):
    page.get_by_role("button", name="Afbeelding").first.click()
    dialoog = page.get_by_role("dialog")
    expect(dialoog).to_be_visible()
    keuze = dialoog.locator("button[data-url]").first
    if keuze.count() == 0:
        _ontbreekt("geen pagina-afbeelding in de bibliotheek")
    keuze.click()
    dialoog.locator("#cp-alt").fill(alt)
    dialoog.get_by_role("button", name=maat, exact=True).click()
    dialoog.get_by_role("button", name="Invoegen", exact=True).click()
    page.wait_for_function(
        f"() => document.querySelector('#cp-trix figure[data-trix-attachment*=\\\"{alt}\\\"]')",
        timeout=5000,
    )


@pytest.fixture
def pagina_met_beeld(editor):
    scherm = Paginascherm(editor).open_eerste()
    if scherm is None:
        _ontbreekt("geen cms-pagina op deze omgeving")
    _leeg(editor)
    _voeg_in(editor, "Half", "Beeld half")
    editor.locator("#cp-trix figure.attachment").first.click()
    expect(editor.locator("[data-raak-beeld-bewerken]").first).to_be_visible()
    return scherm


# ── 1. De knop leest als een knop ───────────────────────────────────────────


def test_de_bewerkknop_heeft_een_eigen_achtergrond(editor, pagina_met_beeld):
    """Het gemelde gebrek. Zonder eigen achtergrond hangt de leesbaarheid af van
    de foto eronder, en die kan donker zijn."""
    stijl = editor.evaluate("""() => {
      const b = document.querySelector('[data-raak-beeld-bewerken]');
      const s = getComputedStyle(b);
      return {achtergrond: s.backgroundColor, kleur: s.color};
    }""")

    assert stijl["achtergrond"] not in ("rgba(0, 0, 0, 0)", "transparent"), (
        f"de knop heeft geen eigen achtergrond ({stijl['achtergrond']}) en leest "
        "dus als kale tekst over het beeld — precies de melding van #1230"
    )


def test_de_bewerkknop_staat_op_dezelfde_hoogte_als_het_kruisje(editor, pagina_met_beeld):
    """Dezelfde hoogte en dezelfde bovenkant: de twee horen als één bediening te
    lezen. De breedte verschilt, want in de ene staat een woord en in de andere
    een symbool."""
    m = editor.evaluate("""() => {
      const doos = (el) => { const r = el.getBoundingClientRect();
        return {top: Math.round(r.top), hoogte: Math.round(r.height),
                links: Math.round(r.left), rechts: Math.round(r.right)}; };
      return {kruisje: doos(document.querySelector('.trix-button--remove')),
              bewerken: doos(document.querySelector('[data-raak-beeld-bewerken]'))};
    }""")

    assert m["bewerken"]["hoogte"] == m["kruisje"]["hoogte"], f"de knoppen zijn niet even hoog: {m}"
    assert abs(m["bewerken"]["top"] - m["kruisje"]["top"]) <= 1, (
        f"de knoppen staan niet op dezelfde bovenkant: {m}"
    )
    assert m["bewerken"]["links"] >= m["kruisje"]["rechts"], (
        f"de knoppen overlappen elkaar: {m} — een trefvlak over een knop die "
        "iets wist, is gevaarlijker dan een kleine knop"
    )


def test_de_bewerkknop_heeft_een_toegankelijke_naam(editor, pagina_met_beeld):
    """De val van #1230, punt 4: de UI-poort leest SJABLONEN en ziet deze knop
    niet, want hij ontstaat in JavaScript. Groen betekent daar dus niets over dit
    ding, en deze test vervangt die dekking."""
    naam = editor.evaluate("""() => {
      const b = document.querySelector('[data-raak-beeld-bewerken]');
      return (b.getAttribute('aria-label') || b.textContent || '').trim();
    }""")

    assert naam, "de bewerkknop heeft geen toegankelijke naam"
    assert len(naam) > 2, (
        f"de naam {naam!r} is te kort om iets te zeggen; is het een symboolknop "
        "geworden, geef haar dan een aria-label"
    )


# ── 2. De maat is in de editor te zien ──────────────────────────────────────


def _breedtes(page) -> dict:
    return page.evaluate("""() => {
      const uit = {};
      for (const f of document.querySelectorAll('#cp-trix figure.attachment')) {
        const d = JSON.parse(f.getAttribute('data-trix-attachment'));
        uit[d.alt] = Math.round(f.getBoundingClientRect().width);
      }
      uit.editor = Math.round(
        document.getElementById('cp-trix').getBoundingClientRect().width);
      return uit;
    }""")


def test_klein_is_in_de_editor_smaller_dan_half_en_vol(editor, pagina_met_beeld):
    """Gemeten op de gerenderde editor, niet op de klassenaam.

    Een benadering: de editorkolom is niet de tekstkolom van de pagina, dus het
    gaat om de VERHOUDING, niet om een pixelmaat.
    """
    _leeg(editor)
    for maat, alt in (
        ("Klein", "Beeld klein"),
        ("Half", "Beeld half"),
        ("Volle breedte", "Beeld vol"),
    ):
        _voeg_in(editor, maat, alt)

    m = _breedtes(editor)

    assert m["Beeld klein"] < m["Beeld half"] < m["Beeld vol"], (
        f"de drie maten zijn in de editor niet oplopend: {m} — je kiest klein en "
        "ziet groot, precies de tweede melding van #1230"
    )
    assert m["Beeld vol"] > m["editor"] * 0.8, f"volle breedte vult de editor niet: {m}"


def test_de_maat_wijzigen_verandert_de_weergave_meteen(editor, pagina_met_beeld):
    """Punt 6: bewerken werkt door in wat je ziet, niet pas na publiceren."""
    voor = _breedtes(editor)["Beeld half"]

    # NIET opnieuw op de figuur klikken: de fixture heeft haar al geselecteerd, en
    # een tweede klik heft die selectie op. `editingAttachment` is dan leeg en
    # Bijwerken doet niets — gemeten, het kostte een test die "size":"half" bleef
    # zien terwijl de knop wel degelijk werkte.
    editor.locator("[data-raak-beeld-bewerken]").first.click()
    dialoog = editor.get_by_role("dialog")
    expect(dialoog).to_be_visible()
    dialoog.get_by_role("button", name="Klein", exact=True).click()
    dialoog.get_by_role("button", name="Bijwerken", exact=True).click()
    editor.wait_for_function(
        """() => {
             const f = document.querySelector('#cp-trix figure.attachment');
             return f && JSON.parse(f.getAttribute('data-trix-attachment')).size === 'klein';
           }""",
        timeout=5000,
    )

    na = _breedtes(editor)["Beeld half"]
    assert na < voor, f"de weergave veranderde niet mee: {voor} px → {na} px"


def test_een_onbekende_maat_levert_ook_in_de_editor_niets_op(editor, pagina_met_beeld):
    """Punt 7, en het is de reden dat de editor uit dezelfde opgeslagen waarde
    leest in plaats van een eigen vertaling te maken."""
    _leeg(editor)
    editor.evaluate("""() => {
      const ed = document.getElementById('cp-trix').editor;
      ed.insertAttachment(new Trix.Attachment({
        url: '/api/v1/media/3', contentType: 'image', alt: 'Stiekem',
        size: 'reus', width: 240, height: 150 }));
    }""")
    editor.wait_for_function(
        "() => document.querySelector('#cp-trix figure.attachment')", timeout=5000
    )

    m = _breedtes(editor)
    assert m["Stiekem"] > m["editor"] * 0.8, (
        f"een onbekende maat kreeg toch opmaak: {m} — dan bestaat er een tweede, "
        "soepelere vertaling naast de vaste lijst van #1207"
    )
