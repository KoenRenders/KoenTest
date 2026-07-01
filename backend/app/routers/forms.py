import logging
import re
import secrets
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.config import settings
from app.database import get_db
from app.models.form import (
    Form,
    FormSection,
    FormField,
    FormFieldOption,
    FormSubmission,
    FORM_STATUSES,
    FIELD_TYPES,
)
from app.models.user import User
from app.schemas.form import (
    FormCreate,
    FormUpdate,
    FormAdminOut,
    FormSummary,
    PublicForm,
    SubmissionIn,
    SubmissionResult,
    EditSubmissionOut,
)
from app.services.form_submission import build_answers, assert_open_for_submission
from app.services.form_results import compute_results
from app.services.form_export import export_csv, export_ods
from app.services.email import send_form_confirmation

logger = logging.getLogger(__name__)

router = APIRouter(tags=["forms"])


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _unique_share_token(db: Session) -> str:
    for _ in range(10):
        tok = _new_token()
        if not db.query(Form.id).filter(Form.share_token == tok).first():
            return tok
    raise HTTPException(status_code=500, detail="Kon geen unieke deellink genereren.")


def _validate_form_payload(data) -> None:
    if data.status not in FORM_STATUSES:
        raise HTTPException(status_code=422, detail=f"Ongeldige status: {data.status}")
    for f in data.fields:
        if f.field_type not in FIELD_TYPES:
            raise HTTPException(status_code=422, detail=f"Ongeldig veldtype: {f.field_type}")


def _apply_fields(form: Form, data) -> None:
    """Vervang de secties/velden/opties van het formulier door wat in de payload
    staat. Velden verwijzen via `section_index` naar de aangemaakte secties."""
    form.sections.clear()
    form.fields.clear()

    created_sections = []
    for si in getattr(data, "sections", []) or []:
        section = FormSection(title=si.title, description=si.description, position=si.position)
        form.sections.append(section)
        created_sections.append(section)

    for fi in data.fields:
        field = FormField(
            field_type=fi.field_type,
            label=fi.label,
            help_text=fi.help_text,
            required=fi.required,
            position=fi.position,
            min_value=fi.min_value,
            max_value=fi.max_value,
            min_length=fi.min_length,
            max_length=fi.max_length,
            regex_pattern=fi.regex_pattern,
        )
        idx = fi.section_index
        if idx is not None and 0 <= idx < len(created_sections):
            field.section = created_sections[idx]
        for oi in fi.options:
            field.options.append(
                FormFieldOption(
                    label=oi.label, value=oi.value, position=oi.position,
                    is_other=oi.is_other,
                )
            )
        form.fields.append(field)


def _submission_count(db: Session, form_id: int) -> int:
    return (
        db.query(func.count(FormSubmission.id))
        .filter(FormSubmission.form_id == form_id)
        .scalar()
        or 0
    )


def _admin_out(db: Session, form: Form) -> dict:
    data = FormAdminOut.model_validate(form).model_dump()
    data["submission_count"] = _submission_count(db, form.id)
    return data


# ── Admin CRUD ──────────────────────────────────────────────────────────────────

