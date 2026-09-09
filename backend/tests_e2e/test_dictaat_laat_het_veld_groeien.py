"""E2E: gedicteerde tekst laat het invoerveld meegroeien (#788).

De tekst kwam altijd al aan — het veld groeide alleen niet mee, zodat een ingesproken
zin uit beeld liep. Typte je daarna zelf één teken bij, dan sprong het alsnog open.

**De oorzaak is één regel JavaScript-gedrag:** `input.value = t` vuurt géén
`input`-gebeurtenis, en het meegroeien hangt daaraan (`x-on:input` in de twee
raakje-templates). Typen vuurt ze wel — vandaar het verschil.

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

from tests_e2e.schermen import BASE  # noqa: E402

SJABLONEN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "app", "domains", "chatbot", "templates")


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


def _open(page):
    """Laadt het scherm en geeft (veld, hoogte mét handler, natuurlijke hoogte).

    Er zijn twee "één regel"-hoogtes en ze schelen twee pixels: 38 px tekent de
    browser voor een `rows=1`-textarea, 36 px zet de handler erop zodra hij één keer
    gelopen heeft. Zonder dat onderscheid meet je een geslaagde reparatie als krimp,
    of je verwart de terugzetting na het verzenden (die op `auto` zet, dus 38) met een
    veld dat hoog blijft staan.
    """
    page.goto("/raakje")
    page.wait_for_selector("#raakje-vraag", timeout=5000)
    veld = page.locator("#raakje-vraag")
    natuurlijk = veld.bounding_box()["height"]
    page.evaluate("""() => document.querySelector('#raakje-vraag')
        .dispatchEvent(new Event('input', { bubbles: true }))""")
    page.wait_for_timeout(100)
    return veld, veld.bounding_box()["height"], natuurlijk


def _knop(page):
    knop = page.locator("[data-stt-target='#raakje-vraag']")
    assert knop.count() == 1, (
        "de spraakknop staat er niet — staat STT_MODE op een modus met provider?")
    return knop


def _dicteer_tot_lang(page, hoogte_leeg):
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
    _knop(page).click()
    page.wait_for_function(
        """(basis) => {
             const v = document.querySelector('#raakje-vraag');
             return v.value.length > 300 && v.offsetHeight > basis;
           }""",
        arg=hoogte_leeg, timeout=15000)


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
    page.wait_for_timeout(200)

    assert veld.bounding_box()["height"] == hoogte_leeg, (
        "het veld blijft hoog terwijl de eindtekst op één regel past")


def test_na_verzenden_staat_het_veld_weer_op_een_regel(page):
    """De tegenproef op het geheel: zonder haar staan de twee tests hierboven ook
    groen wanneer het veld na gebruik nooit meer dichtgaat."""
    veld, hoogte_leeg, natuurlijk = _open(page)
    veld.fill("Ik heb een vrij lange vraag over het lidmaatschap. " * 4)
    page.wait_for_timeout(200)
    assert veld.bounding_box()["height"] > hoogte_leeg  # voorwaarde van deze test

    veld.press("Enter")
    page.wait_for_function(
        "() => document.querySelector('#raakje-vraag').value === ''", timeout=10000)
    page.wait_for_timeout(200)

    # De terugzetting gebeurt met `height = auto`, dus je landt op de natuurlijke
    # hoogte van 38 en niet op de 36 die de handler zou zetten. Waar het om gaat is
    # dat het veld weer één regel is en niet op zijn 120 px blijft staan.
    assert veld.bounding_box()["height"] <= natuurlijk, (
        "het veld blijft hoog terwijl het leeg is")
    assert veld.evaluate("el => el.style.height") == "auto", (
        "de hoogte wordt na het verzenden niet teruggezet")


def test_beide_schermen_dragen_dezelfde_groeihandler():
    """`stt.js` is gedeeld, de templates niet — de uitdrukking staat twee keer.

    De e2e hierboven draait op `/raakje`; deze regel legt vast dat de widget dezelfde
    handler draagt, zodat een wijziging niet één van de twee schermen repareert.
    """
    handler = ("x-on:input=\"$el.style.height = `auto`; "
               "$el.style.height = Math.min($el.scrollHeight, 120) + `px`\"")
    for naam in ("raakje.html", "_raakje_widget.html"):
        with open(os.path.join(SJABLONEN, naam)) as f:
            assert handler in f.read(), f"{naam} laat het veld niet meegroeien"
