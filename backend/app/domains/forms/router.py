import logging
import re
import secrets
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.limiter import form_submit_limiter
from app.config import settings
from app.database import get_db
from app.domains.forms.models import (
    Form,
    FormSection,
    FormField,
    FormFieldOption,
    FormSubmission,
    FORM_STATUSES,
    FIELD_TYPES,
)
from app.models.user import User
from app.domains.forms.schemas import (
    FormCreate,
    FormUpdate,
    FormAdminOut,
    FormSummary,
    PublicForm,
    SubmissionIn,
    SubmissionResult,
    EditSubmissionOut,
)
from app.domains.forms.service import build_answers, assert_open_for_submission
from app.domains.forms.results import compute_results
from app.domains.forms.export import export_ods, build_submissions_view
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
    sections = getattr(data, "sections", []) or []
    n_sections = len(sections)
    # Sectie-navigatie moet vooruit springen (geen lus).
    for i, s in enumerate(sections):
        if s.next_section_index is not None:
            if not (0 <= s.next_section_index < n_sections):
                raise HTTPException(status_code=422, detail="Ongeldige doelsectie.")
            if s.next_section_index <= i:
                raise HTTPException(
                    status_code=422,
                    detail="Een sectie-sprong moet naar een latere sectie gaan.",
                )
    for f in data.fields:
        if f.field_type not in FIELD_TYPES:
            raise HTTPException(status_code=422, detail=f"Ongeldig veldtype: {f.field_type}")
        # Vraag/label is verplicht (#340).
        if not (f.label or "").strip():
            raise HTTPException(status_code=422, detail="Elk veld heeft een vraag/label nodig.")
        for o in f.options:
            has_skip = o.skip_to_section_index is not None or o.skip_to_end
            if has_skip and f.field_type not in ("radio", "select"):
                raise HTTPException(
                    status_code=422,
                    detail="Vertakking kan enkel bij 'één keuze' of 'keuzelijst'.",
                )
            # Vooruit-sprong afdwingen (geen lus): doelsectie moet ná de sectie van
            # het veld komen. Secties zijn geordend volgens hun index in de payload.
            if o.skip_to_section_index is not None:
                if not (0 <= o.skip_to_section_index < n_sections):
                    raise HTTPException(status_code=422, detail="Ongeldige doelsectie voor vertakking.")
                if f.section_index is not None and o.skip_to_section_index <= f.section_index:
                    raise HTTPException(
                        status_code=422,
                        detail="Een vertakking moet naar een latere sectie springen.",
                    )


