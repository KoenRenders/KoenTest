"""First-party business-events (#152, laag 2) — het "ERP-zaadje".

Server-side gelogde, GDPR-conforme gebeurtenissen op de kernflows (registratie,
betaling, hernieuwing) waaruit we later conversie-, omzet- en lifecycle-rapporten
bouwen. Bewust gescheiden van de anonieme web-analytics (Umami, laag 1).

Privacy (harde randvoorwaarde): NOOIT PII in deze tabel. `payload` bevat enkel
niet-identificerende context (bedrag, betaalmethode, form-type, doeljaar). De
service-laag (`app.domains.analytics.service.log_business_event`) bewaakt dit
actief en weigert PII.

Net als de history-tabellen (zie app/models/history.py) gebruikt deze tabel
BEWUST geen ForeignKeys naar member/activity/payment: een analytics-event moet
het verwijderen van de bron-rij overleven (en bij een GDPR-wisverzoek blijft het
geanonimiseerde event staan zonder de bron te forceren). De koppel-id's zijn dus
gewone, geïndexeerde kolommen — ingevuld waar van toepassing, anders NULL.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class BusinessEvent(Base):
    __tablename__ = "business_events"

    id = Column(Integer, primary_key=True, index=True)
    # Semantisch type, bv. "inschrijving_voltooid", "betaling_succes".
    event_type = Column(String(50), nullable=False, index=True)
    occurred_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False, index=True)

    # Optionele, niet-PII koppelingen (geen FK — zie module-docstring).
    member_id = Column(Integer, nullable=True, index=True)
    activity_id = Column(Integer, nullable=True, index=True)
    payment_record_id = Column(String(36), nullable=True, index=True)

    # Niet-PII context (bedrag, methode, form-type, ...). Bewaakt door de service.
    payload = Column(JSONB, nullable=True)
    # Anonieme correlatie-id (geen IP/e-mail). Voorlopig ongebruikt server-side;
    # voorzien voor latere koppeling met de funnel-events.
    session_ref = Column(String(64), nullable=True, index=True)
