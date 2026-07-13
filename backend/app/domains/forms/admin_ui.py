"""Server-rendered form-builder (React-exit 405-c2, #405 — optie a §21):
lijstgebaseerd bouwen — secties en velden met op/aflopen, alle veldtypes,
branching via selects, JSON-import als vluchtluik (zelfde payload als de
admin-API), plus de inzendingen-tab en de afdrukweergave.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf
from app.domains.forms.models import FIELD_TYPES, FORM_STATUSES, Form as FormModel
from app.domains.forms.models import FormField, FormFieldOption, FormSection, FormSubmission
from app.ui import admin_nav, templates

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/formulieren")


def _csrf(request: Request) -> str:
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


def _form_or_404(db: Session, form_id: int) -> FormModel:
    form = db.query(FormModel).filter(FormModel.id == form_id).first()
    if form is None:
        raise HTTPException(status_code=404, detail="Formulier niet gevonden")
    return form


def _builder_ctx(request: Request, db: Session, form: FormModel, **extra) -> dict:
    sections = sorted(form.sections, key=lambda s: s.position)
    grouped = [{"section": s,
                "fields": sorted((f for f in form.fields if f.section_id == s.id),
                                 key=lambda f: f.position)}
               for s in sections]
    loose = sorted((f for f in form.fields if f.section_id is None),
                   key=lambda f: f.position)
    ctx = {
        "form": form, "grouped": grouped, "loose_fields": loose,
        "sections": sections, "field_types": FIELD_TYPES, "statuses": FORM_STATUSES,
        "submission_count": db.query(FormSubmission)
                              .filter(FormSubmission.form_id == form.id).count(),
        "csrf_token": _csrf(request), "error": None,
    }
    ctx.update(extra)
    return ctx


def _builder_response(request: Request, db: Session, form: FormModel, **extra):
    return templates.TemplateResponse(request, "_fb_builder.html",
                                      _builder_ctx(request, db, form, **extra))


# ── Lijst + aanmaken ───────────────────────────────────────────────────────────

@router.get("/admin/formulieren", response_class=HTMLResponse)
def formulieren_page(request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui)):
    forms = db.query(FormModel).order_by(FormModel.created_at.desc()).all()
    return templates.TemplateResponse(request, "admin_formulieren.html", {
        "nav_items": NAV, "forms": forms, "csrf_token": _csrf(request)})


@router.post("/admin/formulieren", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def formulier_aanmaken(request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_admin_ui),
                       title: str = Form(...)):
    from app.domains.forms.router import _unique_share_token

    form = FormModel(title=title.strip() or "Naamloos formulier",
                     share_token=_unique_share_token(db))
    db.add(form)
    db.commit()
    return _builder_response(request, db, form)


@router.get("/admin/formulieren/{form_id}", response_class=HTMLResponse)
def formulier_builder(form_id: int, request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui)):
    form = _form_or_404(db, form_id)
    if request.headers.get("hx-request"):
        return _builder_response(request, db, form)
    return templates.TemplateResponse(request, "admin_formulier_builder.html", {
        "nav_items": NAV, **_builder_ctx(request, db, form)})


@router.post("/admin/formulieren/{form_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def formulier_verwijderen(form_id: int, request: Request, db: Session = Depends(get_db),
                          email: str = Depends(require_admin_ui)):
    form = _form_or_404(db, form_id)
    db.delete(form)
    db.commit()
    forms = db.query(FormModel).order_by(FormModel.created_at.desc()).all()
    return templates.TemplateResponse(request, "_fb_lijst.html", {
        "forms": forms, "csrf_token": _csrf(request)})


# ── Instellingen ───────────────────────────────────────────────────────────────

@router.post("/admin/formulieren/{form_id}/instellingen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def instellingen_opslaan(form_id: int, request: Request, db: Session = Depends(get_db),
                         email: str = Depends(require_admin_ui),
                         title: str = Form(...), description: str = Form(""),
                         status: str = Form("draft"), max_submissions: str = Form(""),
                         send_confirmation: str = Form(""), confirmation_message: str = Form(""),
                         allow_edit: str = Form(""), is_anonymous: str = Form(""),
                         requires_login: str = Form("")):
    form = _form_or_404(db, form_id)
    if status not in FORM_STATUSES:
        raise HTTPException(status_code=422, detail=f"Ongeldige status: {status}")
    form.title = title.strip() or form.title
    form.description = description.strip() or None
    form.status = status
    form.max_submissions = int(max_submissions) if max_submissions.strip().isdigit() else None
    form.send_confirmation = bool(send_confirmation)
    form.confirmation_message = confirmation_message.strip() or None
    form.allow_edit = bool(allow_edit)
    form.is_anonymous = bool(is_anonymous)
    form.requires_login = bool(requires_login)
    db.commit()
    return _builder_response(request, db, form)


# ── Secties ────────────────────────────────────────────────────────────────────

def _renumber(items) -> None:
    for i, item in enumerate(sorted(items, key=lambda x: x.position)):
        item.position = i


@router.post("/admin/formulieren/{form_id}/secties", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def sectie_toevoegen(form_id: int, request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui), title: str = Form("")):
    form = _form_or_404(db, form_id)
    form.sections.append(FormSection(title=title.strip() or None,
                                     position=len(form.sections)))
    db.commit()
    return _builder_response(request, db, form)


@router.post("/admin/formulieren/{form_id}/secties/{section_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def sectie_bewerken(form_id: int, section_id: int, request: Request,
                    db: Session = Depends(get_db), email: str = Depends(require_admin_ui),
                    title: str = Form(""), description: str = Form(""),
                    next_section_id: str = Form(""), next_is_end: str = Form("")):
    form = _form_or_404(db, form_id)
    section = next((s for s in form.sections if s.id == section_id), None)
    if section is None:
        raise HTTPException(status_code=404, detail="Sectie niet gevonden")
    section.title = title.strip() or None
    section.description = description.strip() or None
    target: Optional[int] = int(next_section_id) if next_section_id.strip().isdigit() else None
    if target is not None:
        doel = next((s for s in form.sections if s.id == target), None)
        if doel is None or doel.position <= section.position:
            raise HTTPException(status_code=422,
                                detail="Een sectie-sprong moet naar een latere sectie gaan.")
    section.next_section_id = target
    section.next_is_end = bool(next_is_end)
    db.commit()
    return _builder_response(request, db, form)


@router.post("/admin/formulieren/{form_id}/secties/{section_id}/verplaats",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def sectie_verplaatsen(form_id: int, section_id: int, request: Request,
                       db: Session = Depends(get_db), email: str = Depends(require_admin_ui),
                       richting: str = Form("op")):
    form = _form_or_404(db, form_id)
    ordered = sorted(form.sections, key=lambda s: s.position)
    index = next((i for i, s in enumerate(ordered) if s.id == section_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail="Sectie niet gevonden")
    buur = index - 1 if richting == "op" else index + 1
    if 0 <= buur < len(ordered):
        ordered[index].position, ordered[buur].position = (
            ordered[buur].position, ordered[index].position)
    db.commit()
    return _builder_response(request, db, form)


@router.post("/admin/formulieren/{form_id}/secties/{section_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def sectie_verwijderen(form_id: int, section_id: int, request: Request,
                       db: Session = Depends(get_db), email: str = Depends(require_admin_ui)):
    form = _form_or_404(db, form_id)
    section = next((s for s in form.sections if s.id == section_id), None)
    if section is not None:
        form.sections.remove(section)
        _renumber(form.sections)
    db.commit()
    return _builder_response(request, db, form)


# ── Velden ─────────────────────────────────────────────────────────────────────

@router.post("/admin/formulieren/{form_id}/velden", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def veld_toevoegen(form_id: int, request: Request, db: Session = Depends(get_db),
                   email: str = Depends(require_admin_ui),
                   label: str = Form(...), field_type: str = Form("text"),
                   section_id: str = Form("")):
    form = _form_or_404(db, form_id)
    if field_type not in FIELD_TYPES:
        raise HTTPException(status_code=422, detail=f"Ongeldig veldtype: {field_type}")
    if not label.strip():
        raise HTTPException(status_code=422, detail="Elk veld heeft een vraag/label nodig.")
    sid = int(section_id) if section_id.strip().isdigit() else None
    broers = [f for f in form.fields if f.section_id == sid]
    form.fields.append(FormField(label=label.strip(), field_type=field_type,
                                 section_id=sid, position=len(broers)))
    db.commit()
    return _builder_response(request, db, form)


@router.post("/admin/formulieren/{form_id}/velden/{field_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def veld_bewerken(form_id: int, field_id: int, request: Request,
                  db: Session = Depends(get_db), email: str = Depends(require_admin_ui),
                  label: str = Form(...), help_text: str = Form(""),
                  required: str = Form(""), min_length: str = Form(""),
                  max_length: str = Form(""), min_value: str = Form(""),
                  max_value: str = Form(""), rating_max: str = Form(""),
                  rating_low_label: str = Form(""), rating_high_label: str = Form("")):
    form = _form_or_404(db, form_id)
    veld = next((f for f in form.fields if f.id == field_id), None)
    if veld is None:
        raise HTTPException(status_code=404, detail="Veld niet gevonden")
    if not label.strip():
        raise HTTPException(status_code=422, detail="Elk veld heeft een vraag/label nodig.")
    veld.label = label.strip()
    veld.help_text = help_text.strip() or None
    veld.required = bool(required)
    veld.min_length = int(min_length) if min_length.strip().isdigit() else None
    veld.max_length = int(max_length) if max_length.strip().isdigit() else None
    veld.min_value = min_value.strip() or None
    veld.max_value = max_value.strip() or None
    veld.rating_max = int(rating_max) if rating_max.strip().isdigit() else None
    veld.rating_low_label = rating_low_label.strip() or None
    veld.rating_high_label = rating_high_label.strip() or None
    db.commit()
    return _builder_response(request, db, form)


@router.post("/admin/formulieren/{form_id}/velden/{field_id}/verplaats",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def veld_verplaatsen(form_id: int, field_id: int, request: Request,
                     db: Session = Depends(get_db), email: str = Depends(require_admin_ui),
                     richting: str = Form("op")):
    form = _form_or_404(db, form_id)
    veld = next((f for f in form.fields if f.id == field_id), None)
    if veld is None:
        raise HTTPException(status_code=404, detail="Veld niet gevonden")
    broers = sorted((f for f in form.fields if f.section_id == veld.section_id),
                    key=lambda f: f.position)
    index = broers.index(veld)
    buur = index - 1 if richting == "op" else index + 1
    if 0 <= buur < len(broers):
        broers[index].position, broers[buur].position = (
            broers[buur].position, broers[index].position)
    db.commit()
    return _builder_response(request, db, form)


@router.post("/admin/formulieren/{form_id}/velden/{field_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def veld_verwijderen(form_id: int, field_id: int, request: Request,
                     db: Session = Depends(get_db), email: str = Depends(require_admin_ui)):
    form = _form_or_404(db, form_id)
    veld = next((f for f in form.fields if f.id == field_id), None)
    if veld is not None:
        form.fields.remove(veld)
    db.commit()
    return _builder_response(request, db, form)


# ── Opties ─────────────────────────────────────────────────────────────────────

@router.post("/admin/formulieren/{form_id}/velden/{field_id}/opties",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def optie_toevoegen(form_id: int, field_id: int, request: Request,
                    db: Session = Depends(get_db), email: str = Depends(require_admin_ui),
                    label: str = Form(...), is_other: str = Form("")):
    form = _form_or_404(db, form_id)
    veld = next((f for f in form.fields if f.id == field_id), None)
    if veld is None or veld.field_type not in ("select", "radio", "checkbox"):
        raise HTTPException(status_code=422, detail="Opties kunnen enkel bij keuzevelden.")
    veld.options.append(FormFieldOption(label=label.strip(), position=len(veld.options),
                                        is_other=bool(is_other)))
    db.commit()
    return _builder_response(request, db, form)


@router.post("/admin/formulieren/{form_id}/opties/{option_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def optie_bewerken(form_id: int, option_id: int, request: Request,
                   db: Session = Depends(get_db), email: str = Depends(require_admin_ui),
                   label: str = Form(...), is_other: str = Form(""),
                   skip_to_section_id: str = Form(""), skip_to_end: str = Form("")):
    form = _form_or_404(db, form_id)
    optie = next((o for f in form.fields for o in f.options if o.id == option_id), None)
    if optie is None:
        raise HTTPException(status_code=404, detail="Optie niet gevonden")
    veld = optie.field
    heeft_sprong = bool(skip_to_end) or skip_to_section_id.strip().isdigit()
    if heeft_sprong and veld.field_type not in ("radio", "select"):
        raise HTTPException(status_code=422,
                            detail="Vertakking kan enkel bij 'één keuze' of 'keuzelijst'.")
    target = int(skip_to_section_id) if skip_to_section_id.strip().isdigit() else None
    if target is not None:
        doel = next((s for s in form.sections if s.id == target), None)
        eigen = next((s for s in form.sections if s.id == veld.section_id), None)
        if doel is None or (eigen is not None and doel.position <= eigen.position):
            raise HTTPException(status_code=422,
                                detail="Een vertakking moet naar een latere sectie springen.")
    optie.label = label.strip() or optie.label
    optie.is_other = bool(is_other)
    optie.skip_to_section_id = target
    optie.skip_to_end = bool(skip_to_end)
    db.commit()
    return _builder_response(request, db, form)


@router.post("/admin/formulieren/{form_id}/opties/{option_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def optie_verwijderen(form_id: int, option_id: int, request: Request,
                      db: Session = Depends(get_db), email: str = Depends(require_admin_ui)):
    form = _form_or_404(db, form_id)
    optie = next((o for f in form.fields for o in f.options if o.id == option_id), None)
    if optie is not None:
        optie.field.options.remove(optie)
    db.commit()
    return _builder_response(request, db, form)


# ── JSON-import (vluchtluik + AI-formaatgids) ──────────────────────────────────

@router.post("/admin/formulieren/{form_id}/json-import", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def json_import(form_id: int, request: Request, db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui), payload: str = Form(...)):
    from app.domains.forms.router import _apply_fields, _validate_form_payload
    from app.domains.forms.schemas import FormUpdate

    form = _form_or_404(db, form_id)
    try:
        data = FormUpdate(**json.loads(payload))
    except (json.JSONDecodeError, ValueError) as exc:
        return _builder_response(request, db, form,
                                 error=f"Ongeldige JSON: {exc}")
    try:
        _validate_form_payload(data)
        form.title = data.title
        form.description = data.description
        form.status = data.status
        _apply_fields(form, data)
        db.commit()
    except HTTPException as exc:
        db.rollback()
        return _builder_response(request, db, form, error=str(exc.detail))
    return _builder_response(request, db, form)


# ── Inzendingen + afdruk ───────────────────────────────────────────────────────

@router.get("/admin/formulieren/{form_id}/inzendingen", response_class=HTMLResponse)
def inzendingen_tab(form_id: int, request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui)):
    from app.domains.forms.api import submission_view

    form = _form_or_404(db, form_id)
    subs = (db.query(FormSubmission).filter(FormSubmission.form_id == form.id)
            .order_by(FormSubmission.id.desc()).all())
    rows = [{"submission": s, "answers": submission_view(db, s.id)} for s in subs]
    return templates.TemplateResponse(request, "_fb_inzendingen.html", {
        "form": form, "rows": rows, "csrf_token": _csrf(request)})


@router.post("/admin/formulieren/{form_id}/inzendingen/{submission_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def inzending_verwijderen(form_id: int, submission_id: int, request: Request,
                          db: Session = Depends(get_db),
                          email: str = Depends(require_admin_ui)):
    sub = (db.query(FormSubmission)
           .filter(FormSubmission.id == submission_id,
                   FormSubmission.form_id == form_id).first())
    if sub is not None:
        db.delete(sub)
        db.commit()
    return inzendingen_tab(form_id, request, db=db, email=email)


@router.get("/admin/formulieren/{form_id}/export")
def inzendingen_export(form_id: int, request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_admin_ui)) -> Response:
    from app.domains.forms.router import export_form

    return export_form(form_id, db=db, _admin=None)  # type: ignore[arg-type]


@router.get("/admin/formulieren/{form_id}/afdruk", response_class=HTMLResponse)
def formulier_afdruk(form_id: int, request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui)):
    form = _form_or_404(db, form_id)
    sections = sorted(form.sections, key=lambda s: s.position)
    grouped = [{"section": s,
                "fields": sorted((f for f in form.fields if f.section_id == s.id),
                                 key=lambda f: f.position)}
               for s in sections]
    loose = sorted((f for f in form.fields if f.section_id is None),
                   key=lambda f: f.position)
    return templates.TemplateResponse(request, "formulier_afdruk.html", {
        "form": form, "grouped": grouped, "loose_fields": loose})
