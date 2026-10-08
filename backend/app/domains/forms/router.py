import logging
import re
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import User, get_current_admin
from app.domains.forms.export import build_submissions_view, export_ods
from app.domains.forms.models import (
    Form,
    FormStatus,
    FormSubmission,
)
from app.domains.forms.results import compute_results
from app.domains.forms.schemas import (
    EditSubmissionOut,
    FormAdminOut,
    FormCreate,
    FormUpdate,
    PublicForm,
    SubmissionIn,
    SubmissionResult,
)
from app.domains.forms.service import (
    FormulierFout,
    apply_definition,
    assert_open_for_submission,
    assert_submitter,
    build_answers,
    update_settings,
    validate_definition,
)
from app.domains.mail.api import send_form_confirmation
from app.i18n import _
from app.limiter import form_submit_limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["forms"])


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _unique_share_token(db: Session) -> str:
    for _poging in range(10):
        tok = _new_token()
        if not db.query(Form.id).filter(Form.share_token == tok).first():
            return tok
    raise HTTPException(status_code=500, detail=_("Kon geen unieke deellink genereren."))


def _submission_count(db: Session, form_id: int) -> int:
    return (
        db.query(func.count(FormSubmission.id)).filter(FormSubmission.form_id == form_id).scalar()
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
    validate_definition(data)
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
    apply_definition(form, data)
    db.add(form)
    db.commit()
    db.refresh(form)
    return _admin_out(db, form)


@router.get("/forms/{form_id}", response_model=FormAdminOut)
def get_form(
    form_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail=_("Formulier niet gevonden"))
    return _admin_out(db, form)


@router.put("/forms/{form_id}", response_model=FormAdminOut)
def update_form(
    form_id: int,
    data: FormUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    validate_definition(data)
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail=_("Formulier niet gevonden"))
    # Dezelfde functie als json_import (#635-3), zodat de twee ingangen niet
    # opnieuw uiteen kunnen lopen.
    update_settings(form, data)
    try:
        apply_definition(form, data)
    except FormulierFout as exc:
        # #1347: the definition would drop an answered question or a chosen
        # option. Refused before `apply_definition` changes anything, and nothing
        # is committed, so the settings above are not stored either.
        raise HTTPException(status_code=422, detail=str(exc)) from None
    db.commit()
    db.refresh(form)
    return _admin_out(db, form)


@router.delete("/forms/{form_id}", status_code=204)
def delete_form(
    form_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    from app.domains.forms import service

    # One way to delete, the service's: it refuses a form whose answers a
    # registration holds (CR-14 F11) — the API says so with a 409.
    try:
        service.delete_form(db, form_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=_("Formulier niet gevonden"))
    except service.FormulierFout as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/forms/{form_id}/results")
def form_results(
    form_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail=_("Formulier niet gevonden"))
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
        raise HTTPException(status_code=404, detail=_("Formulier niet gevonden"))
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
        raise HTTPException(status_code=404, detail=_("Inzending niet gevonden"))
    from app.domains.forms import service

    try:
        service.delete_submission(db, form_id, submission_id)
    except service.FormulierFout as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/forms/{form_id}/export")
def export_form(
    form_id: int,
    format: str = Query("ods"),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail=_("Formulier niet gevonden"))
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", form.title or "formulier").strip("_") or "formulier"
    if format != "ods":
        raise HTTPException(status_code=422, detail=_("Ongeldig formaat (enkel ods)."))
    return Response(
        content=export_ods(db, form),
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={"Content-Disposition": f'attachment; filename="{safe}.ods"'},
    )


# ── Publiek: invullen ───────────────────────────────────────────────────────────


def _load_public_form(db: Session, share_token: str) -> Form:
    form = db.query(Form).filter(Form.share_token == share_token).first()
    # Concept-formulieren zijn niet publiek zichtbaar.
    if not form or form.status is FormStatus.DRAFT:
        raise HTTPException(status_code=404, detail=_("Formulier niet gevonden"))
    return form


@router.get("/forms/by-token/{share_token}", response_model=PublicForm)
def get_public_form(share_token: str, db: Session = Depends(get_db)):
    """The form, and the signed time a JSON client sends back with it (#1297)."""
    from app.kernel.form_guard import issue_token

    public = PublicForm.model_validate(_load_public_form(db, share_token))
    return public.model_copy(update={"form_ts": issue_token()})


@router.post(
    "/forms/by-token/{share_token}/submit",
    response_model=SubmissionResult,
    dependencies=[Depends(form_submit_limiter)],
)
def submit_form_http(
    share_token: str,
    data: SubmissionIn,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """The JSON way in. Same guard as the screen (#1297): the honeypot and the
    signed time travel in the body (`website`, `form_ts`); the time comes from
    `GET /forms/by-token/{share_token}`."""
    from app.kernel.form_guard import Proof
    from app.limiter import client_ip

    proof = Proof(honeypot=data.website, token=data.form_ts, client_ip=client_ip(request))
    return submit_form(db, share_token, data, background_tasks, proof=proof)


def submit_form(
    db: Session, share_token: str, data: SubmissionIn, background_tasks, *, proof
) -> SubmissionResult:
    """One public submission, for the screen and the JSON way in alike.

    A submission the guard drops (#1297) answers like a stored one — `status`
    "ok" — but with id 0 and no edit link, and leaves no row and no mail.
    """
    from app.kernel import form_guard

    form = _load_public_form(db, share_token)
    assert_open_for_submission(db, form)
    if form_guard.refused(proof, f"form {form.id}"):
        return SubmissionResult(id=0, status="ok", edit_token=None)
    assert_submitter(form, data.submitter_name, data.submitter_email)
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
            from app.kernel.tenant_config import tenant_home_url

            # `tenant_home_url` en niet `tenant_base_url` (#928). Geen bugfix maar
            # een betekeniscorrectie, en het verschil is de moeite waard omdat het
            # klein is: allebei zetten ze de pad-prefix op een platform-host, dus de
            # link was niet stuk. Ze lopen uiteen zodra de afdeling een EIGEN domein
            # heeft. Dan geeft `tenant_base_url` de host waar de beheerder toevallig
            # werkte (`https://platform.example/raakmillegem`) en `tenant_home_url`
            # het adres waar de afdeling woont (`https://raakmillegem.be`).
            #
            # Voor een link in een MAIL is dat tweede het juiste: er is geen "terug".
            # Hij wordt geopend vanuit een andere browser, zonder de cookie die de
            # afdeling onthield, misschien weken later — en dan hoort er het adres
            # van de afdeling te staan en niet dat van de beheerder zijn werkdag.
            #
            # De SLEUTEL-URL blijft staan, ook als het formulier een slug heeft
            # (#690/#928): bewerken bestaat alleen onder
            # `/formulier/{share_token}/edit/{edit_token}`. De slug verandert wat je
            # DEELT, niet waarlangs een inzending bewerkt wordt.
            edit_link = (
                f"{tenant_home_url(db)}/formulier/{form.share_token}/edit/{submission.edit_token}"
            )
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
            {
                "field_id": ans.field_id,
                "text": None,
                "number": None,
                "option_ids": [],
                "rating": None,
                "other_text": None,
            },
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
        raise HTTPException(status_code=404, detail=_("Inzending niet gevonden"))
    form = db.query(Form).filter(Form.id == submission.form_id).first()
    return {
        "form": form,
        "submitter_name": submission.submitter_name,
        "submitter_email": submission.submitter_email,
        "answers": _answers_payload(submission),
    }


@router.put(
    "/forms/edit/{edit_token}",
    response_model=SubmissionResult,
    dependencies=[Depends(form_submit_limiter)],
)
def update_submission(
    edit_token: str,
    data: SubmissionIn,
    db: Session = Depends(get_db),
):
    submission = db.query(FormSubmission).filter(FormSubmission.edit_token == edit_token).first()
    if not submission:
        raise HTTPException(status_code=404, detail=_("Inzending niet gevonden"))
    form = db.query(Form).filter(Form.id == submission.form_id).first()
    if not form or not form.allow_edit:
        raise HTTPException(status_code=403, detail=_("Wijzigen is niet toegestaan."))
    if form.status is not FormStatus.OPEN:
        raise HTTPException(status_code=403, detail=_("Dit formulier staat niet (meer) open."))
    assert_submitter(form, data.submitter_name, data.submitter_email)

    from app.domains.forms.service import replace_answers

    replace_answers(submission, build_answers(form, data.answers))
    submission.submitter_name = data.submitter_name
    submission.submitter_email = data.submitter_email
    db.commit()
    return SubmissionResult(id=submission.id, status="updated", edit_token=submission.edit_token)
