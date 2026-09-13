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
from typing import Any, Callable

from app.database import SessionLocal

from .models import AiCallLog

logger = logging.getLogger(__name__)

# A payload is a whole conversation and grows with every round; a runaway one
# should not be able to fill the table. Cut with a visible marker rather than
# silently, so the fold-out never suggests it is showing everything when it is not.
MAX_PAYLOAD = 100_000
_CUT = "\n… [afgekapt: de payload was groter dan het logboek bewaart]"


def sink_for(actor: str = "") -> Callable[..., None]:
    """A log sink for this caller."""

    def write(*, surface: str, capability: str, model: str, payload: str,
              blocked_reason: str = "", usage: dict[str, int] | None = None,
              **_extra: Any) -> None:
        text = payload if len(payload) <= MAX_PAYLOAD else payload[:MAX_PAYLOAD] + _CUT
        counts = usage or {}
        eigen = SessionLocal()
        try:
            eigen.add(
                AiCallLog(
                    surface=surface,
                    capability=capability or "",
                    actor=actor or "",
                    model=model or "",
                    payload=text,
                    tokens_prompt=counts.get("prompt"),
                    tokens_completion=counts.get("completion"),
                    blocked_reason=blocked_reason or "",
                )
            )
            eigen.commit()
        finally:
            eigen.close()

    return write
