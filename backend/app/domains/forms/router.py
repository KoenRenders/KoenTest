import logging
import re
import secrets

from fastapi import Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import User, get_current_admin
from app.domains.forms.export import export_ods
from app.domains.forms.models import (
    Form,
    FormStatus,
    FormSubmission,
)
from app.domains.forms.schemas import (
    FormAdminOut,
    SubmissionIn,
    SubmissionResult,
)
from app.domains.forms.service import (
    assert_open_for_submission,
    assert_submitter,
    build_answers,
)
from app.domains.mail.api import send_form_confirmation
from app.i18n import _

logger = logging.getLogger(__name__)

# No JSON route is left in this file (CR-13 phase 4b, #1251): the twelve under
# `/api/v1/forms` had no caller but their own tests. What stands here are the
# functions the screens still reach through `forms.api` — the public submission,
# the change through the edit link, the export — and they move to `service.py`
# in phase 4c, where their entries in `rules_baseline.py` settle.


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


# ── Export ──────────────────────────────────────────────────────────────────────


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
