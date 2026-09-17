"""Writing the outbound-call log (CR-07 §6.4).

Separate from `seam.py` on purpose. The guard decides whether a payload may leave
and must stay free of anything it might have to import back; this module knows
about the session and the table and nothing about the rules. The seam calls it
through a plain callable, so a test can hand the guard a list instead of a
database.

One row per call, blocked calls included — a call that was refused is the row you
most want afterwards.

**In its own session, and committed there.** A row here records that data left the
building; whether the request that caused it went on to succeed is a different
question. Tied to the caller's transaction, a rolled-back turn would erase the
record of the call that was already made — and a refused call, whose route ends in
an error path, is precisely the one worth keeping. It also keeps the commit out of
the route, where the layer gate rightly does not want one (#635 rule 2).
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Callable

from app.database import SessionLocal

from .models import AiCallLog

logger = logging.getLogger(__name__)

# A payload is a whole conversation and grows with every round; a runaway one
# should not be able to fill the table. Cut with a visible marker rather than
# silently, so the fold-out never suggests it is showing everything when it is not.
MAX_PAYLOAD = 100_000
_CUT = "\n… [afgekapt: de payload was groter dan het logboek bewaart]"


#: The values `status` takes (#978). Empty is not one of them: a row that does
#: not say how the call went cannot be counted either way.
STATUSES = ("ok", "blocked", "error", "moderated")


def sink_for(actor: str = "") -> Callable[..., None]:
    """A log sink for this caller.

    Every field is named (#978). An unknown keyword is a TypeError rather than
    something swallowed: a field that silently disappears is how a cost goes
    missing from the total.

    `tenant_id` is only for callers outside a request — a background job has no
    tenant in its context, and the row would otherwise land on the default one.
    """

    def write(*, surface: str, capability: str, model: str, payload: str,
              blocked_reason: str = "", usage: dict[str, int] | None = None,
              provider: str = "", endpoint: str = "", provider_request_id: str = "",
              status: str = "", duration_ms: int | None = None,
              cost_credits: Decimal | float | None = None,
              cost_amount: Decimal | float | None = None,
              cost_currency: str | None = None,
              output_megapixels: Decimal | float | None = None,
              tenant_id: int | None = None) -> None:
        text = payload if len(payload) <= MAX_PAYLOAD else payload[:MAX_PAYLOAD] + _CUT
        counts = usage or {}
        status = status or ("blocked" if blocked_reason else "ok")
        if status not in STATUSES:
            raise ValueError(f"onbekende status voor het AI-logboek: {status!r}")
        rij = AiCallLog(
            surface=surface,
            capability=capability or "",
            actor=actor or "",
            model=model or "",
            payload=text,
            tokens_prompt=counts.get("prompt"),
            tokens_completion=counts.get("completion"),
            blocked_reason=blocked_reason or "",
            provider=(provider or "")[:32],
            endpoint=(endpoint or "")[:128],
            provider_request_id=(provider_request_id or "")[:128],
            status=status,
            duration_ms=duration_ms,
            cost_credits=_decimal(cost_credits),
            cost_amount=_decimal(cost_amount),
            cost_currency=(cost_currency or None) and cost_currency.upper(),
            output_megapixels=_decimal(output_megapixels),
        )
        if tenant_id is not None:
            rij.tenant_id = tenant_id
        eigen = SessionLocal()
        try:
            eigen.add(rij)
            eigen.commit()
        finally:
            eigen.close()

    return write


def _decimal(value: Decimal | float | None) -> Decimal | None:
    """Through `str`, so 4.5 is stored as 4.5 and not as its binary neighbour."""
    return None if value is None else Decimal(str(value))
