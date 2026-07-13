"""Event-abonnementen van workflow (#398): berichten krijgen een behartigen-taak.

Geïmporteerd door de composer (main) zodat de abonnementen geregistreerd zijn.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.workflow import api
from app.kernel.contracts.forms import SubmissionCreated
from app.kernel.events import subscribe

BERICHTEN_SLUG = "berichten"


@subscribe(SubmissionCreated)
def create_behartigen_task(event: SubmissionCreated, db: Session) -> None:
    if event.form_slug != BERICHTEN_SLUG:
        return
    afzender = event.submitter_name or "onbekende afzender"
    api.create_task(
        db,
        kind="bericht.behartigen",
        title=f"Bericht van {afzender} behartigen",
        subject_type="form_submission",
        subject_id=event.submission_id,
    )
