"""Server-rendered berichten-pagina (#398) — de micro-pilot van §21.4.

'Contacteer ons' als geseed formulier (slug 'berichten'): capture → submission
→ SubmissionCreated → behartigen-taak (workflow). Deze route is gespecialiseerd
op dat ene formulier; de generieke htmx-render van álle formulieren volgt met
de React-exit (#405).
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.forms.models import Form as FormModel
from app.limiter import form_submit_limiter
from app.ui import templates
from app.i18n import _

router = APIRouter(include_in_schema=False)

BERICHTEN_SLUG = "berichten"


def _berichten_form(db: Session) -> FormModel | None:
    return db.query(FormModel).filter(FormModel.slug == BERICHTEN_SLUG).first()


@router.get("/berichten", response_class=HTMLResponse)
def berichten_page(request: Request, db: Session = Depends(get_db)):
    from app.ui import site_context

    form = _berichten_form(db)
    return templates.TemplateResponse(request, "berichten.html", {
        **site_context(db, request), "form": form, "error": None})


@router.post("/berichten", response_class=HTMLResponse,
             dependencies=[Depends(form_submit_limiter)])
def berichten_submit(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    naam: str = Form(""),
    email: str = Form(""),
    bericht: str = Form(""),
):
    form = _berichten_form(db)
    naam, email, bericht = naam.strip(), email.strip(), bericht.strip()
    if form is None:
        return templates.TemplateResponse(
            request, "_berichten_form.html",
            {"form": None, "error": _("Berichten zijn tijdelijk niet beschikbaar."),
             "naam": naam, "email": email, "bericht": bericht})
    # Niet-anoniem contactformulier: naam én een geldig e-mailadres verplicht (#501).
    if not naam or "@" not in email or not bericht:
        return templates.TemplateResponse(
            request, "_berichten_form.html",
            {"form": form, "error": _("Vul je naam, een geldig e-mailadres en je bericht in."),
             "naam": naam, "email": email, "bericht": bericht})

    from app.domains.forms.api import submit_bericht

    submit_bericht(db, naam=naam, email=email or None, bericht=bericht,
                   background_tasks=background_tasks)
    # Terug naar de homepage met een bedankt-flash (#451) i.p.v. op /berichten
    # blijven hangen; htmx doet een volledige navigatie op de HX-Redirect-header.
    return HTMLResponse("", headers={"HX-Redirect": "/?bericht=verzonden"})


# ── Publieke formulier-render (React-exit 405-c, #405) ─────────────────────────
#
# Server-rendered op /formulier/{share_token} — alle veldtypes; branching wordt
# door de servicelaag afgehandeld (overgeslagen secties tellen niet als
# verplicht, zie build_answers/_traversed_field_ids). Wijzig-flow via
# /formulier/{token}/edit/{edit_token} (zelfde template, voorgevuld).

def _answers_from_form(form_model, form_data) -> list:
    """Vertaal geposte f{field_id}-waarden naar AnswerIn-payloads."""
    from decimal import Decimal, InvalidOperation

    from app.domains.forms.schemas import AnswerIn

    answers = []
    for field in form_model.fields:
        key = f"f{field.id}"
        if field.field_type == "info":
            continue
        if field.field_type == "checkbox":
            raw = [v for v in form_data.getlist(key) if v]
            option_ids = [int(v) for v in raw if str(v).isdigit()]
            if option_ids:
                answers.append(AnswerIn(field_id=field.id, option_ids=option_ids,
                                        other_text=(form_data.get(f"{key}_other") or None)))
        elif field.field_type in ("select", "radio"):
            raw = form_data.get(key)
            if raw and str(raw).isdigit():
                answers.append(AnswerIn(field_id=field.id, option_ids=[int(raw)],
                                        other_text=(form_data.get(f"{key}_other") or None)))
        elif field.field_type == "number":
            raw_num = form_data.get(key)
            num_text = raw_num.strip() if isinstance(raw_num, str) else ""
            if num_text:
                try:
                    answers.append(AnswerIn(field_id=field.id,
                                            number=Decimal(num_text.replace(",", "."))))
                except InvalidOperation:
                    answers.append(AnswerIn(field_id=field.id, text=num_text))
        elif field.field_type == "rating":
            raw = form_data.get(key)
            if raw and str(raw).isdigit():
                answers.append(AnswerIn(field_id=field.id, rating=int(raw)))
        else:  # text, textarea, email, phone
            raw = form_data.get(key)
            text = raw.strip() if isinstance(raw, str) else ""
            if text:
                answers.append(AnswerIn(field_id=field.id, text=text))
    return answers


def _prefill_from_session(db, request, submitter_name, submitter_email):
    """Voorinvullen van naam/e-mail voor een ingelogd lid (#454), zonder een
    reeds ingevulde waarde te overschrijven. Mag het renderen nooit breken."""
    if submitter_name or submitter_email or request is None:
        return submitter_name, submitter_email
    try:
        from app.domains.auth.api import (
            SESSION_COOKIE, login_person_for_email, read_session_value)

        email = read_session_value(request.cookies.get(SESSION_COOKIE))
        if not email:
            return submitter_name, submitter_email
        person = login_person_for_email(db, email)
        if person is not None:
            naam = f"{person.first_name} {person.last_name}".strip()
            return naam or submitter_name, email
        return submitter_name, email
    except Exception:
        return submitter_name, submitter_email


def _form_render_ctx(db, form_model, request, *, values=None, error=None,
                     submitter_name="", submitter_email="") -> dict:
    from app.ui import site_context

    submitter_name, submitter_email = _prefill_from_session(
        db, request, submitter_name, submitter_email)

    # Veldenlijst in weergavevolgorde: secties (op positie) met hun velden,
    # daarna de ongegroepeerde velden.
    sections = sorted(form_model.sections, key=lambda s: (s.position, s.id))
    grouped = []
    for section in sections:
        grouped.append({"section": section,
                        "fields": [f for f in form_model.fields if f.section_id == section.id]})
    loose = [f for f in form_model.fields if f.section_id is None]

    # Stap-per-stap-wizard (#454): enkel bij ≥2 secties en geen losse velden —
    # de branching (sectie- en optie-niveau) wordt vertaald naar stap-indices zodat
    # de Alpine-wizard client-side dezelfde route volgt als de server (#336). Bij
    # afwijking blijft de server de waarheid (die valideert de bereikte route).
    idx_by_id = {s.id: i for i, s in enumerate(sections)}
    wizard = len(sections) >= 2 and not loose
    wizard_steps = []
    if wizard:
        for section in sections:
            skips = []
            for f in (fld for fld in form_model.fields if fld.section_id == section.id):
                for o in f.options:
                    if o.skip_to_section_id is not None or o.skip_to_end:
                        skips.append({
                            "opt": o.id,
                            "section": idx_by_id.get(o.skip_to_section_id),
                            "end": bool(o.skip_to_end),
                        })
            wizard_steps.append({
                "id": section.id,
                "end": bool(section.next_is_end),
                "next": idx_by_id.get(section.next_section_id)
                        if section.next_section_id is not None else None,
                "skips": skips,
            })

    return {
        **site_context(db, request), "form": form_model, "grouped": grouped,
        "loose_fields": loose, "values": values or {}, "error": error,
        "submitter_name": submitter_name, "submitter_email": submitter_email,
        "wizard": wizard, "wizard_steps": wizard_steps,
    }


def _load_open_form(db, share_token: str):
    from app.domains.forms.service import assert_open_for_submission

    form_model = (db.query(FormModel)
                  .filter(FormModel.share_token == share_token).first())
    if form_model is None:
        raise HTTPException(status_code=404, detail=_("Formulier niet gevonden"))
    assert_open_for_submission(db, form_model)
    return form_model


@router.get("/formulier/{share_token}", response_class=HTMLResponse)
def formulier_page(share_token: str, request: Request, db: Session = Depends(get_db)):
    form_model = _load_open_form(db, share_token)
    return templates.TemplateResponse(request, "formulier.html",
                                      _form_render_ctx(db, form_model, request))


@router.post("/formulier/{share_token}", response_class=HTMLResponse,
             dependencies=[Depends(form_submit_limiter)])
async def formulier_submit(share_token: str, request: Request,
                           background_tasks: BackgroundTasks,
                           db: Session = Depends(get_db)):
    from app.domains.forms.router import submit_form
    from app.domains.forms.schemas import SubmissionIn

    form_model = _load_open_form(db, share_token)
    form_data = await request.form()
    values = {k: form_data.getlist(k) if len(form_data.getlist(k)) > 1 else (form_data.get(k) or "")
              for k in form_data.keys()}
    naam = (form_data.get("submitter_name") or "")
    naam = naam.strip() if isinstance(naam, str) else ""
    email = (form_data.get("submitter_email") or "")
    email = email.strip() if isinstance(email, str) else ""

    if not form_model.is_anonymous and (not naam or "@" not in email):
        ctx = _form_render_ctx(db, form_model, request, values=values,
                               error=_("Vul je naam en een geldig e-mailadres in."),
                               submitter_name=naam, submitter_email=email)
        return templates.TemplateResponse(request, "formulier.html", ctx)

    payload = SubmissionIn(submitter_name=naam or None, submitter_email=email or None,
                           answers=_answers_from_form(form_model, form_data))
    try:
        result = submit_form(share_token, payload, background_tasks, db=db)
    except HTTPException as exc:
        ctx = _form_render_ctx(db, form_model, request, values=values, error=str(exc.detail),
                               submitter_name=naam, submitter_email=email)
        return templates.TemplateResponse(request, "formulier.html", ctx)

    from app.ui import site_context
    return templates.TemplateResponse(request, "formulier_klaar.html", {
        **site_context(db, request), "form": form_model, "updated": False,
        "edit_link": (f"/formulier/{share_token}/edit/{result.edit_token}"
                      if result.edit_token else None)})


@router.get("/formulier/{share_token}/edit/{edit_token}", response_class=HTMLResponse)
def formulier_edit_page(share_token: str, edit_token: str, request: Request,
                        db: Session = Depends(get_db)):
    from app.domains.forms.models import FormSubmission

    submission = (db.query(FormSubmission)
                  .filter(FormSubmission.edit_token == edit_token).first())
    form_model = _load_open_form(db, share_token)
    if submission is None or submission.form_id != form_model.id or not form_model.allow_edit:
        raise HTTPException(status_code=404, detail=_("Inzending niet gevonden"))

    # Voorvullen: antwoorden terug naar f{field_id}-waarden.
    values: dict = {}
    for answer in submission.answers:
        key = f"f{answer.field_id}"
        if answer.value_option_id is not None:
            values.setdefault(key, [])
            if isinstance(values[key], list):
                values[key].append(str(answer.value_option_id))
            if answer.value_text:
                values[f"{key}_other"] = answer.value_text
        elif answer.value_rating is not None:
            values[key] = str(answer.value_rating)
        elif answer.value_number is not None:
            values[key] = str(answer.value_number)
        elif answer.value_text is not None:
            values[key] = answer.value_text
    ctx = _form_render_ctx(db, form_model, request, values=values,
                           submitter_name=submission.submitter_name or "",
                           submitter_email=submission.submitter_email or "")
    ctx["edit_token"] = edit_token
    return templates.TemplateResponse(request, "formulier.html", ctx)


@router.post("/formulier/{share_token}/edit/{edit_token}", response_class=HTMLResponse,
             dependencies=[Depends(form_submit_limiter)])
async def formulier_edit_submit(share_token: str, edit_token: str, request: Request,
                                db: Session = Depends(get_db)):
    from app.domains.forms.router import update_submission
    from app.domains.forms.schemas import SubmissionIn

    form_model = _load_open_form(db, share_token)
    form_data = await request.form()
    naam = form_data.get("submitter_name")
    naam = naam.strip() if isinstance(naam, str) else ""
    email = form_data.get("submitter_email")
    email = email.strip() if isinstance(email, str) else ""
    payload = SubmissionIn(submitter_name=naam or None, submitter_email=email or None,
                           answers=_answers_from_form(form_model, form_data))
    try:
        update_submission(edit_token, payload, db=db)
    except HTTPException as exc:
        ctx = _form_render_ctx(db, form_model, request, error=str(exc.detail),
                               submitter_name=naam, submitter_email=email)
        ctx["edit_token"] = edit_token
        return templates.TemplateResponse(request, "formulier.html", ctx)

    from app.ui import site_context
    return templates.TemplateResponse(request, "formulier_klaar.html", {
        **site_context(db, request), "form": form_model, "updated": True, "edit_link": None})
