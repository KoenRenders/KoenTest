"""Eenvoudige in-memory rate limiter — geen Redis, geen externe dependencies.

Let op: dit is in-memory en per proces. Draaien er meerdere Uvicorn-workers,
dan telt elke worker apart (de effectieve limiet ligt dan hoger). Voor de
schaal van deze site (één vereniging, één worker) is dat ruim voldoende.
Een gedeelde teller zou Redis o.i.d. vereisen — bewust niet gedaan.
"""
import time
from collections import defaultdict
from datetime import date
from fastapi import Request, HTTPException, status


def _client_ip(request: Request) -> str:
    """Bepaal het echte client-IP.

    Al het verkeer komt via Caddy binnen, dus request.client.host is het IP
    van de proxy. Caddy geeft het echte bezoekers-IP door in X-Forwarded-For;
    het eerste adres in die lijst is de oorspronkelijke client.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window = window_seconds
        self._calls: dict = defaultdict(list)

    def __call__(self, request: Request):
        key = _client_ip(request)
        now = time.time()
        window_start = now - self.window
        # Behoud enkel de aanroepen binnen het venster (oude vallen weg).
        recent = [t for t in self._calls[key] if t > window_start]
        if len(recent) >= self.max_calls:
            self._calls[key] = recent
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Te veel pogingen. Probeer later opnieuw.",
            )
        recent.append(now)
        self._calls[key] = recent


class DailyCharBudget:
    """Dagelijks tekenbudget per IP — misbruik-/kostenrem voor de chatbot (#205).

    Telt het aantal door de bezoeker getypte tekens per dag op. Bij overschrijding
    een vriendelijke 429 i.p.v. een harde fout. In-memory en per proces (zelfde
    voorbehoud als RateLimiter); reset vanzelf bij dagwissel.
    """

    def __init__(self, max_chars_per_day: int):
        self.max_chars = max_chars_per_day
        self._usage: dict = defaultdict(int)
        self._day: date = date.today()

    def _roll_day(self):
        today = date.today()
        if today != self._day:
            self._usage.clear()
            self._day = today

    def charge(self, request: Request, chars: int):
        self._roll_day()
        key = _client_ip(request)
        if self._usage[key] + chars > self.max_chars:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Je hebt vandaag veel met Raakje gechat. Probeer het morgen "
                    "opnieuw, of laat je vraag achter via het ideeënformulier."
                ),
            )
        self._usage[key] += chars


# Per endpoint een eigen limiter met een passende limiet.
# Login verstuurt e-mails → streng. Registratie/inschrijving raakt Mollie
# maar moet een legitieme piek toelaten → matig.
login_limiter = RateLimiter(max_calls=5, window_seconds=60)
registration_limiter = RateLimiter(max_calls=10, window_seconds=60)
idea_limiter = RateLimiter(max_calls=5, window_seconds=60)
# Chatbot: matige burst-limiet + dagelijks tekenbudget tegen 'pagina-droppen'.
chat_limiter = RateLimiter(max_calls=20, window_seconds=60)
# Mollie-webhook: ruime limiet (#182). Mollie deelt enkele IP's en kan bursts/
# herhalingen sturen, dus de drempel ligt hoog genoeg om legitieme calls nooit
# te droppen; een zeldzame drop self-heal't bovendien (Mollie hertest, en de
# status wordt bij de volgende re-fetch alsnog opgehaald). Doel is enkel een rem
# tegen een ruwe flood vanaf één IP (DB-/Mollie-quota-bescherming).
mollie_webhook_limiter = RateLimiter(max_calls=60, window_seconds=60)
