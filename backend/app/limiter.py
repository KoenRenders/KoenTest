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
from app.i18n import _


def _client_ip(request: Request) -> str:
    """Bepaal het echte client-IP voor de rate-limiter.

    Aanname: precies één bekende proxy-hop (Caddy), en de backend is NIET direct
    van buiten bereikbaar (poort 8000 staat in prod/uat enkel op het interne
    Docker-netwerk — geen ``ports:`` in docker-compose.{prod,uat}.yml). Caddy
    APPENDT het werkelijke client-IP achteraan ``X-Forwarded-For``, dus het MEEST
    RECHTSE adres is door Caddy gezet en betrouwbaar. Het meest linkse adres is
    client-gestuurd en dus spoofbaar — wie dát vertrouwt, krijgt per request een
    vers 'IP' en omzeilt álle per-IP-limieten (OTP-gok, login-mails, bericht-spam,
    chat-budget) (#268).
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
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
                detail=_("Te veel pogingen. Probeer later opnieuw."),
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
                detail=_(
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
# Publieke formulier-inzending/-wijziging: schrijft rijen + kan een bevestigingsmail
# triggeren → rem tegen spam/DoS. Ruim genoeg voor een legitieme piek per IP (#371).
form_submit_limiter = RateLimiter(max_calls=10, window_seconds=60)
# Duimpje bij een foto (#920): een EIGEN limiet, en bewust ruimer dan die hierboven.
# Het endpoint hing eerst aan `form_submit_limiter`, en dat brak op productie binnen
# enkele uren: door een album klikken en tien foto's leuk vinden is het normale gebruik,
# niet een aanval — het is letterlijk waar #883 voor gebouwd is. De teller loopt per IP,
# dus een gezin dat samen thuiskijkt of een zaal op één wifi deelde die tien.
#
# De rem zelf blijft: zonder cookie krijgt elk verzoek een nieuw token en dus een nieuwe
# rij, dus een script mag hier niet ongelimiteerd kunnen schrijven. Ze moet een script
# tegenhouden, geen bezoeker — en zestig per minuut is sneller dan iemand klikt en traag
# genoeg om een teller niet in een uitslag te veranderen.
thumb_limiter = RateLimiter(max_calls=60, window_seconds=60)
# Chatbot: matige burst-limiet + dagelijks tekenbudget tegen 'pagina-droppen'.
chat_limiter = RateLimiter(max_calls=20, window_seconds=60)
# Mollie-webhook: ruime limiet (#182). Mollie deelt enkele IP's en kan bursts/
# herhalingen sturen, dus de drempel ligt hoog genoeg om legitieme calls nooit
# te droppen; een zeldzame drop self-heal't bovendien (Mollie hertest, en de
# status wordt bij de volgende re-fetch alsnog opgehaald). Doel is enkel een rem
# tegen een ruwe flood vanaf één IP (DB-/Mollie-quota-bescherming).
mollie_webhook_limiter = RateLimiter(max_calls=60, window_seconds=60)
