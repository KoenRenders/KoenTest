"""#772 — een lege transcriptie kan drie dingen betekenen, en ze zagen er identiek uit.

Bij het onderzoek naar #772 leverde de spraakinvoer geen tekst. In de logs stond
daarover: niets. De keten deed netjes wat ze moest — audioblokken heen, een
`transcription.done` terug — en het enige wat ontbrak was tekst. Wat je dan NIET kan
zien is welke van deze drie het was:

1. de provider **weigerde het formaat** (bijvoorbeeld een sample rate die het model
   niet aanvaardt) — dat komt als fout boven;
2. de provider **aanvaardde het en herkende geen spraak** — dat is stil;
3. er is **niets ingesproken** — dat is óók stil, en het zegt niets over de provider.

Sinds #772 stuurt de browser bij het stoppen mee of zijn eigen VAD ooit energie boven
de drempel zag. Daarmee valt geval 3 van geval 2 te scheiden, en met de sample rate
erbij is de logregel genoeg om de volgende ronde te beginnen bij de juiste vraag in
plaats van bij alle drie.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `_log_uitkomst()`
uit de `finally` gehaald → alles behalve geval 1 valt om (dat wordt elders gelogd);
de `spraak`-vlag in de router genegeerd → geval 2 én geval 3 vallen om, want zonder
de vlag zijn ze niet meer van elkaar te onderscheiden — precies de verwarring die dit
moest wegnemen.
"""
import json
import logging
from typing import AsyncIterator

import pytest

from app.config import settings
from app.domains.stt import router as stt_mod
from app.domains.stt.providers.base import SttProvider, TranscriptEvent

pytestmark = pytest.mark.ui_agnostisch


class StilleProvider(SttProvider):
    """Aanvaardt alles en levert nooit een delta — geval 2."""

    name = "stil"

    async def stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[TranscriptEvent]:
        async for _chunk in audio:
            pass
        yield TranscriptEvent(text="", is_final=True)


class WeigerendeProvider(SttProvider):
    """Weigert het formaat — geval 1."""

    name = "weigert"

    async def stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[TranscriptEvent]:
        async for _chunk in audio:
            pass
        raise RuntimeError("Voxtral realtime fout: unsupported sample_rate")
        yield  # pragma: no cover - maakt dit een async generator


@pytest.fixture
def logregels():
    """Hangt rechtstreeks aan de logger van de route, en zet hem eerst weer aan.

    `caplog` levert hier niets op, en de reden is de moeite waard om op te schrijven:
    de testopstelling draait alembic **in hetzelfde proces**, en `alembic/env.py` doet
    `fileConfig(...)`. Die staat standaard op `disable_existing_loggers=True` en zet
    dus `disabled = True` op elke logger die op dat moment al bestond — deze inbegrepen.
    Gemeten: `stt_mod.logger.disabled` is `True` zodra de fixtures gedraaid hebben.

    In productie speelt dat niet: daar draait `alembic upgrade head` in `startup.sh`
    als een apart proces, vóór uvicorn. Het is dus een eigenaardigheid van de
    testopstelling en geen stille logstoring op de server — maar een test die dit niet
    weet, meet niets en staat groen.
    """
    regels: list[tuple[int, str]] = []

    class Vanger(logging.Handler):
        def emit(self, record):
            regels.append((record.levelno, record.getMessage()))

    vanger = Vanger()
    oud_niveau, oud_uit = stt_mod.logger.level, stt_mod.logger.disabled
    stt_mod.logger.addHandler(vanger)
    stt_mod.logger.setLevel(logging.INFO)
    stt_mod.logger.disabled = False
    yield regels
    stt_mod.logger.removeHandler(vanger)
    stt_mod.logger.setLevel(oud_niveau)
    stt_mod.logger.disabled = oud_uit


@pytest.fixture(autouse=True)
def _mock_provider(monkeypatch):
    monkeypatch.setattr(settings, "stt_mode", "native_first")
    monkeypatch.setattr(settings, "stt_provider", "mock")
    stt_mod.handshake_limiter.reset()
    stt_mod.audio_budget.reset()
    yield
    stt_mod.handshake_limiter.reset()
    stt_mod.audio_budget.reset()


def _sessie(client, provider=None, *, snelheid=48000, spraak=True, monkeypatch=None):
    if provider is not None:
        monkeypatch.setattr(stt_mod, "get_stt_provider", lambda sample_rate=None: provider)
    with client.websocket_connect("/api/v1/stt/voxtral") as ws:
        ws.send_text(json.dumps({"type": "start", "sample_rate": snelheid}))
        ws.send_bytes(b"audio-chunk")
        ws.send_text(json.dumps({"type": "stop", "spraak": spraak}))
        try:
            for _ in range(10):
                if ws.receive_json()["type"] == "final":
                    break
        except Exception:
            pass


def test_geval_1_de_provider_weigert(client, monkeypatch, logregels):
    """Een expliciete weigering komt als waarschuwing boven, mét de snelheid — want
    de snelheid is dan juist de verdachte."""
    _sessie(client, WeigerendeProvider(), monkeypatch=monkeypatch)

    berichten = [m for _lvl, m in logregels]
    assert any("STT-provider mislukt (48000 Hz)" in m for m in berichten), berichten
    assert not any("herkende geen spraak" in m for m in berichten), (
        "een weigering wordt óók als 'niets herkend' gemeld; dan is het onderscheid weg")


def test_geval_2_aanvaard_maar_niets_herkend(client, monkeypatch, logregels):
    """Geen fout van de provider, wél spraak volgens de browser, en toch geen tekst.

    Dit is het geval waarin de audio zelf de verdachte is — precies de situatie van
    #772 vóór de reparatie.
    """
    _sessie(client, StilleProvider(), spraak=True, monkeypatch=monkeypatch)

    zwaar = [m for lvl, m in logregels if lvl >= logging.WARNING]
    assert any("herkende geen spraak" in m and "48000 Hz" in m
               and "de browser hoorde wél spraak" in m for m in zwaar), logregels


def test_geval_3_er_is_niets_ingesproken(client, monkeypatch, logregels):
    """De browser meldt zelf dat zijn VAD niets hoorde. Dan zegt de lege transcriptie
    niets over de provider, en hoort er geen waarschuwing te staan die naar de
    verkeerde verdachte wijst."""
    _sessie(client, StilleProvider(), spraak=False, monkeypatch=monkeypatch)

    stil = [m for _lvl, m in logregels if "de browser hoorde" in m]
    assert stil and "zelf geen spraak" in stil[0], logregels
    assert all(lvl < logging.WARNING for lvl, m in logregels if "STT-sessie" in m), (
        "een sessie waarin niemand iets zei is geen waarschuwing")


def test_een_geslaagde_sessie_meldt_hoeveel_tekst(client, logregels):
    """De tegenproef: gaat het goed, dan hoort er géén waarschuwing te staan.

    Zonder deze test zou "log altijd een waarschuwing" ook groen staan, en dan is de
    waarschuwing waardeloos als signaal.
    """
    _sessie(client)

    assert any("STT-sessie klaar" in m and "tekstdelen" in m
               for _lvl, m in logregels), logregels
    assert all(lvl < logging.WARNING for lvl, m in logregels if "STT-sessie" in m)
