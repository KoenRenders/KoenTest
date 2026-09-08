"""#751 — de AudioContext wordt niet meer op een vaste sample rate gezet.

Firefox weigert een microfoonstroom te koppelen aan een context met een andere
snelheid, met zoveel woorden:

    NotSupportedError — AudioContext.createMediaStreamSource: Connecting AudioNodes
    from AudioContexts with different sample-rate is currently not supported.

Een kaart op Linux levert vrijwel altijd 48 kHz (PipeWire) en de context stond op
16 kHz. Chrome herbemonstert stilzwijgend; daar viel het nooit op.

**Waarom dit een brontest is en geen browsertest.** Het gedrag hangt aan een
microfoon met een ándere snelheid dan de context, en een nepapparaat in een
container levert gewoon de snelheid van de context — precies waarom mijn eerdere
meting niets vond. Wat wél te toetsen valt, is dat de context zonder vaste snelheid
gemaakt wordt en dat de worklet herbemonstert. Dat laatste staat als browsertest in
`tests_e2e/test_stt_worklet.py`, waar de echte worklet met een gestubde
`sampleRate` gedraaid wordt.

Kapotgemaakt om te controleren dat deze test rood kan worden: `new AudioContext()`
terug op `new AudioContext({ sampleRate: 16000 })` → de eerste test valt om.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_agnostisch

STT = (Path(__file__).resolve().parents[1] / "app/static/stt.js").read_text()
WORKLET = (Path(__file__).resolve().parents[1]
           / "app/static/stt-pcm-worklet.js").read_text()


def test_de_context_krijgt_geen_vaste_sample_rate():
    """De regel die de storing veroorzaakte."""
    assert "new AudioContext()" in STT, "de context wordt niet zonder opties gemaakt"
    assert "sampleRate:" not in STT, (
        "de AudioContext wordt weer op een vaste snelheid gezet; Firefox weigert dan "
        "de microfoon te koppelen (#751)")


def test_de_worklet_herbemonstert_naar_16_khz():
    """De tegenhanger: zonder herbemonstering krijgt Voxtral de verkeerde snelheid.

    Zonder deze test zou "haal de sampleRate weg" ook groen staan, en dan stuurt de
    browser 48 kHz naar een dienst die 16 kHz verwacht — een storing die je pas hoort
    aan de transcriptie.
    """
    assert "DOEL_RATE = 16000" in WORKLET
    assert "sampleRate / DOEL_RATE" in WORKLET, "er wordt niet herbemonsterd"


def test_de_foutafhandeling_noemt_de_stap():
    """Vier stappen, vier meldingen. Ze hingen alle aan dezelfde catch, en dat is de
    reden dat deze storing vier vermoedens kostte: de code kende de reden en zei niet
    wélke stap ze betrof."""
    for stap in ("de audiocontext aanmaken", "de worklet laden",
                 "de microfoon koppelen", "de audiograaf opzetten"):
        assert stap in STT, f"de stap '{stap}' heeft geen eigen melding"
