"""Events die het forms-component publiceert (contract, zie forms/CONTRACT.md)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.kernel.events import KernelEvent


@dataclass(frozen=True)
class SubmissionCreated(KernelEvent):
    """Een formulier-inzending is aangemaakt (synchroon, in-transactie —
    event-ladder trede 1). Consumenten: workflow (behartigen-taak, #398)."""

    form_id: int
    form_slug: Optional[str]
    submission_id: int
    submitter_name: Optional[str]
    submitter_email: Optional[str]
