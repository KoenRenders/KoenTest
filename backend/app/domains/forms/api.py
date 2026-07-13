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
