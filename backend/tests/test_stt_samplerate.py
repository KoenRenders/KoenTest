"""#751/#772 — wie herbemonstert, en wat krijgt Voxtral te horen?

De reeks in het kort. #751 haalde de vaste 16 kHz van de `AudioContext` af, omdat
Firefox weigert een microfoonstroom te koppelen aan een context met een andere
snelheid:

    NotSupportedError — AudioContext.createMediaStreamSource: Connecting AudioNodes
    from AudioContexts with different sample-rate is currently not supported.

Daarmee startte de spraakinvoer weer, maar wij herbemonsterden vanaf dat moment zelf
— lineair en zonder anti-aliasfilter. Gemeten op die versie, met een raster van
125 Hz over de uitgang van de worklet: een toon van 10 kHz kwam terug op 6 kHz met
amplitude 0,25, even sterk als het origineel; 14 kHz kwam terug op 2 kHz, midden in
de spraakband. Nul demping. Voxtral kreeg tientallen audioblokken en stuurde nul
`transcription.text.delta` terug.

#772 haalt de resampler wég in plaats van er een filter bij te bouwen:

- **weg A** — vraag het aan de bron (16 kHz in de `getUserMedia`-constraints) en
  probeer de context daar ook op te zetten. Slaagt het koppelen, dan heeft de
  browser herbemonsterd, mét zijn eigen filter;
- **weg B** — lukt dat niet, dan draait alles op apparaatsnelheid en meldt de
  browser die snelheid aan de server, die ze doorgeeft aan Voxtral.

**Waarom proberen en niet uitlezen.** `getSettings().sampleRate` is precies wat je
hier zou willen. Gemeten met een nepapparaat in playwright-firefox: Chromium meldt
`sampleRate: 48000` en negeert `ideal: 16000`; Firefox levert het veld `sampleRate`
hélemaal niet. In de browser waar deze storing thuishoort is uitlezen dus geen
optie, en dan is een poging de enige eerlijke meting.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: de tweede poging
(`null`) uit `_openAudio` gehaald → de terugvaltest valt om; `Math.round(...)`
vervangen door een vaste `16000` → de meldtest valt om; het `start`-bericht in de
router genegeerd → de doorgeeftest valt om.
"""
import json
from pathlib import Path

import pytest

from app.config import settings
from app.domains.stt import router as stt_mod

pytestmark = pytest.mark.ui_agnostisch

STT = (Path(__file__).resolve().parents[1] / "app/static/stt.js").read_text()
WORKLET = (Path(__file__).resolve().parents[1]
           / "app/static/stt-pcm-worklet.js").read_text()


def test_de_browser_vraagt_zestien_khz_aan_de_bron():
    """Weg A. `ideal` en niet `exact`: gemeten geeft `exact: 16000` in Chromium een
    OverconstrainedError op een apparaat dat alleen 48 kHz kan, en dan start de
    spraakinvoer helemaal niet meer."""
    beperking = next(r for r in STT.splitlines() if "audio: { sampleRate:" in r)

    assert "ideal: DOEL_RATE" in beperking
    assert "exact" not in beperking, (
        "een harde eis op de sample rate laat de spraakinvoer niet starten op een "
        "apparaat dat die snelheid niet levert")


def test_er_is_een_terugval_op_de_apparaatsnelheid():
    """De randvoorwaarde uit #751, en de reden dat weg A veilig is om te proberen.

    Zonder de tweede poging zou een browser die 16 kHz aan de bron NIET levert weer
    een `NotSupportedError` krijgen bij het koppelen — precies de storing die #751
    oploste.
    """
    assert "var opties = [{ sampleRate: DOEL_RATE }, null];" in STT, (
        "er wordt maar één contextsnelheid geprobeerd")
    assert "new AudioContext()" in STT, "de terugval zet nog steeds een vaste snelheid"


def test_de_worklet_herbemonstert_niet_meer():
    """De kern van #772: geen eigen signaalbewerking meer.

    Deze test is bewust een verbod en geen gebod. Wat er wél gebeurt (Float32 naar
    Int16, plus de RMS) staat als browsertest in `tests_e2e/test_stt_worklet.py`;
    wat hier telt is dat er niemand meer aan de snelheid rekent.
    """
    assert "sampleRate" not in WORKLET, (
        "de worklet rekent weer met de sample rate — herbemonsteren hoort bij de "
        "browser, die het mét een anti-aliasfilter doet")
    assert "DOEL_RATE" not in WORKLET


