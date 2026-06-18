"""Voxtral Realtime-adapter (Mistral AI, EU) — #282.

Praat met de Mistral Voxtral-Realtime-WebSocket (model
``voxtral-mini-transcribe-realtime-2602``) via een rauwe ``websockets``-client
(beschikbaar via ``uvicorn[standard]``). De ``MISTRAL_API_KEY`` gaat in de
Authorization-header en blijft dus serverside; de browser praat enkel met onze
eigen proxy, nooit rechtstreeks met Mistral.

Protocol (gecorroboreerd via secundaire bronnen — vLLM-implementatie + de Voxtral
Realtime-paper — maar ⚠️ TE BEVESTIGEN OP HDEV tegen de live Mistral-endpoint,
want de officiële docs zijn tijdens de bouw afgeschermd):

- **client → server:** ``input_audio_buffer.append`` (audio als base64),
  ``input_audio_buffer.commit`` (einde opname), sessieconfig via
  ``transcription_session.update`` (vLLM: ``session.update``).
- **server → client:** ``transcription.delta`` (partial; tekst in ``delta``),
  een ``...done``/``...completed``-event (final) en ``session.created`` bij start.
- **audio:** base64 **PCM16, 16 kHz mono** — de frontend moet de mic-audio dus
  naar 16 kHz mono PCM16 herbemonsteren vóór ze hierheen te streamen.

De mock-provider draait in CI/lokaal; dit pad wordt enkel actief met
``STT_PROVIDER=voxtral`` (of ``auto`` + key) en moet gesmoke-test worden vóór de
toggle live gaat — pas dan staat het schema definitief vast.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import AsyncIterator

from .base import SttProvider, TranscriptEvent

logger = logging.getLogger(__name__)


class VoxtralRealtimeProvider(SttProvider):
    name = "voxtral"

    def __init__(self, api_key: str, model: str, url: str):
        self._api_key = api_key
        self._model = model
        self._url = url

    async def stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[TranscriptEvent]:
        try:
            import websockets  # via uvicorn[standard]
        except ImportError as exc:  # pragma: no cover - enkel zonder de extra
            raise RuntimeError(
                "De Voxtral-adapter vereist de 'websockets'-library."
            ) from exc

        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with websockets.connect(self._url, additional_headers=headers) as ws:
            # Sessie configureren (model + audioformaat). Schema te bevestigen op HDEV.
            await ws.send(json.dumps({
                "type": "transcription_session.update",
                "session": {"model": self._model, "input_audio_format": "pcm16"},
            }))

            async def _send_audio() -> None:
                async for chunk in audio:
                    await ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(chunk).decode("ascii"),
                    }))
                # Einde opname → commit zodat de server kan afronden.
                await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

            sender = asyncio.create_task(_send_audio())
            try:
                async for raw in ws:
                    try:
                        event = json.loads(raw)
                    except (ValueError, TypeError):
                        continue
                    etype = str(event.get("type", ""))
                    if etype.endswith("delta"):
                        text = event.get("delta") or event.get("text") or ""
                        if text:
                            yield TranscriptEvent(text=text, is_final=False)
                    elif etype.endswith("completed") or etype.endswith("done"):
                        text = event.get("transcript") or event.get("text") or ""
                        yield TranscriptEvent(text=text, is_final=True)
                        break
            finally:
                sender.cancel()
