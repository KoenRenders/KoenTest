"""Publiek WebSocket-endpoint voor spraak-naar-tekst (STT) — #282.

Fallback-pad voor browsers zonder (werkende) native Web Speech API (o.a. Firefox):
de browser streamt mic-audio naar deze proxy, die op zijn beurt naar **Voxtral
Realtime** (Mistral, EU) praat. De API-sleutel (gedeelde ``MISTRAL_API_KEY``)
blijft serverside; de browser praat nooit rechtstreeks met Mistral.

Dit is het **dark-launch-skelet** (eerste increment): de WS-infrastructuur en de
kill-switch staan op hun plaats, maar de eigenlijke stream-proxy naar Voxtral is
nog **niet** geïmplementeerd. ``STT_VOXTRAL_ENABLED`` staat standaard UIT → de
handshake wordt geweigerd, precies zoals ``CHAT_ENABLED`` de chat-route
'onzichtbaar' houdt. Zo kan deze code mee naar PROD zonder dat de feature live is.

De echte proxy (audio-frames in, transcript-events uit) plus de server-side
vangrails (handshake-rate-limit per IP, idle-timeout, harde audio-cap per sessie
én per IP/dag) volgen in latere increments en worden op HDEV gesmoke-test tegen
de live Voxtral-endpoint.
"""
import logging

from fastapi import APIRouter, WebSocket

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stt"])

# WebSocket-sluitcodes (RFC 6455).
_WS_POLICY_VIOLATION = 1008   # feature uitgeschakeld → handshake geweigerd
_WS_INTERNAL_ERROR = 1011     # aan, maar proxy nog niet geïmplementeerd (dark)


@router.websocket("/stt/voxtral")
async def stt_voxtral(websocket: WebSocket) -> None:
    """Dark-launch-skelet (#282).

    - ``STT_VOXTRAL_ENABLED`` uit → weiger de handshake (geen upgrade), zodat de
      client meteen terugvalt op tekstinvoer en er geen Voxtral-kost ontstaat.
    - aan (dark) → aanvaard en sluit netjes; de echte Voxtral-Realtime-proxy is
      hier nog niet geïmplementeerd.
    """
    if not settings.stt_voxtral_enabled:
        await websocket.close(code=_WS_POLICY_VIOLATION, reason="STT uitgeschakeld")
        return

    await websocket.accept()
    await websocket.close(code=_WS_INTERNAL_ERROR, reason="STT nog niet beschikbaar")