def _apply_fields(form: Form, data) -> None:
    """Verzoen de secties/velden/opties van het formulier met de payload.

    Bestaande rijen worden **hergebruikt op basis van hun id** (indien meegestuurd)
    i.p.v. gewist-en-heraangemaakt. Zo behouden velden hun id en blijven de
    eraan gekoppelde inzendings-antwoorden intact wanneer de admin het formulier
    bewerkt (bv. een vraag toevoegt). Velden/opties/secties die niet meer in de
    payload staan, worden verwijderd. Velden verwijzen via `section_index` naar
    de secties in payload-volgorde (branching #336).
    """
    existing_sections = {s.id: s for s in form.sections}
    existing_fields = {f.id: f for f in form.fields}

    # ── Secties: hergebruik-op-id, in payload-volgorde ──────────────────────────
    payload_sections = getattr(data, "sections", []) or []
    result_sections = []
    for si in payload_sections:
        section = existing_sections.get(si.id) if si.id is not None else None
        if section is None:
            section = FormSection()
            form.sections.append(section)
        section.title = si.title
        section.description = si.description
        section.position = si.position
        section.next_is_end = si.next_is_end
        section.next_section = None  # onder resolven
        result_sections.append(section)
    # Verwijder secties die niet meer voorkomen.
    keep_sections = set(result_sections)
    for section in list(form.sections):
        if section not in keep_sections:
            form.sections.remove(section)
    # Sectie-navigatie koppelen (index → sectie-object in payload-volgorde).
    for si, section in zip(payload_sections, result_sections):
        nidx = si.next_section_index
        if nidx is not None and 0 <= nidx < len(result_sections):
            section.next_section = result_sections[nidx]

    # ── Velden: hergebruik-op-id ────────────────────────────────────────────────
    result_fields = []
    for fi in data.fields:
        field = existing_fields.get(fi.id) if fi.id is not None else None
        if field is None:
            field = FormField()
            form.fields.append(field)
        field.field_type = fi.field_type
        field.label = fi.label
        field.help_text = fi.help_text
        field.required = fi.required
        field.position = fi.position
        field.min_value = fi.min_value
        field.max_value = fi.max_value
        field.min_length = fi.min_length
        field.max_length = fi.max_length
        field.regex_pattern = fi.regex_pattern
        field.rating_max = fi.rating_max
        field.rating_low_label = fi.rating_low_label
        field.rating_high_label = fi.rating_high_label
        idx = fi.section_index
        field.section = (
            result_sections[idx] if idx is not None and 0 <= idx < len(result_sections) else None
        )

        # Opties: hergebruik-op-id binnen dit veld.
        existing_options = {o.id: o for o in field.options}
        result_options = []
        for oi in fi.options:
            option = existing_options.get(oi.id) if oi.id is not None else None
            if option is None:
                option = FormFieldOption()
                field.options.append(option)
            option.label = oi.label
            option.value = oi.value
            option.position = oi.position
            option.is_other = oi.is_other
            option.skip_to_end = oi.skip_to_end
            sidx = oi.skip_to_section_index
            option.skip_to_section = (
                result_sections[sidx] if sidx is not None and 0 <= sidx < len(result_sections) else None
            )
            result_options.append(option)
        keep_options = set(result_options)
        for option in list(field.options):
            if option not in keep_options:
                field.options.remove(option)

        result_fields.append(field)

    # Verwijder velden die niet meer voorkomen (hun antwoorden vallen mee weg).
    keep_fields = set(result_fields)
    for field in list(form.fields):
        if field not in keep_fields:
            form.fields.remove(field)


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
        is_anonymous=data.is_anonymous,
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
    form.is_anonymous = data.is_anonymous
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


@router.get("/forms/{form_id}/submissions")
def list_submissions(
    form_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Individuele inzendingen (admin-only, #356) — bevat de antwoorden per veld."""
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Formulier niet gevonden")
    return build_submissions_view(db, form)


@router.delete("/forms/{form_id}/submissions/{submission_id}", status_code=204)
def delete_submission(
    form_id: int,
    submission_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Verwijder één inzending (admin-only, #356). Cascade verwijdert de antwoorden."""
    sub = (
        db.query(FormSubmission)
        .filter(FormSubmission.id == submission_id, FormSubmission.form_id == form_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Inzending niet gevonden")
    db.delete(sub)
    db.commit()


@router.get("/forms/{form_id}/export")
def export_form(
    form_id: int,
    format: str = Query("ods"),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Formulier niet gevonden")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", form.title or "formulier").strip("_") or "formulier"
    if format != "ods":
        raise HTTPException(status_code=422, detail="Ongeldig formaat (enkel ods).")
    return Response(
        content=export_ods(db, form),
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={"Content-Disposition": f'attachment; filename="{safe}.ods"'},
    )


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


@router.post("/forms/by-token/{share_token}/submit", response_model=SubmissionResult,
             dependencies=[Depends(form_submit_limiter)])
def submit_form(
    share_token: str,
    data: SubmissionIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    form = _load_public_form(db, share_token)
    assert_open_for_submission(db, form)
    answers = build_answers(form, data.answers)

    # Anoniem (#343): geen submitter bewaren. Anders het contactblok-adres.
    sub_name = None if form.is_anonymous else data.submitter_name
    sub_email = None if form.is_anonymous else data.submitter_email

    submission = FormSubmission(
        form_id=form.id,
        submitter_name=sub_name,
        submitter_email=sub_email,
        edit_token=_new_token() if form.allow_edit else None,
    )
    for row in answers:
        submission.answers.append(row)
    db.add(submission)
    db.commit()
    db.refresh(submission)

    if form.send_confirmation and not form.is_anonymous and sub_email:
        edit_link = None
        if form.allow_edit and submission.edit_token:
            edit_link = f"{settings.frontend_url}/formulier/{form.share_token}/edit/{submission.edit_token}"
        try:
            send_form_confirmation(
                to_email=sub_email,
                form_title=form.title,
                name=sub_name,
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


@router.put("/forms/edit/{edit_token}", response_model=SubmissionResult,
            dependencies=[Depends(form_submit_limiter)])
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
