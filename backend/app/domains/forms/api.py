"""Facade van het forms-component (#397) — het enige publieke oppervlak (§1).

Buitenstaanders (schermen, andere componenten) gebruiken uitsluitend deze
functies; models/service/router zijn intern. Contract in CONTRACT.md.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.forms.models import Form, FormSubmission


def get_form_by_slug(db: Session, slug: str) -> Form | None:
    """Publiek raadpleegbaar formulier (of None). DTO-verfijning volgt zodra de
    eerste externe consument (berichten/workflow, #398) zich aandient."""
    return db.query(Form).filter(Form.slug == slug).first()


def submission_count(db: Session, form_id: int) -> int:
    return db.query(FormSubmission).filter(FormSubmission.form_id == form_id).count()


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
