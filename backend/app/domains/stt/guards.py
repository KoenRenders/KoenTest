"""WebSocket-specifieke vangrails voor de STT-proxy (#282).

In-memory en per proces (zelfde voorbehoud als ``app.limiter``). Bewust apart van
de HTTP-limiters: een WebSocket kan geen ``HTTPException`` gooien, dus deze guards
geven booleans terug en de route sluit de socket met een gepaste code.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import date

from starlette.websockets import WebSocket


def ws_client_ip(websocket: WebSocket) -> str:
    """Zelfde betrouwbare-IP-logica als ``app.limiter._client_ip`` (#268): het
    MEEST RECHTSE ``X-Forwarded-For``-adres is door Caddy gezet en niet spoofbaar.
    """
    xff = websocket.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return websocket.client.host if websocket.client else "unknown"


class HandshakeRateLimiter:
    """Sliding-window rate-limit op WS-handshakes per IP."""

    def __init__(self, max_calls: int, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window = window_seconds
        self._calls: dict[str, deque] = defaultdict(deque)

    def allow(self, ip: str) -> bool:
        now = time.time()
        q = self._calls[ip]
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.max_calls:
            return False
        q.append(now)
        return True

    def reset(self) -> None:
        self._calls.clear()


class DailyAudioBudget:
    """Dagelijks audio-byte-budget per IP — kosten-/misbruikrem. Reset vanzelf bij
    dagwissel (zelfde patroon als ``app.limiter.DailyCharBudget``)."""

    def __init__(self, max_bytes_per_day: int):
        self.max_bytes = max_bytes_per_day
        self._usage: dict[str, int] = defaultdict(int)
        self._day: date = date.today()

    def _roll(self) -> None:
        today = date.today()
        if today != self._day:
            self._usage.clear()
            self._day = today

    def exhausted(self, ip: str) -> bool:
        self._roll()
        return self._usage[ip] >= self.max_bytes

    def charge(self, ip: str, nbytes: int) -> bool:
        """Boek ``nbytes`` op het dagbudget. True als het paste (en geboekt is),
        False bij overschrijding (niets geboekt)."""
        self._roll()
        if self._usage[ip] + nbytes > self.max_bytes:
            return False
        self._usage[ip] += nbytes
        return True

    def reset(self) -> None:
        self._usage.clear()
        self._day = date.today()
