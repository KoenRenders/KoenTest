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
from app.domains.auth.api import (
    SESSION_COOKIE, admin_user_by_email, csrf_from_request, csrf_token_for,
    require_admin_ui, require_csrf,
)
from app.domains.forms.models import FIELD_TYPES, FORM_STATUSES, Form as FormModel
from app.domains.forms.models import FormField, FormFieldOption, FormSection, FormSubmission
from app.ui import admin_nav, is_fragment_request, templates
from app.i18n import _

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/formulieren")


def _form_or_404(db: Session, form_id: int) -> FormModel:
    form = db.query(FormModel).filter(FormModel.id == form_id).first()
    if form is None:
        raise HTTPException(status_code=404, detail=_("Formulier niet gevonden"))
    return form


def _builder_ctx(request: Request, db: Session, form: FormModel, **extra) -> dict:
    sections = sorted(form.sections, key=lambda s: s.position)
    grouped = [{"section": s,
                "fields": sorted((f for f in form.fields if f.section_id == s.id),
                                 key=lambda f: f.position)}
               for s in sections]
    loose = sorted((f for f in form.fields if f.section_id is None),
                   key=lambda f: f.position)
    # §2.12: nooit een rauwe DB-waarde op het scherm (#641). De veldtypes zijn
    # Engelse codes (`textarea`, `radio`); de form-builder wordt bediend door een
    # bestuurslid, niet door een ontwikkelaar. Per request opgebouwd zodat _() de
    # taal van de tenant volgt (zelfde patroon als de statuslabels bij betalingen).
    veldtype_labels = {
        "text": _("Korte tekst"), "textarea": _("Lange tekst"),
        "number": _("Getal"), "email": _("E-mailadres"),
        "select": _("Keuzelijst"), "radio": _("Eén keuze"),
        "checkbox": _("Meerdere keuzes"), "rating": _("Score"),
        "phone": _("Telefoonnummer"),
    }
    ctx = {
        "form": form, "grouped": grouped, "loose_fields": loose,
        "sections": sections, "field_types": FIELD_TYPES, "statuses": FORM_STATUSES,
        "field_type_labels": veldtype_labels,
        "submission_count": db.query(FormSubmission)
                              .filter(FormSubmission.form_id == form.id).count(),
        "csrf_token": csrf_from_request(request), "error": None,
    }
    ctx.update(extra)
    return ctx


def _builder_response(request: Request, db: Session, form: FormModel, **extra):
    return templates.TemplateResponse(request, "_fb_builder.html",
                                      _builder_ctx(request, db, form, **extra))


# ── Lijst + aanmaken ───────────────────────────────────────────────────────────

# Badge-tonen per status, conform §2.4: concept grijs, open groen, gesloten rood.
# De labels staan bewust NIET hier maar in de route: _() vertaalt naar de taal van
# de actieve tenant, en op moduleniveau zou die keuze bij import bevriezen.
STATUS_TONES = {"draft": "gray", "open": "green", "closed": "red"}


def _status_labels() -> dict[str, str]:
    """Eén woordkeuze voor de filterdropdown én de kaart-badges."""
    return {"draft": _("Concept"), "open": _("Open"), "closed": _("Gesloten")}


@router.get("/admin/formulieren", response_class=HTMLResponse)
def formulieren_page(request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui),
                     q: str = "", status: str = ""):
    """Lijst-index (design-system C1, #585): zoeken op naam + statusfilter.

    Een onbekende status filtert niet — een gemanipuleerde querystring hoort een
    lege lijst noch een 500 op te leveren, gewoon 'alles'.
    """
    query = db.query(FormModel)
    if q.strip():
        query = query.filter(FormModel.title.ilike(f"%{q.strip()}%"))
    if status in FORM_STATUSES:
        query = query.filter(FormModel.status == status)
    forms = query.order_by(FormModel.created_at.desc()).all()
    # De filterbalk vraagt enkel de kaarten op: zou ze de pagina vervangen, dan
    # sneuvelt het zoekveld (en je focus) bij elke aanslag.
    sjabloon = ("_fb_kaarten.html" if is_fragment_request(request)
                else "admin_formulieren.html")
    return templates.TemplateResponse(request, sjabloon, {
        "nav_items": NAV, "forms": forms, "q": q, "status": status,
        "statuses": FORM_STATUSES, "status_labels": _status_labels(),
        "status_tones": STATUS_TONES, "gefilterd": bool(q.strip() or status),
        "csrf_token": csrf_from_request(request)})


