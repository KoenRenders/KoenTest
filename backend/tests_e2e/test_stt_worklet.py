"""E2E: de worklet herbemonstert naar 16 kHz (#751).

De oorzaak, met de woorden van Firefox zelf:

    NotSupportedError — AudioContext.createMediaStreamSource: Connecting AudioNodes
    from AudioContexts with different sample-rate is currently not supported.

De microfoon levert op Linux vrijwel altijd 48 kHz (PipeWire) en de context stond op
16 kHz. Chrome herbemonstert stilzwijgend; daarom werkte het daar en nergens anders.
De context draait nu op de snelheid van het apparaat en de worklet herbemonstert.

**Dit hoort in een browser.** De worklet draait in de audio-thread en gebruikt de
globale `sampleRate`; een servertest kan er niet bij. De echte bronbestanden worden
hier ingeladen met een stub voor `AudioWorkletProcessor` en `registerProcessor`, zodat
`process()` getoetst wordt zoals hij draait — niet een kopie ervan.

De tweede test is de randvoorwaarde die het makkelijkst sneuvelt: op een apparaat dat
16 kHz wél levert moet het een doorgeefluik blijven. Een herbemonstering die het
gelijke-snelheid-geval sloopt, ruilt de ene storing voor de andere.
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


def test_48_khz_wordt_teruggebracht_naar_16(page):
    """Het geval dat de storing gaf: 48 kHz in, een derde eruit."""
    uit = _draai(page, 48000, 384)

    assert uit["aantal"] == 128, (
        f"384 samples op 48 kHz horen er 128 op 16 kHz te worden, niet {uit['aantal']}")
    assert 0.2 < uit["rms"] < 0.5, (
        f"de RMS ({uit['rms']:.3f}) klopt niet voor een sinus van 0,5 — de "
        "stiltedetectie hoort op de HERBEMONSTERDE stroom te rekenen")


def test_16_khz_blijft_een_doorgeefluik(page):
    """De randvoorwaarde: een apparaat dat 16 kHz levert mag niet stukgaan."""
    uit = _draai(page, 16000, 128)

    assert uit["aantal"] == 128, "bij gelijke snelheid hoort er niets te veranderen"
    # Het eerste sample van een sinus is 0; het tweede al niet meer. Zou de lus een
    # halve stap verschoven zijn, dan zie je dat hier meteen.
    assert uit["eerste"][0] == 0
    assert uit["eerste"][1] > 0


def test_de_toonhoogte_blijft_staan(page):
    """Herbemonsteren mag het signaal niet uitrekken.

    Een 440 Hz-sinus van 384 samples op 48 kHz duurt 8 ms en bevat ~3,5 perioden.
    Na herbemonstering zijn dat 128 samples op 16 kHz — dezelfde 8 ms, dus nog
    steeds ~3,5 perioden. Wie de stap verkeerd om zet, krijgt er 1,2 of 10.
    """
    uit = page.evaluate(PROEF.replace(
        "return {aantal:", """
        const pcm = new Int16Array(m.pcm);
        let kruisingen = 0;
        for (let i = 1; i < pcm.length; i++) {
          if ((pcm[i - 1] < 0) !== (pcm[i] < 0)) kruisingen++;
        }
        return {kruisingen: kruisingen, aantal:"""),
        [open(BRON).read(), 48000, 384])

    # ~3,5 perioden → 7 nuldoorgangen; met wat speling voor de randen.
    assert 5 <= uit["kruisingen"] <= 9, (
        f"{uit['kruisingen']} nuldoorgangen — het signaal is uitgerekt of ingekort")
