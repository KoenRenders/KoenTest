"""The Design Studio screens (CR-10, #1007): the list, the new-design screen,
the editor.

Board-only and desktop-first: a poster is made at a desk. Everything sits
behind `require_admin_ui`. The paths are Dutch because a board member reads
them in the address bar; the module, routes and parameters are English.

The editor is one screen: the form on the left, the preview on the right. The
preview is a PNG rendered on request (`/voorbeeld.png`), refreshed after every
save through a fragment; the checks come with it. "Definitief maken" renders
every layout with Inkscape as the authority and writes a version — or shows
why not. "Publiceren" copies the A3 PDF onto the activity after a
confirmation.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf
from app.domains.designstudio.api import (
    ENABLED_DUOS,
    ICONS,
    LAYOUT_LABELS,
    LAYOUTS,
    MAX_HIGHLIGHTS,
    MAX_VERSIONS,
    PRESET_LABELS,
    PRESETS,
    STATUS_LABELS,
    STATUS_TONES,
    STYLE_LABELS,
    DesignError,
    ImagingError,
    RenderError,
    add_design_image,
    budget,
    check_design,
    create_design,
    delete_design,
    edited_svg_for,
    facts_for,
    fingerprint,
    get_design,
    image_options,
    is_stale,
    list_designs,
    make_version,
    pick_generation,
    preview_png,
    publish,
    remove_edited_svg,
    request_images,
    save_design,
    sponsor_options,
    sponsor_usage,
    upload_edited_svg,
    warnings_for,
)
from app.domains.designstudio.viewmodels import (
    DesignEditorView,
    DesignListView,
    DesignNewView,
    DesignRow,
    GenerationRow,
    HighlightRow,
    ImageOption,
    VersionRow,
)
from app.i18n import _
from app.ui import admin_nav, is_fragment_request, templates

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)

NAV = "/admin/ontwerpen"

DUO_LABELS = {
    "dark_green-golden_yellow": "Donkergroen · Geel",
    "ocean_blue-golden_yellow": "Blauw · Geel",
    "golden_yellow-indigo": "Geel · Paars",
}
GENERATION_LABELS = {"requested": "Bezig…", "fetched": "Klaar", "picked": "Gekozen", "discarded": "Niet gekozen",
                     "refused": "Geweigerd (moderatie)", "failed": "Mislukt"}


def _short(name: str, limit: int = 22) -> str:
    """A file name cut to what a select shows: the extension goes, the middle
    gives way ("WhatsApp Image 2026-05-01 at 15.14.39.jpeg" → "WhatsApp Im…15.14.39")."""
    stem = name.rsplit(".", 1)[0] if "." in name else name
    if len(stem) <= limit:
        return stem or _("(zonder naam)")
    keep = (limit - 1) // 2
    return f"{stem[:keep]}…{stem[-keep:]}"


def _csrf(request: Request) -> str:
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


def _design_or_404(db: Session, design_id: int):
    design = get_design(db, design_id)
    if design is None:
        raise HTTPException(status_code=404, detail=_("Ontwerp niet gevonden."))
    return design


def _activity_options(db: Session) -> list[tuple[int, str]]:
    from app.domains.activities.api import activity_options

    return [(o.id, f"{o.name} ({o.first_date.isoformat()})" if o.first_date else o.name)
            for o in activity_options(db)]


def _duo_options() -> list[tuple[str, str]]:
    return [(code, DUO_LABELS.get(code, code)) for code in ENABLED_DUOS]


def _preset_options() -> list[tuple[str, str]]:
    return [(code, PRESET_LABELS[code]) for code in PRESETS]


def _redirect(request: Request, target: str):
    # Boosted forms travel as htmx requests: HX-Redirect makes the browser
    # navigate for real, so a refresh stays on the editor (same as meetings).
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=303)


# ── The list ─────────────────────────────────────────────────────────────────

def _list_view(request: Request, db: Session, q: str = "", error: Optional[str] = None) -> DesignListView:
    from app.domains.activities.api import get_activity

    rows = []
    needle = (q or "").strip().lower()
    for design in list_designs(db):
        activity = get_activity(db, design.activity_id)
        name = activity.name if activity is not None else _("(activiteit verwijderd)")
        if needle and needle not in name.lower():
            continue
        published = next((v for v in design.versions if v.id == design.published_version_id), None)
        rows.append(DesignRow(
            id=design.id, activity_id=design.activity_id, activity_name=name,
            preset_label=PRESET_LABELS.get(design.preset, design.preset),
            status_label=_(STATUS_LABELS.get(design.status, design.status)),
            status_tone=STATUS_TONES.get(design.status, "gray"),
            version_count=len(design.versions), published=published is not None,
            stale=bool(published is not None and activity is not None and is_stale(db, published)),
            updated=design.updated_at.strftime("%d-%m-%Y %H:%M") if design.updated_at else "",
        ))
    return DesignListView(rows=rows, q=q, csrf_token=_csrf(request), error=error, nav_items=admin_nav(NAV))


@router.get("/admin/ontwerpen", response_class=HTMLResponse)
def design_list(request: Request, db: Session = Depends(get_db),
                _email: str = Depends(require_admin_ui), q: str = ""):
    view = _list_view(request, db, q=q)
    template = "_ds_lijst.html" if is_fragment_request(request) else "admin_ontwerpen.html"
    return templates.TemplateResponse(request, template, view.as_context())


def _new_view(request: Request, db: Session, *, activity_id: str = "", duo_code: str = "",
              preset: str = "beeld", error: Optional[str] = None) -> DesignNewView:
    return DesignNewView(activity_options=_activity_options(db), activity_id=activity_id,
                         duo_options=_duo_options(), duo_code=duo_code or ENABLED_DUOS[0],
                         preset_options=_preset_options(), preset=preset,
                         csrf_token=_csrf(request), error=error, nav_items=admin_nav(NAV))


@router.get("/admin/ontwerpen/nieuw", response_class=HTMLResponse)
def design_new(request: Request, db: Session = Depends(get_db), _email: str = Depends(require_admin_ui),
               activity_id: str = ""):
    return templates.TemplateResponse(request, "admin_ontwerp_nieuw.html",
                                      _new_view(request, db, activity_id=activity_id).as_context())


@router.post("/admin/ontwerpen", response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def design_create(request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui),
                  activity_id: str = Form(""), duo_code: str = Form(""), preset: str = Form("beeld")):
    try:
        design = create_design(db, activity_id=int(activity_id or 0), duo_code=duo_code, preset=preset,
                               created_by=email)
    except (DesignError, ValueError) as exc:
        return templates.TemplateResponse(
            request, "admin_ontwerp_nieuw.html",
            _new_view(request, db, activity_id=activity_id, duo_code=duo_code, preset=preset,
                      error=str(exc) or _("Kies een activiteit.")).as_context())
    return _redirect(request, f"/admin/ontwerpen/{design.id}")


# ── The editor ───────────────────────────────────────────────────────────────

def _facts_rows(facts: dict) -> list[tuple[str, str]]:
    rows = [(_("Titel"), facts["title"])]
    if facts["dates"]:
        rows.append((_("Data"), ", ".join(
            f"{d['date']} {d['time']}".strip() for d in facts["dates"])))
    rows.append((_("Plaats"), facts["location"] or "—"))
    rows.append((_("Inschrijven tot"), facts["deadline"] or "—"))
    rows.append((_("Contact"), "; ".join(" · ".join(p for p in (c["name"], c["mobile"], c["email"]) if p)
                                          for c in facts["organisers"])
                 or _("niemand aangevinkt → gegevens van de vereniging")))
    rows.append((_("Omschrijving"), facts["description"] or _("— (leeg; typ hieronder een toelichting)")))
    return rows


def _editor_view(request: Request, db: Session, design, *, layout: str = "print_a",
                 error: Optional[str] = None, notice: Optional[str] = None,
                 violations: Optional[list[str]] = None, ai_prompt: str = "", ai_style: str = "lijn") -> DesignEditorView:
    if layout not in LAYOUTS:
        layout = "print_a"
    facts = facts_for(db, design)
    render_error = None
    if violations is None:
        try:
            violations = check_design(db, design).get(layout, [])
        except RenderError as exc:
            violations, render_error = [], str(exc)
    # Short labels: a select shows ~25 characters; a phone's file name does
    # not fit and the source in Dutch says more than "activity_photo".
    source_labels = {"activity_photo": _("foto activiteit"), "design_image": _("studio"), "generated": _("AI")}
    options = [ImageOption(id=m["id"], thumb_url=m["thumb_url"],
                           label=f"{_short(m.get('title') or '')} · {source_labels.get(m['source'], m['source'])} #{m['id']}",
                           source=m["source"]) for m in image_options(db, design)]
    year = date.today().year
    logos = [ImageOption(id=m["id"], thumb_url=m["thumb_url"],
                         label=f"{m.get('title') or '#' + str(m['id'])} ({sponsor_usage(db, m['id'], year)}× in {year})",
                         source="sponsor")
             for m in sponsor_options(db)]
    versions = []
    for v in sorted(design.versions, key=lambda v: -v.number):
        files = [{"label": f"{LAYOUT_LABELS.get(r.layout_code, r.layout_code)} · {r.variant.upper()} {r.size_code}".strip(),
                  "url": f"/api/v1/media/{r.media_asset_id}"} for r in v.renditions]
        versions.append(VersionRow(id=v.id, number=v.number, created=v.created_at.strftime("%d-%m-%Y %H:%M"),
                                   published=(v.id == design.published_version_id), stale=is_stale(db, v), files=files))
    generations = [GenerationRow(id=g.id, status=g.status, status_label=_(GENERATION_LABELS.get(g.status, g.status)),
                                 thumb_url=f"/api/v1/media/{g.media_asset_id}/thumb" if g.media_asset_id else "",
                                 media_asset_id=g.media_asset_id, failure_reason=g.failure_reason or "",
                                 scene=g.scene or "", style=g.style or "lijn")
                   for g in sorted(design.generations, key=lambda g: -g.id)[:12]]
    highlights = [HighlightRow(icon=h.icon_code, text=h.text, emphasis=h.emphasis) for h in design.highlights]
    while len(highlights) < MAX_HIGHLIGHTS:
        highlights.append(HighlightRow(icon="smile", text="", emphasis=False))
    ai = budget(db)
    return DesignEditorView(
        design_id=design.id, activity_id=design.activity_id, activity_name=facts["title"],
        status=design.status, status_label=_(STATUS_LABELS.get(design.status, design.status)),
        status_tone=STATUS_TONES.get(design.status, "gray"),
        preset=design.preset, preset_options=_preset_options(), duo_code=design.duo_code, duo_options=_duo_options(),
        tagline=design.tagline or "", subtitle=design.subtitle or "",
        explanation_md=design.explanation_md or facts["description"], explanation_is_own=bool(design.explanation_md),
        highlights=highlights, icon_options=[(code, label) for code, (label, _p) in ICONS.items()],
        main_image_id=design.main_image_id, inset_image_id=design.inset_image_id, third_image_id=design.third_image_id,
        main_focus_x=f"{float(design.main_focus_x):.2f}", main_focus_y=f"{float(design.main_focus_y):.2f}",
        image_options=options, logo_options=logos, logo_ids=[lg.media_asset_id for lg in design.logos],
        facts=_facts_rows(facts), facts_href=f"/admin/activiteiten/{design.activity_id}",
        preview_url=f"/admin/ontwerpen/{design.id}/voorbeeld.png?layout={layout}&v={fingerprint(facts)[:8]}",
        layout=layout, layout_options=[(code, _(label)) for code, label in LAYOUT_LABELS.items()],
        violations=violations or [], warnings=warnings_for(design, facts), render_error=render_error,
        edited_layouts=[lc for lc in LAYOUTS if edited_svg_for(db, design, lc) is not None],
        font_links=[("Radio Canada Big", "/static/fonts/RadioCanadaBig-VariableFont_wght.ttf"),
                    ("Caveat", "/static/fonts/Caveat-VariableFont_wght.ttf")],
        versions=versions, published_version_id=design.published_version_id, max_versions=MAX_VERSIONS,
        ai_enabled=ai.enabled, ai_budget_line=ai.line(), generations=generations, ai_prompt=ai_prompt,
        ai_style=ai_style, style_options=[(code, _(label)) for code, label in STYLE_LABELS.items()],
        csrf_token=_csrf(request), error=error, notice=notice, nav_items=admin_nav(NAV))


@router.get("/admin/ontwerpen/{design_id}", response_class=HTMLResponse)
def design_editor(request: Request, design_id: int, db: Session = Depends(get_db),
                  _email: str = Depends(require_admin_ui), layout: str = "print_a", notice: str = ""):
    design = _design_or_404(db, design_id)
    view = _editor_view(request, db, design, layout=layout, notice=notice or None)
    template = "_ds_voorbeeld.html" if is_fragment_request(request) else "admin_ontwerp.html"
    return templates.TemplateResponse(request, template, view.as_context())


@router.get("/admin/ontwerpen/{design_id}/voorbeeld.png")
def design_preview(design_id: int, db: Session = Depends(get_db), _email: str = Depends(require_admin_ui),
                   layout: str = "print_a"):
    design = _design_or_404(db, design_id)
    if layout not in LAYOUTS:
        raise HTTPException(status_code=404)
    try:
        png, _problems = preview_png(db, design, layout)
    except (DesignError, RenderError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/admin/ontwerpen/{design_id}/svg/{layout}")
def design_svg_download(design_id: int, layout: str, db: Session = Depends(get_db),
                        _email: str = Depends(require_admin_ui)):
    """The editable SVG of the current draft, to rework in Inkscape (§3.6a)."""
    from app.domains.designstudio.service import merged_for

    design = _design_or_404(db, design_id)
    if layout not in LAYOUTS:
        raise HTTPException(status_code=404)
    merged = merged_for(db, design, layout, facts=facts_for(db, design))
    return Response(content=merged.svg.encode("utf-8"), media_type="image/svg+xml",
                    headers={"Content-Disposition": f'attachment; filename="ontwerp-{design.id}-{layout}.svg"'})


async def _form_dict(request: Request) -> dict:
    form = await request.form()
    return {k: v for k, v in form.multi_items() if not hasattr(v, "filename")}


@router.post("/admin/ontwerpen/{design_id}", response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
async def design_save(request: Request, design_id: int, db: Session = Depends(get_db),
                      _email: str = Depends(require_admin_ui)):
    design = _design_or_404(db, design_id)
    form = await request.form()
    values = {k: str(v) for k, v in form.items() if not hasattr(v, "filename")}
    highlights: list[tuple[str, str, bool]] = []
    for i in range(MAX_HIGHLIGHTS):
        highlights.append((str(form.get(f"hl_icon_{i}", "smile")), str(form.get(f"hl_text_{i}", "")),
                           bool(form.get(f"hl_emphasis_{i}"))))
    logo_ids = [int(str(v)) for v in form.getlist("logo_ids") if str(v).isdigit()]
    layout = values.get("layout", "print_a")
    try:
        save_design(db, design, values, highlights=highlights, logo_ids=logo_ids)
    except DesignError as exc:
        return templates.TemplateResponse(request, "admin_ontwerp.html",
                                          _editor_view(request, db, design, layout=layout, error=str(exc)).as_context())
    return _redirect(request, f"/admin/ontwerpen/{design.id}?layout={layout}&notice=bewaard")


@router.post("/admin/ontwerpen/{design_id}/afbeelding", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def design_image_upload(request: Request, design_id: int, db: Session = Depends(get_db),
                              _email: str = Depends(require_admin_ui), file: UploadFile = File(...),
                              slot: str = Form("main_image_id"), layout: str = Form("print_a")):
    design = _design_or_404(db, design_id)
    try:
        await add_design_image(db, design, file, slot=slot)
    except DesignError as exc:
        return templates.TemplateResponse(request, "admin_ontwerp.html",
                                          _editor_view(request, db, design, layout=layout, error=str(exc)).as_context())
    return _redirect(request, f"/admin/ontwerpen/{design.id}?layout={layout}&notice=afbeelding")


@router.post("/admin/ontwerpen/{design_id}/genereer", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def design_generate(request: Request, design_id: int, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui), scene: str = Form(""), layout: str = Form("print_a"),
                    reference_id: str = Form(""), style: str = Form("lijn"), change: str = Form("")):
    """Four variants — from scratch, or ("wat wil je anders?") on top of a
    variant the unit liked: then `reference_id` is that variant's picture and
    `change` the instruction."""
    design = _design_or_404(db, design_id)
    try:
        request_images(db, design, scene, requested_by=email, style=style, change=change,
                       reference_asset_id=int(reference_id) if reference_id.isdigit() else None)
    except (DesignError, ImagingError) as exc:
        return templates.TemplateResponse(
            request, "admin_ontwerp.html",
            _editor_view(request, db, design, layout=layout, error=str(exc), ai_prompt=scene,
                         ai_style=style).as_context())
    return _redirect(request, f"/admin/ontwerpen/{design.id}?layout={layout}&notice=gevraagd")


@router.post("/admin/ontwerpen/{design_id}/kies/{generation_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def design_pick(request: Request, design_id: int, generation_id: int, db: Session = Depends(get_db),
                _email: str = Depends(require_admin_ui), slot: str = Form("main_image_id"),
                layout: str = Form("print_a")):
    design = _design_or_404(db, design_id)
    try:
        pick_generation(db, design, generation_id, slot=slot)
    except DesignError as exc:
        return templates.TemplateResponse(request, "admin_ontwerp.html",
                                          _editor_view(request, db, design, layout=layout, error=str(exc)).as_context())
    return _redirect(request, f"/admin/ontwerpen/{design.id}?layout={layout}&notice=gekozen")


@router.post("/admin/ontwerpen/{design_id}/definitief", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def design_finalise(request: Request, design_id: int, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui), layout: str = Form("print_a")):
    design = _design_or_404(db, design_id)
    try:
        version = make_version(db, design, created_by=email)
    except DesignError as exc:
        return templates.TemplateResponse(
            request, "admin_ontwerp.html",
            _editor_view(request, db, design, layout=layout, error=_("Nog niet definitief:"),
                         violations=exc.messages).as_context())
    except RenderError as exc:
        return templates.TemplateResponse(request, "admin_ontwerp.html",
                                          _editor_view(request, db, design, layout=layout, error=str(exc)).as_context())
    return _redirect(request, f"/admin/ontwerpen/{design.id}?layout={layout}&notice=versie{version.number}")


@router.post("/admin/ontwerpen/{design_id}/publiceer", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def design_publish(request: Request, design_id: int, background_tasks: BackgroundTasks,
                         db: Session = Depends(get_db), _email: str = Depends(require_admin_ui),
                         version_id: int = Form(...), layout: str = Form("print_a")):
    design = _design_or_404(db, design_id)
    version = next((v for v in design.versions if v.id == version_id), None)
    if version is None:
        raise HTTPException(status_code=404, detail=_("Versie niet gevonden."))
    try:
        await publish(db, design, version, background_tasks)
    except DesignError as exc:
        return templates.TemplateResponse(request, "admin_ontwerp.html",
                                          _editor_view(request, db, design, layout=layout, error=str(exc)).as_context())
    return _redirect(request, f"/admin/ontwerpen/{design.id}?layout={layout}&notice=gepubliceerd")


@router.post("/admin/ontwerpen/{design_id}/svg", response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
async def design_svg_upload(request: Request, design_id: int, db: Session = Depends(get_db),
                            _email: str = Depends(require_admin_ui), file: UploadFile = File(...),
                            layout: str = Form("print_a")):
    design = _design_or_404(db, design_id)
    raw = await file.read()
    try:
        warnings = upload_edited_svg(db, design, layout, raw)
    except DesignError as exc:
        return templates.TemplateResponse(request, "admin_ontwerp.html",
                                          _editor_view(request, db, design, layout=layout, error=str(exc)).as_context())
    if warnings:
        return templates.TemplateResponse(
            request, "admin_ontwerp.html",
            _editor_view(request, db, design, layout=layout, notice=_("SVG bewaard — met opmerkingen van de huisstijl:"),
                         violations=warnings).as_context())
    return _redirect(request, f"/admin/ontwerpen/{design.id}?layout={layout}&notice=svg")


@router.post("/admin/ontwerpen/{design_id}/svg/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def design_svg_remove(request: Request, design_id: int, db: Session = Depends(get_db),
                      _email: str = Depends(require_admin_ui), layout: str = Form("print_a")):
    design = _design_or_404(db, design_id)
    remove_edited_svg(db, design, layout)
    return _redirect(request, f"/admin/ontwerpen/{design.id}?layout={layout}&notice=svgweg")


@router.post("/admin/ontwerpen/{design_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def design_delete(request: Request, design_id: int, db: Session = Depends(get_db),
                  _email: str = Depends(require_admin_ui)):
    design = _design_or_404(db, design_id)
    delete_design(db, design)
    return _redirect(request, "/admin/ontwerpen")
