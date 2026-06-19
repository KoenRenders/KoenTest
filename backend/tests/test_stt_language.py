"""Voxtral-adapter forceert de taal defensief (#295).

De realtime-SDK toont in haar voorbeelden geen language-parameter; wij geven hem
mee als de SDK hem accepteert en vallen anders (TypeError) terug op autodetectie —
zonder te crashen. De echte SDK staat niet in CI, dus we injecteren een nep-module.
"""
import asyncio
import sys
import types

from app.config import settings


def test_stt_language_default_is_dutch():
    assert settings.stt_language == "nl"


def _install_fake_mistralai(monkeypatch, *, accept_language: bool, calls: dict):
    models = types.ModuleType("mistralai.client.models")

    class AudioFormat:
        def __init__(self, encoding, sample_rate):
            self.encoding, self.sample_rate = encoding, sample_rate

    class TranscriptionStreamTextDelta:
        def __init__(self, text):
            self.text = text

    class TranscriptionStreamDone:
        pass

    class RealtimeTranscriptionError:
        def __init__(self, error="x"):
            self.error = error

    models.AudioFormat = AudioFormat
    models.TranscriptionStreamTextDelta = TranscriptionStreamTextDelta
    models.TranscriptionStreamDone = TranscriptionStreamDone
    models.RealtimeTranscriptionError = RealtimeTranscriptionError

    client_mod = types.ModuleType("mistralai.client")

    class _Realtime:
        def transcribe_stream(self, **kwargs):
            calls["kwargs"] = kwargs
            if "language" in kwargs and not accept_language:
                raise TypeError("transcribe_stream() got an unexpected keyword argument 'language'")

            async def gen():
                yield TranscriptionStreamTextDelta("hallo ")
                yield TranscriptionStreamDone()

            return gen()

    class _Audio:
        def __init__(self):
            self.realtime = _Realtime()

    class Mistral:
        def __init__(self, api_key=None):
            self.audio = _Audio()

    client_mod.Mistral = Mistral

    monkeypatch.setitem(sys.modules, "mistralai", types.ModuleType("mistralai"))
    monkeypatch.setitem(sys.modules, "mistralai.client", client_mod)
    monkeypatch.setitem(sys.modules, "mistralai.client.models", models)


async def _empty_audio():
    if False:  # pragma: no cover - lege async-iterator
        yield b""


def _collect(provider):
    async def run():
        return [ev async for ev in provider.stream(_empty_audio())]
    return asyncio.run(run())


def test_language_passed_when_supported(monkeypatch):
    calls = {}
    _install_fake_mistralai(monkeypatch, accept_language=True, calls=calls)
    from app.domains.stt.providers.voxtral import VoxtralRealtimeProvider

    provider = VoxtralRealtimeProvider(
        api_key="k", model="m", base_url="wss://x", sample_rate=16000, language="nl"
    )
    events = _collect(provider)
    assert calls["kwargs"].get("language") == "nl"
    assert any(e.is_final for e in events)
    assert events[-1].text == "hallo "


def test_language_fallback_on_typeerror(monkeypatch):
    calls = {}
    _install_fake_mistralai(monkeypatch, accept_language=False, calls=calls)
    from app.domains.stt.providers.voxtral import VoxtralRealtimeProvider

    provider = VoxtralRealtimeProvider(
        api_key="k", model="m", base_url="wss://x", sample_rate=16000, language="nl"
    )
    events = _collect(provider)
    # Na de TypeError volgt een tweede call ZONDER language → transcriptie werkt nog.
    assert "language" not in calls["kwargs"]
    assert any(e.is_final for e in events)
