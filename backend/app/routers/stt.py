"""Publiek WebSocket-endpoint voor spraak-naar-tekst (STT) — #282.

Fallback-pad voor browsers zonder (werkende) native Web Speech API (o.a. Firefox):
de browser streamt mic-audio (binaire frames) naar deze proxy, die ze via een
swapbare provider-laag naar **Voxtral Realtime** (Mistral, EU) doorzet en de
transcript-events terugstuurt als JSON (``{"type": "partial"|"final", "text": …}``).
De API-sleutel (gedeelde ``MISTRAL_API_KEY``) blijft serverside.

Hoofdschakelaar ``STT_VOXTRAL_ENABLED`` staat standaard UIT → de handshake wordt
geweigerd (zoals ``CHAT_ENABLED`` de chat-route 'onzichtbaar' houdt), zodat deze
code dark mee naar PROD mag. In CI/zonder key draait de provider-laag op de mock.

Vangrails (defense-in-depth, #282): handshake-rate-limit per IP, idle-timeout,
harde audio-cap per sessie én per IP/dag — een vastgelopen of misbruikte socket
kan zo nooit ongelimiteerd Voxtral-minuten opstoken.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketState

from app.config import settings
from app.domains.stt.guards import DailyAudioBudget, HandshakeRateLimiter, ws_client_ip
from app.domains.stt.providers import get_stt_provider

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stt"])

# Sluitcodes. 1008 (policy) voor pre-accept-weigeringen (uit / rate-limit /
# dagbudget) — de client ziet enkel een mislukte handshake en valt terug op tekst.
# Voor sessie-limieten gebruiken we de applicatie-range (4000-4999), analoog aan
# de HTTP-statussen, zodat de client de reden kan onderscheiden.
_WS_POLICY = 1008
_WS_NORMAL = 1000
_WS_IDLE = 4408           # ~ HTTP 408 Request Timeout
_WS_SESSION_CAP = 4413    # ~ HTTP 413 Payload Too Large

# Module-globale vangrails (per proces; reset-baar in tests).
handshake_limiter = HandshakeRateLimiter(settings.stt_ws_max_handshakes_per_min)
audio_budget = DailyAudioBudget(settings.stt_daily_audio_budget_bytes)


@router.websocket("/stt/voxtral")
async def stt_voxtral(websocket: WebSocket) -> None:
    # 1) Hoofdschakelaar + pre-accept-vangrails (geen kost als we hier weigeren).
    if not settings.stt_voxtral_enabled:
        await websocket.close(code=_WS_POLICY, reason="STT uitgeschakeld")
        return
    ip = ws_client_ip(websocket)
    if not handshake_limiter.allow(ip):
        await websocket.close(code=_WS_POLICY, reason="Te veel pogingen")
        return
    if audio_budget.exhausted(ip):
        await websocket.close(code=_WS_POLICY, reason="Daglimiet bereikt")
        return

    await websocket.accept()
    provider = get_stt_provider()

    audio_q: asyncio.Queue = asyncio.Queue()
    session_bytes = 0
    close_code = _WS_NORMAL
    close_reason = "Klaar"

    async def audio_iter():
        """Bridge: voedt de provider met de binnenkomende audiochunks tot ``None``
        het einde van de opname signaleert."""
        while True:
            chunk = await audio_q.get()
            if chunk is None:
                return
            yield chunk

    async def pump_transcripts() -> None:
        try:
            async for ev in provider.stream(audio_iter()):
                if websocket.application_state != WebSocketState.CONNECTED:
                    break
                await websocket.send_json(
                    {"type": "final" if ev.is_final else "partial", "text": ev.text}
                )
        except Exception as exc:  # provider-fout mag de socket niet hard laten crashen
            logger.warning("STT-provider mislukt: %s", exc)

    pump_task = asyncio.create_task(pump_transcripts())
    try:
        while True:
            try:
                msg = await asyncio.wait_for(
                    websocket.receive(), timeout=settings.stt_idle_timeout_seconds
                )
            except asyncio.TimeoutError:
                close_code, close_reason = _WS_IDLE, "Inactief"
                break

            if msg["type"] == "websocket.disconnect":
                break

            chunk = msg.get("bytes")
            text = msg.get("text")
            if chunk is not None:
                session_bytes += len(chunk)
                if session_bytes > settings.stt_max_session_bytes:
                    close_code, close_reason = _WS_SESSION_CAP, "Audiolimiet bereikt"
                    break
                if not audio_budget.charge(ip, len(chunk)):
                    close_code, close_reason = _WS_POLICY, "Daglimiet bereikt"
                    break
                await audio_q.put(chunk)
            elif text is not None:
                # Controleboodschap: {"type": "stop"} = einde opname.
                try:
                    ctrl = json.loads(text)
                except (ValueError, TypeError):
                    ctrl = {}
                if ctrl.get("type") == "stop":
                    break
    finally:
        # Signaleer einde-audio en laat de transcripts afronden, sluit dan netjes.
        await audio_q.put(None)
        try:
            await asyncio.wait_for(pump_task, timeout=10)
        except Exception:
            pump_task.cancel()
        if websocket.application_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=close_code, reason=close_reason)
            except RuntimeError:
                pass
