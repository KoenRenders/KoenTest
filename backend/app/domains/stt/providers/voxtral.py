"""Voxtral Realtime-adapter (Mistral AI, EU) — #282.

Gebruikt de **officiële** ``mistralai[realtime]``-SDK
(``client.audio.realtime.transcribe_stream``) — model
``voxtral-mini-transcribe-realtime-2602``, audio ``pcm_s16le`` @ 16 kHz mono.
De ``MISTRAL_API_KEY`` gaat naar de SDK en blijft serverside; de browser praat
enkel met onze eigen proxy.

Bewust **lazy geïmporteerd** (net zoals de chat-provider geen SDK-dep hardcodeert):
``check_imports``/CI blijven groen zonder de SDK, en dit pad wordt enkel actief met
``STT_PROVIDER=voxtral`` + een provider-modus (``STT_MODE=native_first``/
``provider_only``). Om het live te zetten op een host: ``pip install
mistralai[realtime]`` + de juiste ``STT_MODE``, plus een HDEV-smoke tegen de live
endpoint.

Contract naar de route: elke ``TranscriptionStreamTextDelta`` → een ``partial``
``TranscriptEvent`` met de incrementele tekst; ``TranscriptionStreamDone`` → een
``final`` met de volledige (samengevoegde) transcriptie.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from .base import SttProvider, TranscriptEvent

logger = logging.getLogger(__name__)


class VoxtralRealtimeProvider(SttProvider):
    name = "voxtral"

    def __init__(self, api_key: str, model: str, base_url: str, sample_rate: int,
                 language: str = ""):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._sample_rate = sample_rate
        self._language = (language or "").strip()

    async def stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[TranscriptEvent]:
        try:
            from mistralai.client import Mistral
            from mistralai.client.models import (
                AudioFormat,
                RealtimeTranscriptionError,
                TranscriptionStreamDone,
                TranscriptionStreamTextDelta,
            )
        except ImportError as exc:  # pragma: no cover - enkel zonder de extra
            raise RuntimeError(
                "De Voxtral-adapter vereist de mistralai[realtime]-SDK "
                "(pip install mistralai[realtime])."
            ) from exc

        client = Mistral(api_key=self._api_key)
        audio_format = AudioFormat(encoding="pcm_s16le", sample_rate=self._sample_rate)

        # Taal forceren (#295). De realtime-SDK toont in haar voorbeelden geen
        # language-parameter; we geven hem DEFENSIEF mee: accepteert transcribe_stream
        # hem (named of via **kwargs), dan blijft de transcriptie Nederlands; gooit hij
        # een TypeError ("unexpected keyword argument"), dan vallen we terug op
        # autodetectie zonder te crashen. Zo beslist de live endpoint, niet een gok.
        def _open_stream():
            kwargs = dict(
                audio_stream=audio,
                model=self._model,
                audio_format=audio_format,
                server_url=self._base_url,
            )
            if self._language:
                try:
                    return client.audio.realtime.transcribe_stream(language=self._language, **kwargs)
                except TypeError:
                    logger.info("Voxtral: language-parameter niet ondersteund door de SDK; autodetectie.")
            return client.audio.realtime.transcribe_stream(**kwargs)

        full: list[str] = []
        async for event in _open_stream():
            if isinstance(event, TranscriptionStreamTextDelta):
                full.append(event.text)
                yield TranscriptEvent(text=event.text, is_final=False)
            elif isinstance(event, TranscriptionStreamDone):
                yield TranscriptEvent(text="".join(full), is_final=True)
                break
            elif isinstance(event, RealtimeTranscriptionError):
                raise RuntimeError(
                    f"Voxtral realtime fout: {getattr(event, 'error', event)}"
                )
            # RealtimeTranscriptionSessionCreated / UnknownRealtimeEvent → negeren