@router.post("/forms", response_model=FormAdminOut)
def create_form(
    data: FormCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    _validate_form_payload(data)
    form = Form(
        title=data.title,
        slug=data.slug,
        description=data.description,
        share_token=_unique_share_token(db),
        status=data.status,
        requires_login=data.requires_login,
        max_submissions=data.max_submissions,
        send_confirmation=data.send_confirmation,
        confirmation_message=data.confirmation_message,
        allow_edit=data.allow_edit,
    )
    _apply_fields(form, data)
    db.add(form)
    db.commit()
    db.refresh(form)
    return _admin_out(db, form)


@router.get("/forms", response_model=List[FormSummary])
def list_forms(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    forms = db.query(Form).order_by(Form.created_at.desc()).all()
    out = []
    for f in forms:
        item = FormSummary.model_validate(f).model_dump()
        item["submission_count"] = _submission_count(db, f.id)
        out.append(item)
    return out


@router.get("/forms/{form_id}", response_model=FormAdminOut)
def get_form(
    form_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Formulier niet gevonden")
    return _admin_out(db, form)


@router.put("/forms/{form_id}", response_model=FormAdminOut)
def update_form(
    form_id: int,
    data: FormUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    _validate_form_payload(data)
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Formulier niet gevonden")
    form.title = data.title
    form.slug = data.slug
    form.description = data.description
    form.status = data.status
    form.requires_login = data.requires_login
    form.max_submissions = data.max_submissions
    form.send_confirmation = data.send_confirmation
    form.confirmation_message = data.confirmation_message
    form.allow_edit = data.allow_edit
    _apply_fields(form, data)
    db.commit()
    db.refresh(form)
    return _admin_out(db, form)


@router.delete("/forms/{form_id}", status_code=204)
def delete_form(
    form_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Formulier niet gevonden")
    db.delete(form)
    db.commit()


@router.get("/forms/{form_id}/results")
def form_results(
    form_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Formulier niet gevonden")
    return compute_results(db, form)


@router.get("/forms/{form_id}/export")
def export_form(
    form_id: int,
    format: str = Query("csv"),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Formulier niet gevonden")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", form.title or "formulier").strip("_") or "formulier"
    if format == "ods":
        return Response(
            content=export_ods(db, form),
            media_type="application/vnd.oasis.opendocument.spreadsheet",
            headers={"Content-Disposition": f'attachment; filename="{safe}.ods"'},
        )
    if format == "csv":
        return Response(
            content=export_csv(db, form),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{safe}.csv"'},
        )
    raise HTTPException(status_code=422, detail="Ongeldig formaat (csv of ods).")


# ── Publiek: invullen ───────────────────────────────────────────────────────────

def _load_public_form(db: Session, share_token: str) -> Form:
    form = db.query(Form).filter(Form.share_token == share_token).first()
    # Concept-formulieren zijn niet publiek zichtbaar.
    if not form or form.status == "draft":
        raise HTTPException(status_code=404, detail="Formulier niet gevonden")
    return form


@router.get("/forms/by-token/{share_token}", response_model=PublicForm)
def get_public_form(share_token: str, db: Session = Depends(get_db)):
    return _load_public_form(db, share_token)


@router.post("/forms/by-token/{share_token}/submit", response_model=SubmissionResult)
def submit_form(
    share_token: str,
    data: SubmissionIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    form = _load_public_form(db, share_token)
    assert_open_for_submission(db, form)
    answers = build_answers(form, data.answers)

    submission = FormSubmission(
        form_id=form.id,
        submitter_name=data.submitter_name,
        submitter_email=data.submitter_email,
        edit_token=_new_token() if form.allow_edit else None,
    )
    for row in answers:
        submission.answers.append(row)
    db.add(submission)
    db.commit()
    db.refresh(submission)

    if form.send_confirmation and data.submitter_email:
        edit_link = None
        if form.allow_edit and submission.edit_token:
            edit_link = f"{settings.frontend_url}/formulier/{form.share_token}/edit/{submission.edit_token}"
        try:
            send_form_confirmation(
                to_email=data.submitter_email,
                form_title=form.title,
                name=data.submitter_name,
                confirmation_message=form.confirmation_message,
                edit_link=edit_link,
                background_tasks=background_tasks,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Bevestigingsmail formulier kon niet verstuurd worden: %s", exc)

    return SubmissionResult(id=submission.id, status="ok", edit_token=submission.edit_token)


# ── Publiek: wijzigen via edit_token ────────────────────────────────────────────

def _answers_payload(submission: FormSubmission) -> list:
    by_field: dict = {}
    for ans in submission.answers:
        entry = by_field.setdefault(
            ans.field_id,
            {"field_id": ans.field_id, "text": None, "number": None,
             "option_ids": [], "rating": None, "other_text": None},
        )
        if ans.value_option_id is not None:
            entry["option_ids"].append(ans.value_option_id)
            # value_text op een optie-rij = de vrije "Andere…"-tekst (#337).
            if ans.value_text is not None:
                entry["other_text"] = ans.value_text
        elif ans.value_text is not None:
            entry["text"] = ans.value_text
        if ans.value_number is not None:
            entry["number"] = ans.value_number
        if ans.value_rating is not None:
            entry["rating"] = ans.value_rating
    return list(by_field.values())


@router.get("/forms/edit/{edit_token}", response_model=EditSubmissionOut)
def get_editable_submission(edit_token: str, db: Session = Depends(get_db)):
    submission = db.query(FormSubmission).filter(FormSubmission.edit_token == edit_token).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Inzending niet gevonden")
    form = db.query(Form).filter(Form.id == submission.form_id).first()
    return {
        "form": form,
        "submitter_name": submission.submitter_name,
        "submitter_email": submission.submitter_email,
        "answers": _answers_payload(submission),
    }


@router.put("/forms/edit/{edit_token}", response_model=SubmissionResult)
def update_submission(
    edit_token: str,
    data: SubmissionIn,
    db: Session = Depends(get_db),
):
    from datetime import datetime, timezone

    submission = db.query(FormSubmission).filter(FormSubmission.edit_token == edit_token).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Inzending niet gevonden")
    form = db.query(Form).filter(Form.id == submission.form_id).first()
    if not form or not form.allow_edit:
        raise HTTPException(status_code=403, detail="Wijzigen is niet toegestaan.")
    if form.status != "open":
        raise HTTPException(status_code=403, detail="Dit formulier staat niet (meer) open.")

    answers = build_answers(form, data.answers)
    submission.answers.clear()
    for row in answers:
        submission.answers.append(row)
    submission.submitter_name = data.submitter_name
    submission.submitter_email = data.submitter_email
    submission.updated_at = datetime.now(timezone.utc)
    db.commit()
    return SubmissionResult(id=submission.id, status="updated", edit_token=submission.edit_token)
