"""Publiek WebSocket-endpoint voor spraak-naar-tekst (STT) — #282.

Fallback-pad voor browsers zonder (werkende) native Web Speech API (o.a. Firefox):
de browser streamt mic-audio (binaire frames) naar deze proxy, die ze via een
swapbare provider-laag naar **Voxtral Realtime** (Mistral, EU) doorzet en de
transcript-events terugstuurt als JSON (``{"type": "partial"|"final", "text": …}``).
De API-sleutel (gedeelde ``MISTRAL_API_KEY``) blijft serverside.

De strategie ``STT_MODE`` bepaalt of de provider wordt aangesproken: bij
``browser_only`` (default) weigert de route de handshake (provider dark, code mag
mee naar PROD), bij ``native_first``/``provider_only`` accepteert ze. In CI/zonder
key draait de provider-laag op de mock (``STT_PROVIDER=mock``).

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

# #772: grenzen waarbinnen een door de CLIENT gemelde sample rate geloofwaardig is.
# De waarde komt uit de browser en gaat door naar een externe dienst, dus ze wordt
# begrensd en niet zomaar doorgegeven — 8 kHz is telefoonkwaliteit, 192 kHz is het
# hoogste dat consumentenhardware levert. Alles daarbuiten (of iets dat geen geheel
# getal is) valt terug op de serverinstelling.
_MIN_SAMPLE_RATE = 8000
_MAX_SAMPLE_RATE = 192000


class _Grens(Exception):
    """Een vangrail sloeg aan op het eerste audioblok, dat buiten de lus binnenkomt.

    Een `break` bestaat daar niet, en het opruimen in `finally` moet wél draaien —
    vandaar deze interne uitzondering in plaats van een tweede exemplaar van de
    afsluitcode.
    """

# Module-globale vangrails (per proces; reset-baar in tests).
handshake_limiter = HandshakeRateLimiter(settings.stt_ws_max_handshakes_per_min)
audio_budget = DailyAudioBudget(settings.stt_daily_audio_budget_bytes)

# STT_MODE-waarden waarin de provider (Voxtral) effectief wordt aangesproken; in
# 'browser_only' (default) blijft de provider dark en weigert de route.
_PROVIDER_MODES = ("native_first", "provider_only")


@router.websocket("/stt/voxtral")
async def stt_voxtral(websocket: WebSocket) -> None:
    # 1) Strategie + pre-accept-vangrails (geen kost als we hier weigeren).
    if settings.stt_mode not in _PROVIDER_MODES:
        await websocket.close(code=_WS_POLICY, reason="STT via provider niet actief")
        return
    ip = ws_client_ip(websocket)
    if not handshake_limiter.allow(ip):
        await websocket.close(code=_WS_POLICY, reason="Te veel pogingen")
        return
    if audio_budget.exhausted(ip):
        await websocket.close(code=_WS_POLICY, reason="Daglimiet bereikt")
        return

    await websocket.accept()

    audio_q: asyncio.Queue = asyncio.Queue()
    session_bytes = 0
    close_code = _WS_NORMAL
    close_reason = "Klaar"

    def boek_audio(chunk: bytes) -> tuple[int, str] | None:
        """Telt een audioblok mee op de sessie- en dagbudgetten.

        Geeft de sluitreden terug zodra een grens overschreden is, anders ``None``.
        Staat als functie los omdat het eerste blok buiten de lus binnen kan komen
        (zie hieronder) en de vangrails ook dáár moeten gelden.
        """
        nonlocal session_bytes
        session_bytes += len(chunk)
        if session_bytes > settings.stt_max_session_bytes:
            return _WS_SESSION_CAP, "Audiolimiet bereikt"
        if not audio_budget.charge(ip, len(chunk)):
            return _WS_POLICY, "Daglimiet bereikt"
        return None

    # #772: de browser meldt als eerste bericht met welke snelheid hij stuurt. Sinds
    # #772 herbemonstert hij niet meer zelf — dat deed hij zonder anti-aliasfilter, en
    # Voxtral herkende in het resultaat geen spraak — dus de snelheid is die van het
    # apparaat en verschilt per sessie. Ze moet bekend zijn vóór de provider-sessie
    # opengaat, want ze gaat als `AudioFormat` mee in de handshake met Voxtral.
    #
    # Een client die niets meldt (een oude versie uit de cache) krijgt de
    # serverinstelling en blijft dus werken; zijn eerste frame is dan al audio en gaat
    # gewoon mee.
    sample_rate = settings.stt_sample_rate
    eerste_audio: bytes | None = None
    try:
        eerste = await asyncio.wait_for(
            websocket.receive(), timeout=settings.stt_idle_timeout_seconds
        )
    except asyncio.TimeoutError:
        await websocket.close(code=_WS_IDLE, reason="Inactief")
        return
    if eerste["type"] == "websocket.disconnect":
        return
    if eerste.get("bytes") is not None:
        eerste_audio = eerste["bytes"]
    elif eerste.get("text") is not None:
        try:
            ctrl = json.loads(eerste["text"])
        except (ValueError, TypeError):
            ctrl = {}
        if ctrl.get("type") == "stop":
            await websocket.close(code=_WS_NORMAL, reason="Klaar")
            return
        gemeld = ctrl.get("sample_rate")
        if isinstance(gemeld, int) and not isinstance(gemeld, bool) \
                and _MIN_SAMPLE_RATE <= gemeld <= _MAX_SAMPLE_RATE:
            sample_rate = gemeld
        elif gemeld is not None:
            logger.warning("STT: ongeldige sample_rate %r; val terug op %d",
                           gemeld, sample_rate)
    logger.info("STT-sessie: %d Hz", sample_rate)

    provider = get_stt_provider(sample_rate=sample_rate)

    # #772: drie uitkomsten die er in de logs identiek uitzagen — de provider
    # weigerde het formaat, de provider aanvaardde het maar herkende geen spraak, of
    # er is niets ingesproken. Alle drie eindigen in een lege transcriptie. Ze uit
    # elkaar houden kostte dit onderzoek drie rondes, dus ze staan nu uit elkaar
    # gehaald in één regel aan het eind van de sessie.
    deltas = 0
    provider_fout: str | None = None
    spraak_gehoord: bool | None = None

    async def audio_iter():
        """Bridge: voedt de provider met de binnenkomende audiochunks tot ``None``
        het einde van de opname signaleert."""
        while True:
            chunk = await audio_q.get()
            if chunk is None:
                return
            yield chunk

    async def pump_transcripts() -> None:
        nonlocal deltas, provider_fout
        try:
            async for ev in provider.stream(audio_iter()):
                if not ev.is_final and ev.text:
                    deltas += 1
                if websocket.application_state != WebSocketState.CONNECTED:
                    break
                await websocket.send_json(
                    {"type": "final" if ev.is_final else "partial", "text": ev.text}
                )
        except Exception as exc:  # provider-fout mag de socket niet hard laten crashen
            provider_fout = str(exc)
            logger.warning("STT-provider mislukt (%d Hz): %s", sample_rate, exc)

    def _log_uitkomst() -> None:
        """Eén regel per sessie, die de drie stille uitkomsten uit elkaar houdt."""
        if provider_fout is not None:
            return  # al gemeld, mét de snelheid erbij
        if deltas:
            logger.info("STT-sessie klaar: %d Hz, %d tekstdelen, %d audiobytes",
                        sample_rate, deltas, session_bytes)
        elif spraak_gehoord is False:
            logger.info(
                "STT-sessie zonder tekst: %d Hz, %d audiobytes — de browser hoorde "
                "zelf geen spraak (VAD onder de drempel), dus dit zegt niets over de "
                "provider", sample_rate, session_bytes)
        else:
            logger.warning(
                "STT-sessie zonder tekst: %d Hz, %d audiobytes — de provider gaf geen "
                "fout en dus aanvaardde ze het formaat, maar herkende geen spraak%s",
                sample_rate, session_bytes,
                " (de browser hoorde wél spraak)" if spraak_gehoord else "")

    pump_task = asyncio.create_task(pump_transcripts())
    try:
        if eerste_audio is not None:
            reden = boek_audio(eerste_audio)
            if reden is not None:
                close_code, close_reason = reden
                raise _Grens
            await audio_q.put(eerste_audio)
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
                reden = boek_audio(chunk)
                if reden is not None:
                    close_code, close_reason = reden
                    break
                await audio_q.put(chunk)
            elif text is not None:
                # Controleboodschap: {"type": "stop"} = einde opname.
                try:
                    ctrl = json.loads(text)
                except (ValueError, TypeError):
                    ctrl = {}
                if ctrl.get("type") == "stop":
                    gemeld_spraak = ctrl.get("spraak")
                    if isinstance(gemeld_spraak, bool):
                        spraak_gehoord = gemeld_spraak
                    break
    except _Grens:
        pass  # de reden staat al in close_code/close_reason
    finally:
        # Signaleer einde-audio en laat de transcripts afronden, sluit dan netjes.
        await audio_q.put(None)
        try:
            await asyncio.wait_for(pump_task, timeout=10)
        except Exception:
            pump_task.cancel()
        _log_uitkomst()
        if websocket.application_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=close_code, reason=close_reason)
            except RuntimeError:
                pass
