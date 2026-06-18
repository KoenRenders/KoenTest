"""STT-WebSocket-proxy (#282): STT_MODE-gating + STT_PROVIDER.

Dekt het gedrag per strategie (browser_only → handshake geweigerd; native_first →
provider actief), de streaming-pijplijn met de mock-provider (partials → final) en
de vangrails: handshake-rate-limit, idle-timeout, harde audio-cap per sessie en per
IP/dag. CI draait volledig op de mock-provider (geen Voxtral/MISTRAL_API_KEY nodig).
"""
import json

import pytest
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.routers import stt as stt_mod


@pytest.fixture(autouse=True)
def _enable_and_reset(monkeypatch):
    """Zet een provider-modus (native_first) op de mock-provider en reset de globale
    vangrails, zodat tests elkaar niet beïnvloeden (de per-IP-tellers zijn
    module-globaal)."""
    monkeypatch.setattr(settings, "stt_mode", "native_first")
    monkeypatch.setattr(settings, "stt_provider", "mock")
    stt_mod.handshake_limiter.reset()
    stt_mod.audio_budget.reset()
    yield
    stt_mod.handshake_limiter.reset()
    stt_mod.audio_budget.reset()


def _drain_until_disconnect(ws, limit=10):
    """Lees events tot de server de socket sluit; geef (events, close_code)."""
    events = []
    try:
        for _ in range(limit):
            events.append(ws.receive_json())
    except WebSocketDisconnect as exc:
        return events, exc
    return events, None


def test_stt_ws_rejected_in_browser_only_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "stt_mode", "browser_only")
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/stt/voxtral"):
            pass
    assert exc.value.code == 1008


def test_stt_streams_partials_and_final_with_mock(client):
    with client.websocket_connect("/api/v1/stt/voxtral") as ws:
        ws.send_bytes(b"audio-chunk-1")
        ws.send_bytes(b"audio-chunk-2")
        ws.send_text(json.dumps({"type": "stop"}))
        events = []
        while True:
            ev = ws.receive_json()
            events.append(ev)
            if ev["type"] == "final":
                break
    partials = [e for e in events if e["type"] == "partial"]
    finals = [e for e in events if e["type"] == "final"]
    assert len(partials) == 2
    assert finals and finals[-1]["text"] == "mock transcriptie"


def test_stt_idle_timeout_closes(client, monkeypatch):
    monkeypatch.setattr(settings, "stt_idle_timeout_seconds", 1)
    with client.websocket_connect("/api/v1/stt/voxtral") as ws:
        # Geen audio → na de idle-timeout rondt de mock af (final) en sluit de
        # server met de idle-code.
        _events, code = _drain_until_disconnect(ws)
    assert code is not None and code.code == 4408


def test_stt_session_byte_cap_closes(client, monkeypatch):
    monkeypatch.setattr(settings, "stt_max_session_bytes", 10)
    with client.websocket_connect("/api/v1/stt/voxtral") as ws:
        ws.send_bytes(b"x" * 25)  # > cap
        _events, code = _drain_until_disconnect(ws)
    assert code is not None and code.code == 4413


def test_stt_daily_budget_rejects_handshake(client, monkeypatch):
    # Dagbudget op 0 → de handshake wordt al geweigerd (pre-accept), ongeacht IP.
    monkeypatch.setattr(stt_mod.audio_budget, "max_bytes", 0)
    stt_mod.audio_budget.reset()
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/stt/voxtral"):
            pass
    assert exc.value.code == 1008


def test_stt_handshake_rate_limit(client, monkeypatch):
    monkeypatch.setattr(stt_mod.handshake_limiter, "max_calls", 1)
    stt_mod.handshake_limiter.reset()
    # Eerste verbinding mag.
    with client.websocket_connect("/api/v1/stt/voxtral") as ws:
        ws.send_text(json.dumps({"type": "stop"}))
        _drain_until_disconnect(ws)
    # Tweede binnen het venster wordt geweigerd.
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/stt/voxtral"):
            pass
    assert exc.value.code == 1008
