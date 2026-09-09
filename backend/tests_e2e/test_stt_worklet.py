"""E2E: de worklet zet audio om naar PCM16 — en herbemonstert niet (#751, #772).

**Dit hoort in een browser.** De worklet draait in de audio-thread; een servertest kan
er niet bij. Het echte bronbestand wordt hier ingeladen met een stub voor
`AudioWorkletProcessor` en `registerProcessor`, zodat `process()` getoetst wordt zoals
hij draait — niet een kopie ervan.

**Wat hier vroeger stond, en waarom het weg is.** Tussen #751 en #772 herbemonsterde
deze worklet zelf naar 16 kHz, lineair en zonder anti-aliasfilter. Gemeten op die
versie, met een raster van 125 Hz over de uitgang: een toon van 10 kHz kwam terug op
6 kHz met amplitude 0,25 — even sterk als het origineel — en 14 kHz op 2 kHz, midden
in de spraakband. Nul demping, want 48/16 is precies 3: de posities vielen op hele
samples en de interpolatie kreeg nooit een breukdeel te zien. Voxtral herkende in die
ruis geen spraak.

De drie tests die er toen stonden (lengte, RMS, nuldoorgangen van een 440 Hz-sinus)
waren correct en **ontoereikend**: een enkele toon onder de Nyquist-grens
herbemonstert altijd netjes, dus geen ervan kón dit zien. Dat is geen verwijt, het is
de blinde vlek die telt — en de les die #772 eruit trok is niet "toets beter" maar
"doe het niet zelf". Herbemonsteren is het werk van de browser.

Wat overblijft is dus wat de worklet nog wél doet: het aantal samples ongemoeid laten
(er wordt niets meer uitgedund), Float32 correct naar Int16 schalen, en de RMS
berekenen op precies de stroom die verstuurd wordt.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE  # noqa: E402

BRON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "app", "static", "stt-pcm-worklet.js")

# Voert de echte worklet uit met een gegeven ingangssnelheid en één blok sinus.
PROEF = """([bron, rate, n]) => {
  const uit = [];
  globalThis.sampleRate = rate;
  globalThis.AudioWorkletProcessor = class { constructor() { this.port = {
    postMessage: (bericht) => uit.push(bericht) }; } };
  globalThis.registerProcessor = (naam, klasse) => { globalThis.__klasse = klasse; };
  (0, eval)(bron);
  const proc = new globalThis.__klasse();
  const blok = new Float32Array(n);
  for (let i = 0; i < n; i++) blok[i] = Math.sin(2 * Math.PI * 440 * i / rate) * 0.5;
  proc.process([[blok]]);
  const m = uit[0];
  return {aantal: new Int16Array(m.pcm).length, rms: m.rms,
          eerste: Array.from(new Int16Array(m.pcm)).slice(0, 4)};
}"""


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(base_url=BASE)
        p.goto("/")
        yield p
        browser.close()


def _draai(page, rate, n):
    return page.evaluate(PROEF, [open(BRON).read(), rate, n])


def test_de_worklet_dunt_niets_meer_uit(page):
    """Wat erin gaat, gaat eruit — op elke snelheid.

    Dat is de kern van #772: de worklet is geen resampler meer. Zou hij het tóch weer
    worden, dan valt het aantal samples meteen op.
    """
    for rate in (16000, 44100, 48000):
        uit = _draai(page, rate, 384)
        assert uit["aantal"] == 384, (
            f"op {rate} Hz komen er {uit['aantal']} van de 384 samples uit — er wordt "
            "weer herbemonsterd")


def test_de_rms_hoort_bij_de_verstuurde_stroom(page):
    """De stiltedetectie rekent op wat er verstuurd wordt, niet op iets ernaast.

    Een sinus met amplitude 0,5 heeft een RMS van 0,5/√2 ≈ 0,354. Wijkt dit af, dan
    klopt de schaling naar Int16 niet of wordt er over de verkeerde reeks gerekend —
    en dan stopt de opname te vroeg of nooit.
    """
    uit = _draai(page, 48000, 480)

    assert 0.34 < uit["rms"] < 0.37, f"RMS {uit['rms']:.3f}, verwacht ~0,354"


def test_de_omzetting_naar_int16_klopt_op_het_teken(page):
    """Negatief schaalt op 0x8000 en positief op 0x7fff — anders klipt de ene helft
    of is de andere een sample te stil. Het eerste sample van een sinus is 0, het
    tweede positief."""
    uit = _draai(page, 16000, 128)

    assert uit["eerste"][0] == 0
    assert uit["eerste"][1] > 0
