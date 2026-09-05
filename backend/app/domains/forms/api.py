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
    from app.domains.forms.service import get_form_by_slug as _impl

    return _impl(db, slug)


def submission_count(db: Session, form_id: int) -> int:
    from app.domains.forms.service import submission_count as _impl

    return _impl(db, form_id)


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

    from app.domains.forms.service import assert_submitter

    form = db.query(Form).filter(Form.slug == "berichten").first()
    if form is None or not form.fields:
        return None
    # De invariant gold "voor élke ingang", maar juist deze riep hem niet aan
    # (#635-2). De chatbot schrijft hier ook naartoe, dus een leeg bericht of een
    # ontbrekend adres kwam er langs de zijdeur toch in.
    assert_submitter(form, naam, email, message=bericht, require_message=True)
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
    # Zelfde typedekking als de export (#407-O flatten-drift): ook optie- en
    # rating-antwoorden tonen, met het optielabel i.p.v. een leeg veld.
    per_label: dict[str, list[str]] = {}
    volgorde: list[str] = []
    for ans in sub.answers:
        label = ans.field.label if ans.field else "Antwoord"
        if ans.value_text is not None:
            waarde = ans.value_text
        elif ans.value_number is not None:
            waarde = f"{ans.value_number}"
        elif ans.value_option_id is not None:
            optie = next((o for o in (ans.field.options if ans.field else [])
                          if o.id == ans.value_option_id), None)
            waarde = optie.label if optie else ""
        elif ans.value_rating is not None:
            waarde = str(ans.value_rating)
        else:
            waarde = ""
        if not waarde:
            continue
        if label not in per_label:
            per_label[label] = []
            volgorde.append(label)
        per_label[label].append(waarde)
    rows.extend((label, "; ".join(per_label[label])) for label in volgorde)
    return rows


# ── Wat de schermen gebruiken (#635 D/I) ─────────────────────────────────────
# Onderaan, zodat de functies hierboven hun eigen naam houden: `submission_count`
# en `get_form_by_slug` staan al als facade-functie gedefinieerd en delegeren nu
# naar dezelfde service-implementatie.

from app.domains.forms.models import (  # noqa: E402,F401
    FIELD_TYPES,
    FORM_STATUSES,
)
from app.domains.forms.service import (  # noqa: E402,F401
    FormulierFout,
    add_field,
    add_option,
    add_section,
    apply_definition,
    assert_submitter,
    create_form,
    delete_field,
    delete_form,
    delete_option,
    delete_section,
    delete_submission,
    get_form,
    get_form_by_share_token,
    get_submission_by_edit_token,
    import_definition,
    list_forms,
    list_submissions,
    move_field,
    move_section,
    update_field,
    update_form_settings,
    update_option,
    update_section,
    update_settings,
    validate_definition,
)


# ── Doorgangen waarvan de implementatie in de router blijft ──────────────────
# De publieke inzendflow is één domeinbewerking die het scherm alleen aanroept —
# hetzelfde patroon als de activiteiteninschrijving, die #635 expliciet als "zo
# hoort het" aanmerkt. Alleen de weg ernaartoe loopt via deze facade.

def submit_public_form(db, share_token: str, payload, background_tasks):
    """Een publieke inzending verwerken."""
    from app.domains.forms.router import submit_form as _impl

    return _impl(share_token, payload, background_tasks, db=db)


def update_public_submission(db, edit_token: str, payload):
    """Een eigen inzending bijwerken via de edit-link."""
    from app.domains.forms.router import update_submission as _impl

    return _impl(edit_token, payload, db=db)


def export_submissions_ods(db, form_id: int):
    """De inzendingen als .ods.

    `format` expliciet: `export_form` heeft `format=Query("ods")`, en bij een
    directe aanroep is die default een FastAPI Query-object i.p.v. de string —
    anders faalt de format-check met 422 "Ongeldig formaat".
    """
    from app.domains.forms.router import export_form as _impl

    return _impl(form_id, format="ods", db=db, _admin=None)  # type: ignore[arg-type]


def form_definition(db, form) -> dict:
    """De volledige definitie als dict (backup, inspectie, AI-gids)."""
    from app.domains.forms.router import _admin_out

    return _admin_out(db, form)


def unique_share_token(db) -> str:
    from app.domains.forms.router import _unique_share_token

    return _unique_share_token(db)
