"""Service voor first-party business-events (#152, laag 2).

`log_business_event` voegt één event toe aan de huidige sessie met GEEN eigen
commit: het event commit mee in dezelfde transactie als de flow die het logt
(atomair — net als de history-snapshots, zie app/domains/audit/service.py). Roep
het dus aan vóór de `db.commit()` van de caller.

PII-bewaking (harde GDPR-randvoorwaarde van #152): de payload mag nooit
identificerende gegevens bevatten. We weigeren actief (a) een denylist van
sleutels (naam, e-mail, telefoon, ...) en (b) waarden die op een e-mailadres
lijken. Liever een harde fout in dev/CI dan stilletjes PII wegschrijven.
"""
import re
from typing import Optional
from sqlalchemy.orm import Session

from app.domains.analytics.models import BusinessEvent

# Sleutels die nooit in een event-payload thuishoren (PII). Vergelijking is
# case-insensitive en op substring, zodat bv. "contact_email" of "kind_naam"
# ook geweigerd wordt.
_FORBIDDEN_KEY_FRAGMENTS = (
    "naam", "name", "email", "e-mail", "mail",
    "phone", "tel", "gsm", "mobile", "mobiel",
    "address", "adres", "street", "straat", "geboorte", "birth",
)

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class PiiInEventError(ValueError):
    """Opgegooid wanneer een event-payload PII lijkt te bevatten."""


def _assert_no_pii(payload: Optional[dict]) -> None:
    if payload is None:
        return
    for key, value in payload.items():
        key_l = str(key).lower()
        for frag in _FORBIDDEN_KEY_FRAGMENTS:
            if frag in key_l:
                raise PiiInEventError(
                    f"PII-achtige sleutel '{key}' is niet toegestaan in een business-event payload."
                )
        if isinstance(value, str) and _EMAIL_RE.search(value):
            raise PiiInEventError(
                f"Waarde van '{key}' lijkt een e-mailadres te bevatten — PII niet toegestaan."
            )


def log_business_event(
    db: Session,
    event_type: str,
    *,
    member_id: Optional[int] = None,
    activity_id: Optional[int] = None,
    payment_record_id: Optional[str] = None,
    payload: Optional[dict] = None,
    session_ref: Optional[str] = None,
) -> BusinessEvent:
    """Leg één business-event vast (zonder commit). Weigert PII in de payload."""
    _assert_no_pii(payload)
    event = BusinessEvent(
        event_type=event_type,
        member_id=member_id,
        activity_id=activity_id,
        payment_record_id=payment_record_id,
        payload=payload,
        session_ref=session_ref,
    )
    db.add(event)
    return event
