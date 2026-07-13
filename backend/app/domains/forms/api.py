"""Facade van het forms-component (#397) — het enige publieke oppervlak (§1).

Buitenstaanders (schermen, andere componenten) gebruiken uitsluitend deze
functies; models/service/router zijn intern. Contract in CONTRACT.md.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

import logging

from app.domains.forms.models import Form, FormSubmission

logger = logging.getLogger(__name__)


def get_form_by_slug(db: Session, slug: str) -> Form | None:
    """Publiek raadpleegbaar formulier (of None). DTO-verfijning volgt zodra de
    eerste externe consument (berichten/workflow, #398) zich aandient."""
    return db.query(Form).filter(Form.slug == slug).first()


def submission_count(db: Session, form_id: int) -> int:
    return db.query(FormSubmission).filter(FormSubmission.form_id == form_id).count()


def submit_bericht(db: Session, *, naam: str, email: str | None, bericht: str,
                   background_tasks=None) -> int | None:
    """Hét schrijfpad voor een bericht (#398): inzending op het geseede
    'berichten'-formulier + SubmissionCreated (→ behartigen-taak) + optionele
    bevestigingsmail. Geeft het submission-id terug, of None als het formulier
    ontbreekt. Gebruikt door /berichten (ui) én de chatbot — geen tweede weg."""
    from app.domains.forms.schemas import AnswerIn
    from app.domains.forms.service import build_answers
    from app.kernel.contracts.forms import SubmissionCreated
    from app.kernel.events import publish
    from app.domains.mail.api import send_form_confirmation

    form = db.query(Form).filter(Form.slug == "berichten").first()
    if form is None or not form.fields:
        return None
    answers = build_answers(form, [AnswerIn(field_id=form.fields[0].id, text=bericht)])
    submission = FormSubmission(form_id=form.id, submitter_name=naam,
                                submitter_email=email or None)
    for row in answers:
        submission.answers.append(row)
    db.add(submission)
    db.flush()
    publish(SubmissionCreated(
        form_id=form.id, form_slug=form.slug, submission_id=submission.id,
        submitter_name=naam, submitter_email=email or None), db)
    db.commit()

    if form.send_confirmation and email:
        try:
            send_form_confirmation(
                to_email=email, form_title=form.title, name=naam,
                confirmation_message=form.confirmation_message,
                background_tasks=background_tasks)
        except Exception as exc:  # pragma: no cover
            logger.warning("Bevestigingsmail bericht kon niet verstuurd worden: %s", exc)
    return submission.id


def submission_view(db: Session, submission_id: int) -> list[tuple[str, str]]:
    """Leesbare (label, waarde)-rijen van één inzending — voor gast-weergave
    buiten het component (werkbank-taakdetail, #398). Geen ORM over de grens."""
    sub = db.query(FormSubmission).filter(FormSubmission.id == submission_id).first()
    if sub is None:
        return []
    rows: list[tuple[str, str]] = [
        ("Van", sub.submitter_name or "—"),
        ("E-mail", sub.submitter_email or "—"),
        ("Ontvangen", sub.submitted_at.strftime("%d-%m-%Y %H:%M")),
    ]
    for ans in sub.answers:
        label = ans.field.label if ans.field else "Antwoord"
        value = ans.value_text or (str(ans.value_number) if ans.value_number is not None else "")
        if value:
            rows.append((label, value))
    return rows