def test_de_browser_meldt_de_snelheid_die_hij_echt_stuurt():
    """En niet een vaste 16000. Een vaste waarde die toevallig klopt bewijst niets —
    en zodra de terugval aanslaat, klopt ze niet meer."""
    assert '"start"' in STT and "sample_rate:" in STT
    assert "Math.round(self.ctx.sampleRate)" in STT, (
        "de gemelde snelheid komt niet uit de context waarop de worklet draait")


def test_de_foutafhandeling_noemt_de_stap():
    """Vier stappen, vier meldingen. Ze hingen alle aan dezelfde catch, en dat is de
    reden dat de storing van #751 vier vermoedens kostte: de code kende de reden en
    zei niet wélke stap ze betrof."""
    for stap in ("de audiocontext aanmaken", "de worklet laden",
                 "de microfoon koppelen", "de audiograaf opzetten"):
        assert stap in STT, f"de stap '{stap}' heeft geen eigen melding"


# ── Serverkant: wat de browser meldt, is wat Voxtral hoort ───────────────────


@pytest.fixture(autouse=True)
def _mock_provider(monkeypatch):
    monkeypatch.setattr(settings, "stt_mode", "native_first")
    monkeypatch.setattr(settings, "stt_provider", "mock")
    stt_mod.handshake_limiter.reset()
    stt_mod.audio_budget.reset()
    yield
    stt_mod.handshake_limiter.reset()
    stt_mod.audio_budget.reset()


@pytest.fixture
def gevraagde_snelheid(monkeypatch):
    """Vangt op met welke sample rate de provider geopend wordt."""
    gezien: list[int | None] = []
    echt = stt_mod.get_stt_provider

    def spion(sample_rate=None):
        gezien.append(sample_rate)
        return echt()

    monkeypatch.setattr(stt_mod, "get_stt_provider", spion)
    return gezien


def _praat(client, eerste, snelheid=None):
    with client.websocket_connect("/api/v1/stt/voxtral") as ws:
        if eerste == "start":
            ws.send_text(json.dumps({"type": "start", "sample_rate": snelheid}))
        else:
            ws.send_bytes(b"audio")
        ws.send_bytes(b"audio-chunk")
        ws.send_text(json.dumps({"type": "stop"}))
        while ws.receive_json()["type"] != "final":
            pass


def test_de_gemelde_snelheid_gaat_naar_de_provider(client, gevraagde_snelheid):
    """48 kHz erin, 48 kHz eruit — niet de serverinstelling van 16000."""
    _praat(client, "start", 48000)

    assert gevraagde_snelheid == [48000]


def test_een_ongeloofwaardige_snelheid_valt_terug_op_de_instelling(client,
                                                                  gevraagde_snelheid):
    """De waarde komt uit de browser en gaat door naar een externe dienst, dus ze
    wordt begrensd. Zonder deze grens zet een geknutselde client er `999999999` in.
    """
    for onzin in (999_999_999, 0, -48000, "48000", None, True):
        gevraagde_snelheid.clear()
        _praat(client, "start", onzin)
        assert gevraagde_snelheid == [settings.stt_sample_rate], (
            f"{onzin!r} werd niet geweigerd")


def test_een_client_die_niets_meldt_blijft_werken(client, gevraagde_snelheid):
    """De tegenproef op de vorige twee: een oude `stt.js` uit de cache begint meteen
    met audio. Die sessie hoort gewoon te lopen op de serverinstelling — en haar
    eerste audioblok mag niet zoekraken."""
    _praat(client, "audio")

    assert gevraagde_snelheid == [settings.stt_sample_rate]


def test_het_eerste_audioblok_telt_mee_voor_de_vangrails(client, monkeypatch):
    """Het eerste blok komt buiten de ontvanglus binnen (#772). Zou het de sessie- en
    dagbudgetten overslaan, dan is er een gat in de vangrail: stuur één groot blok en
    de cap doet niets."""
    monkeypatch.setattr(settings, "stt_max_session_bytes", 10)
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/stt/voxtral") as ws:
            ws.send_bytes(b"x" * 25)
            for _ in range(10):
                ws.receive_json()
    assert exc.value.code == 4413