@router.get("/admin/formulieren/nieuw", response_class=HTMLResponse)
def formulier_nieuw(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui)):
    """Aanmaken als volledige pagina (#627, §2.8) i.p.v. een modal."""
    return templates.TemplateResponse(request, "admin_formulier_nieuw.html", {
        "nav_items": NAV,
        "csrf_token": csrf_from_request(request),
    })


@router.post("/admin/formulieren", dependencies=[Depends(require_csrf)])
def formulier_aanmaken(request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_admin_ui),
                       title: str = Form(...)) -> Response:
    """Aanmaken opent meteen de paginabrede form-builder (C1, #585).

    De naam wordt in de modal gevraagd; het antwoord is een HX-Redirect zodat de
    browser echt navigeert i.p.v. een detailpaneel naast de lijst te vullen — dat
    master-detail is met #585 verdwenen.
    """
    from app.domains.forms.router import _unique_share_token

    form = FormModel(title=title.strip() or "Naamloos formulier",
                     share_token=_unique_share_token(db))
    db.add(form)
    db.commit()
    return Response(status_code=204,
                    headers={"HX-Redirect": f"/admin/formulieren/{form.id}"})


@router.get("/admin/formulieren/{form_id}", response_class=HTMLResponse)
def formulier_builder(form_id: int, request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui)):
    form = _form_or_404(db, form_id)
    if is_fragment_request(request):
        return _builder_response(request, db, form)
    return templates.TemplateResponse(request, "admin_formulier_builder.html", {
        "nav_items": NAV, **_builder_ctx(request, db, form)})


@router.post("/admin/formulieren/{form_id}/verwijderen",
             dependencies=[Depends(require_csrf)])
def formulier_verwijderen(form_id: int, request: Request, db: Session = Depends(get_db),
                          email: str = Depends(require_admin_ui)) -> Response:
    """Verwijderen gebeurt vanuit de builder, dus terug naar de lijst (#585).

    Voorheen kwam hier een lijstfragment terug voor `#fb-lijst`; dat element
    bestond alleen in de oude master-detail-lijst en dus niet op de pagina waar de
    knop staat — de gebruiker zag niets gebeuren.
    """
    form = _form_or_404(db, form_id)
    db.delete(form)
    db.commit()
    return Response(status_code=204, headers={"HX-Redirect": "/admin/formulieren"})


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
        raise HTTPException(status_code=422, detail=_("Ongeldige status: %(status)s") % {"status": status})
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
        raise HTTPException(status_code=404, detail=_("Sectie niet gevonden"))
    section.title = title.strip() or None
    section.description = description.strip() or None
    target: Optional[int] = int(next_section_id) if next_section_id.strip().isdigit() else None
    if target is not None:
        doel = next((s for s in form.sections if s.id == target), None)
        if doel is None or doel.position <= section.position:
            raise HTTPException(status_code=422,
                                detail=_("Een sectie-sprong moet naar een latere sectie gaan."))
    section.next_section_id = target
    section.next_is_end = bool(next_is_end)
    db.commit()
    return _builder_response(request, db, form)


