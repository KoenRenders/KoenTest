"""E2E: gedicteerde tekst laat het invoerveld meegroeien (#788).

De tekst kwam altijd al aan — het veld groeide alleen niet mee, zodat een ingesproken
zin uit beeld liep. Typte je daarna zelf één teken bij, dan sprong het alsnog open.

**De oorzaak is één regel JavaScript-gedrag:** `input.value = t` vuurt géén
`input`-gebeurtenis, en het meegroeien hangt daaraan (`x-on:input` in het gedeelde
Raakje-invoerdeel, `_raakje_controls.html`). Typen vuurt ze wel — vandaar het verschil.

**Daarom toetst dit op de HOOGTE en niet op de waarde.** Een test op de waarde stond
al die tijd groen; die kon dit niet zien.

**En daarom draait dit door de echte keten.** De knop start de mic, de worklet stuurt
PCM naar onze eigen WebSocket, de mock-provider transcribeert en `stt.js` schrijft het
resultaat in het veld. Zou de test in plaats daarvan zelf `value` zetten en de
gebeurtenis afvuren, dan toetst ze de template en niet de reparatie. De opstelling
vraagt daarvoor `STT_MODE=native_first` plus `STT_PROVIDER=mock` (zonder een modus
met provider blijft de knop verborgen, want headless Chromium heeft geen
`SpeechRecognition`) en een nepmicrofoon in Chromium.

**Wat de mock-provider bijzonder maakt, en waarom dat hier goed uitkomt.** Ze levert
een partial per audioblok die opstapelt tot honderden tekens, en daarna een KORTE
eindtekst ("mock transcriptie") die de hele opbouw vervangt. Dat geeft precies twee
meetpunten: tijdens het dicteren moet het veld méé groeien, en na het stoppen moet het
de kortere tekst wéér volgen. Dat tweede is geen extraatje — het is het bewijs dat ook
`onFinal` de gebeurtenis afvuurt. Zonder die tweede aanroep zou het veld op 120 px
blijven staan met drie woorden erin.

**Sinds #1075 ook op de Raakje-overlay van het activiteitenscherm.** Die draagt
dezelfde microfoon uit hetzelfde partial, maar zit in een `x-show`-dialoog op een
beheerscherm: een knop die in een verborgen overlay niet bedraad raakt, of een veld dat
daar niet meegroeit, ziet de publieke test niet. De overlay-test doorloopt dus dezelfde
keten — knop, worklet, WebSocket, mock — op `#aa-raakje-vraag`, als beheerder, met de
beheer-assistent aan (`ADMIN_CHAT_ENABLED` plus de tenantschakelaar uit `seed_e2e.py`).
Dat de vier Raakje-plekken hetzelfde partial gebruiken bewijst
`tests/test_raakje_controls_shared.py`; hier staat alleen wat een browser moet tonen.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: het `dispatchEvent`
in `schrijf()` weggehaald → de eerste twee vallen om (de tekst staat er, het veld
beweegt niet); de `hx-on::after-request` die de hoogte terugzet weggehaald → de derde
valt om.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (BASE, Activiteitdetail, login_met_sessie,  # noqa: E402
                                pagina_klaar)
from tests_e2e.test_beheer_flows import _admin_email, _ontbreekt  # noqa: E402

PUBLIEK = "#raakje-vraag"
OVERLAY = "#aa-raakje-vraag"


@pytest.fixture(scope="module")
def page():
    """Chromium met een nepmicrofoon, en zonder Web Speech API.

    De nepmicrofoon levert een toon, dus de VAD hoort energie en de opname loopt.

    De Web Speech API gaat er bewust uit. Chromium levert `SpeechRecognition` én
    `webkitSpeechRecognition` gewoon (gemeten: allebei aanwezig), en `stt.js` kiest bij
    `native_first` dán het native pad — dat van onze reparatie niets aanraakt. De
    zustertest bij #762 doet het omgekeerde en zet er juist een na; zo bepaalt elke
    test zelf welk pad ze toetst in plaats van dat de serverinstelling dat voor beide
    doet.
    """
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        argumenten = ["--use-fake-device-for-media-stream",
                      "--use-fake-ui-for-media-stream"]
        browser = (pw.chromium.launch(executable_path=exe, args=argumenten) if exe
                   else pw.chromium.launch(args=argumenten))
        ctx = browser.new_context(base_url=BASE, permissions=["microphone"])
        ctx.add_init_script("delete window.SpeechRecognition;"
                            " delete window.webkitSpeechRecognition;")
        yield ctx.new_page()
        browser.close()


def _open(page, veld_selector: str = PUBLIEK):
    """Laadt het scherm en geeft (veld, hoogte mét handler, natuurlijke hoogte).

    Er zijn twee "één regel"-hoogtes en ze schelen twee pixels: 38 px tekent de
    browser voor een `rows=1`-textarea, 36 px zet de handler erop zodra hij één keer
    gelopen heeft. Zonder dat onderscheid meet je een geslaagde reparatie als krimp,
    of je verwart de terugzetting na het verzenden (die op `auto` zet, dus 38) met een
    veld dat hoog blijft staan.
    """
    if veld_selector == PUBLIEK:
        page.goto("/raakje")
        pagina_klaar(page)
    else:
        _open_de_overlay(page)
    veld = page.locator(veld_selector)
    natuurlijk = veld.bounding_box()["height"]
    page.evaluate("""(s) => document.querySelector(s)
        .dispatchEvent(new Event('input', { bubbles: true }))""", veld_selector)
    # #997: the handler has run once it has set an inline height.
    page.wait_for_function(
        "(s) => document.querySelector(s).style.height !== ''", arg=veld_selector,
        timeout=5000)
    return veld, veld.bounding_box()["height"], natuurlijk


def _open_de_overlay(page):
    """Als beheerder naar een activiteit, en de Raakje-overlay open (#1075).

    De knop bestaat alleen als de beheer-assistent aan staat (CR-07 §6.3). Onder de
    e2e-seed hoort hij er te zijn; ontbreekt hij daar, dan is dat een bevinding en
    geen skip (#644).
    """
    from app.domains.auth.api import make_session_value

    login_met_sessie(page, make_session_value(_admin_email()))
    if not Activiteitdetail(page).open_eerste():
        _ontbreekt("geen activiteit om te openen")
    pagina_klaar(page)
    knop = page.get_by_role("button", name="AI · Activiteit")
    if knop.count() == 0:
        _ontbreekt("geen AI · Activiteit-knop — staat de beheer-assistent aan "
                   "(ADMIN_CHAT_ENABLED én de tenantschakelaar)?")
    knop.click()
    page.wait_for_selector(OVERLAY, state="visible", timeout=5000)


def _hoogte_wordt(page, voorwaarde: str, arg, melding: str,
                  veld_selector: str = PUBLIEK) -> None:
    """Wait until the field's height meets `voorwaarde` (`(h, a) => …`) — #997.

    The height must BECOME so; a timeout is the finding, reported as `melding`.
    """
    try:
        page.wait_for_function(
            f"a => ({voorwaarde})(document.querySelector('{veld_selector}')"
            f".getBoundingClientRect().height, a)", arg=arg, timeout=5000)
    except Exception as fout:
        raise AssertionError(melding) from fout


def _knop(page, veld_selector: str = PUBLIEK):
    knop = page.locator(f"[data-stt-target='{veld_selector}']")
    assert knop.count() == 1, (
        "de spraakknop staat er niet — staat STT_MODE op een modus met provider?")
    return knop


def _dicteer_tot_lang(page, hoogte_leeg, veld_selector: str = PUBLIEK):
    """Start de opname en wacht tot er een lange tekst staat **en** het veld gegroeid is.

    Als één wachtvoorwaarde en niet als meting-daarna, en dat is geen stijlkeuze. De
    nepmicrofoon van Chromium piept met tussenpozen, dus de VAD kan tijdens het wachten
    zijn stilte-drempel halen en de opname zelf afsluiten — en dan vervangt de korte
    eindtekst van de mock de hele opbouw. Een meting ná het wachten zag dat als "niet
    gegroeid": gemeten viel deze test zo één keer op de veertig om. Als voorwaarde
    kijkt hij naar het moment zelf, en een uitblijvende groei loopt gewoon in de
    timeout.

    Ruim boven één regel: het veld is een paar honderd pixels breed, dus een korte zin
    past er nog in en zou niets over meegroeien zeggen. De mock levert een partial per
    audioblok, dus dit is binnen een seconde bereikt.
    """
    _knop(page, veld_selector).click()
    page.wait_for_function(
        """([basis, s]) => {
             const v = document.querySelector(s);
             return v.value.length > 300 && v.offsetHeight > basis;
           }""",
        arg=[hoogte_leeg, veld_selector], timeout=15000)


def _stop_zoals_de_app(page):
    """Sluit de opname af via het pad dat de app zelf gebruikt bij een tab-wissel.

    Niet door nog eens op de knop te klikken: is de VAD ons voor geweest, dan START
    die tweede klik een nieuwe opname in plaats van de lopende te stoppen.
    """
    page.evaluate("""() => {
      Object.defineProperty(document, 'hidden', { value: true, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    }""")


def test_tijdens_het_dicteren_groeit_het_veld_mee(page):
    """`onPartial` schrijft tussentijds mee; groeit het veld pas aan het eind, dan zie
    je tijdens het inspreken nog steeds niet wat je zegt."""
    veld, hoogte_leeg, _natuurlijk = _open(page)

    _dicteer_tot_lang(page, hoogte_leeg)

    hoogte_vol = veld.bounding_box()["height"]
    _stop_zoals_de_app(page)
    assert hoogte_vol <= 130, (
        f"het veld groeit ongeremd door ({hoogte_vol}px); boven ~120px hoort het te "
        "scrollen")


def test_het_veld_volgt_ook_de_eindtekst(page):
    """De tweede aanroep telt evengoed: `onFinal` vervangt de tekst.

    Bij de mock is die eindtekst kort, dus het veld hoort weer te krimpen. Vuurt
    alleen `onPartial` de gebeurtenis af, dan blijft het op 120 px staan met drie
    woorden erin — even fout, alleen andersom.
    """
    veld, hoogte_leeg, _natuurlijk = _open(page)
    _dicteer_tot_lang(page, hoogte_leeg)

    _stop_zoals_de_app(page)
    page.wait_for_function(
        "() => document.querySelector('#raakje-vraag').value.length < 100", timeout=10000)

    _hoogte_wordt(page, "(h, a) => h === a", hoogte_leeg,
                  "het veld blijft hoog terwijl de eindtekst op één regel past")


def test_na_verzenden_staat_het_veld_weer_op_een_regel(page):
    """De tegenproef op het geheel: zonder haar staan de twee tests hierboven ook
    groen wanneer het veld na gebruik nooit meer dichtgaat."""
    veld, hoogte_leeg, natuurlijk = _open(page)
    veld.fill("Ik heb een vrij lange vraag over het lidmaatschap. " * 4)
    _hoogte_wordt(page, "(h, a) => h > a", hoogte_leeg,
                  "voorwaarde van deze test: het veld groeit niet mee")

    veld.press("Enter")
    page.wait_for_function(
        "() => document.querySelector('#raakje-vraag').value === ''", timeout=10000)
    try:
        page.wait_for_function(
            "() => document.querySelector('#raakje-vraag').style.height === 'auto'",
            timeout=5000)
    except Exception as fout:
        raise AssertionError("de hoogte wordt na het verzenden niet teruggezet") from fout

    # De terugzetting gebeurt met `height = auto`, dus je landt op de natuurlijke
    # hoogte van 38 en niet op de 36 die de handler zou zetten. Waar het om gaat is
    # dat het veld weer één regel is en niet op zijn 120 px blijft staan.
    assert veld.bounding_box()["height"] <= natuurlijk, (
        "het veld blijft hoog terwijl het leeg is")
    assert veld.evaluate("el => el.style.height") == "auto", (
        "de hoogte wordt na het verzenden niet teruggezet")


# ── De Raakje-overlay van het activiteitenscherm (#1075) ─────────────────────
#
# Hetzelfde partial, maar een andere plek: een dialoog die met `x-show` verborgen
# begint, op een beheerscherm dat via hx-boost binnenkomt. `stt.js` bedraadt zijn
# knoppen bij het laden én na elke swap; dat dat ook voor een knop in een nog
# verborgen overlay geldt, en dat het veld daar even goed meegroeit, ziet alleen een
# browser. (Dat de handler op één plek staat, bewijst tests/test_raakje_controls_shared.py.)

def test_op_de_activiteit_overlay_groeit_het_veld_mee_tijdens_het_dicteren(page):
    veld, hoogte_leeg, _natuurlijk = _open(page, OVERLAY)

    _dicteer_tot_lang(page, hoogte_leeg, OVERLAY)

    hoogte_vol = veld.bounding_box()["height"]
    _stop_zoals_de_app(page)
    assert hoogte_vol <= 130, (
        f"het overlay-veld groeit ongeremd door ({hoogte_vol}px); boven ~120px hoort "
        "het te scrollen")


def test_op_de_activiteit_overlay_volgt_het_veld_ook_de_eindtekst(page):
    veld, hoogte_leeg, _natuurlijk = _open(page, OVERLAY)
    _dicteer_tot_lang(page, hoogte_leeg, OVERLAY)

    _stop_zoals_de_app(page)
    page.wait_for_function(
        "(s) => document.querySelector(s).value.length < 100", arg=OVERLAY, timeout=10000)

    _hoogte_wordt(page, "(h, a) => h === a", hoogte_leeg,
                  "het overlay-veld blijft hoog terwijl de eindtekst op één regel past",
                  OVERLAY)
