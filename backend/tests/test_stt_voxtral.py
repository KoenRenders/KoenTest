"""STT-WebSocket dark-launch-skelet (#282).

Eerste increment: de WS-route + kill-switch staan op hun plaats, de echte
Voxtral-Realtime-proxy nog niet. Deze tests pinnen het kill-switch-gedrag vast:
uit → handshake geweigerd (geen Voxtral-kost); aan (dark) → verbinding wordt
aanvaard en meteen netjes gesloten met 'nog niet beschikbaar'.
"""
import pytest
from starlette.websockets import WebSocketDisconnect

from app.config import settings


def test_stt_ws_rejected_when_disabled(client):
    """Standaard staat STT_VOXTRAL_ENABLED uit → de handshake wordt geweigerd."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/stt/voxtral"):
            pass
    assert exc.value.code == 1008


def test_stt_ws_dark_when_enabled(client, monkeypatch):
    """Aan, maar de proxy is nog niet geïmplementeerd → verbinding wordt
    aanvaard en meteen gesloten met code 1011 (dark skelet)."""
    monkeypatch.setattr(settings, "stt_voxtral_enabled", True)
    with client.websocket_connect("/api/v1/stt/voxtral") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
    assert exc.value.code == 1011