@router.post("/admin/formulieren/{form_id}/secties/{section_id}/verplaats",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def sectie_verplaatsen(form_id: int, section_id: int, request: Request,
                       db: Session = Depends(get_db), email: str = Depends(require_admin_ui),
                       richting: str = Form("op")):
    from app.kernel.ordering import move_sibling

    form = _form_or_404(db, form_id)
    if not any(s.id == section_id for s in form.sections):
        raise HTTPException(status_code=404, detail=_("Sectie niet gevonden"))
    # Dezelfde helper als de activiteiten (#635 E). Die normaliseert eerst naar
    # 0..n: wisselen alléén werkte niet zolang alle posities nog op hun default
    # stonden — dan viel er niets te wisselen en gebeurde er stil niets.
    move_sibling(form.sections, section_id, richting, attr="position")
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
        raise HTTPException(status_code=422, detail=_("Ongeldig veldtype: %(field_type)s") % {"field_type": field_type})
    if not label.strip():
        raise HTTPException(status_code=422, detail=_("Elk veld heeft een vraag/label nodig."))
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
        raise HTTPException(status_code=404, detail=_("Veld niet gevonden"))
    if not label.strip():
        raise HTTPException(status_code=422, detail=_("Elk veld heeft een vraag/label nodig."))
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
    from app.kernel.ordering import move_sibling

    form = _form_or_404(db, form_id)
    veld = next((f for f in form.fields if f.id == field_id), None)
    if veld is None:
        raise HTTPException(status_code=404, detail=_("Veld niet gevonden"))
    broers = [f for f in form.fields if f.section_id == veld.section_id]
    move_sibling(broers, field_id, richting, attr="position")
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
        raise HTTPException(status_code=422, detail=_("Opties kunnen enkel bij keuzevelden."))
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
        raise HTTPException(status_code=404, detail=_("Optie niet gevonden"))
    veld = optie.field
    heeft_sprong = bool(skip_to_end) or skip_to_section_id.strip().isdigit()
    if heeft_sprong and veld.field_type not in ("radio", "select"):
        raise HTTPException(status_code=422,
                            detail=_("Vertakking kan enkel bij 'één keuze' of 'keuzelijst'."))
    target = int(skip_to_section_id) if skip_to_section_id.strip().isdigit() else None
    if target is not None:
        doel = next((s for s in form.sections if s.id == target), None)
        eigen = next((s for s in form.sections if s.id == veld.section_id), None)
        if doel is None or (eigen is not None and doel.position <= eigen.position):
            raise HTTPException(status_code=422,
                                detail=_("Een vertakking moet naar een latere sectie springen."))
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
    from app.domains.forms.schemas import FormUpdate
    from app.domains.forms.service import (apply_definition, update_settings,
                                           validate_definition)

    form = _form_or_404(db, form_id)
    try:
        data = FormUpdate(**json.loads(payload))
    except (json.JSONDecodeError, ValueError) as exc:
        return _builder_response(request, db, form,
                                 error=_("Ongeldige JSON: %(exc)s") % {"exc": exc})
    try:
        validate_definition(data)
        # Alle instellingen, niet drie (#635-3): deze route schreef enkel titel,
        # omschrijving en status, waardoor een import stilzwijgend slug,
        # requires_login, max_submissions, send_confirmation,
        # confirmation_message, allow_edit en is_anonymous liet vallen. Dezelfde
        # functie als update_form gebruikt, dus dat kan niet meer uiteenlopen.
        update_settings(form, data)
        apply_definition(form, data)
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
        "form": form, "rows": rows, "csrf_token": csrf_from_request(request)})


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

    # format expliciet meegeven: export_form heeft `format=Query("ods")`, en bij een
    # directe functie-aanroep is die default een FastAPI Query-object (niet de string
    # "ods") → anders faalt de format-check met 422 "Ongeldig formaat".
    return export_form(form_id, format="ods", db=db, _admin=None)  # type: ignore[arg-type]


# ── Resultaten (statistiek) + JSON-export ──────────────────────────────────────

@router.get("/admin/formulieren/{form_id}/resultaten", response_class=HTMLResponse)
def resultaten_tab(form_id: int, request: Request, db: Session = Depends(get_db),
                   email: str = Depends(require_admin_ui)):
    """Server-side geaggregeerde resultaten per veld (#455/#454): staafjes per
    optie, rating-gemiddelde + verdeling, number-stats, tekstantwoorden."""
    from app.domains.forms.results import compute_results

    form = _form_or_404(db, form_id)
    return templates.TemplateResponse(request, "_fb_resultaten.html", {
        "form": form, "results": compute_results(db, form)})


@router.get("/admin/formulieren/{form_id}/json")
def json_export(form_id: int, request: Request, db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)) -> Response:
    """Volledige formulierdefinitie als downloadbare JSON (backup/inspectie/AI)."""
    from app.domains.forms.router import _admin_out

    form = _form_or_404(db, form_id)
    payload = json.dumps(_admin_out(db, form), ensure_ascii=False,
                         indent=2, default=str)
    slug = form.slug or f"formulier-{form.id}"
    return Response(
        content=payload, media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{slug}.json"'},
    )


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
