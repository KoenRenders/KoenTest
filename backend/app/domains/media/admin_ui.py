"""Server-rendered mediabeheer (React-exit 405-d, #405 — §21).

Sponsors en activiteitenfoto's: uploaden (multipart via htmx), metadata
bewerken (titel, link, volgorde, actief) en verwijderen. Hergebruikt de
media-routerfuncties als servicelaag.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    admin_user_by_email, csrf_from_request,
    SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf,
)
from app.ui import admin_nav, is_fragment_request, templates
from app.i18n import _

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/media")


def _lijst_ctx(request: Request, db: Session, kind: str, q: str = "",
               activity_id: Optional[int] = None) -> dict:
    from app.domains.activities.api import activity_options
    from app.domains.media.api import (VALID_KINDS, activity_ids_with_media,
                                       list_media)

    actief_kind = kind if kind in VALID_KINDS else "sponsor"
    if activity_id is None:
        # GET: het filter staat in de querystring. Bij een mutatie (POST) geeft de
        # kaart hem als verborgen veld mee, zodat het filter niet wegvalt.
        raw = request.query_params.get("activity_id")
        activity_id = int(raw) if raw and raw.isdigit() else None

    # Álle activiteiten (naam + jaar) voor de upload-dropdown (#476): je moet
    # foto's aan om het even welke activiteit kunnen koppelen, ook zonder foto's.
    #
    # `activity_options` en niet `list_activities` (#645): die laatste laadt datums,
    # onderdelen én producten eager en berekent de bezetting per onderdeel — een
    # lijstbewerking, hergebruikt om drie velden in een <select> te zetten. Dat
    # kostte dit scherm p95 578 ms tegen 9–122 ms voor de andere adminroutes.
    alle_activiteiten = [{"id": optie.id, "naam": optie.name,
                          "jaar": optie.first_date.year if optie.first_date else None}
                         for optie in activity_options(db)]
    # Filter-dropdown: enkel activiteiten die al media hebben (#459), mét jaar.
    aids = activity_ids_with_media(db)
    activiteiten = [a for a in alle_activiteiten if a["id"] in aids]

    assets = list_media(db, kind=actief_kind, activity_id=activity_id)
    # Vrij zoeken op titel (C1, #588). Media zonder titel valt weg zodra er
    # gezocht wordt — dat is de bedoeling van een zoekterm.
    term = q.strip().lower()
    if term:
        # admin_list_media levert lichte metadata-dicts (_meta), geen ORM-objecten.
        assets = [a for a in assets if term in (a.get("title") or "").lower()]

    # Chip-labels horen per request opgebouwd: _() volgt de taal van de tenant.
    kind_labels = {"sponsor": _("Sponsors"), "activity_photo": _("Activiteitenfoto's")}
    return {"assets": assets, "q": q, "gefilterd": bool(term or activity_id),
            "kind": actief_kind, "kinds": sorted(VALID_KINDS),
            "kind_options": [(k, kind_labels.get(k, k)) for k in sorted(VALID_KINDS)],
            "activity_id": activity_id, "activiteiten": activiteiten,
            "alle_activiteiten": alle_activiteiten,
            "csrf_token": csrf_from_request(request)}


def _lijst_response(request: Request, db: Session, kind: str,
                    error: str | None = None, q: str = "",
                    activity_id: Optional[int] = None):
    """Enkel de kaarten (C1, #588): kop, knop en filterbalk staan op de pagina."""
    ctx = _lijst_ctx(request, db, kind, q, activity_id)
    ctx["error"] = error
    return templates.TemplateResponse(request, "_me_lijst.html", ctx)


@router.get("/admin/media", response_class=HTMLResponse)
def admin_media(request: Request, kind: str = "sponsor", q: str = "",
                db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)):
    # htmx (de filterbalk) krijgt enkel de kaarten terug: een pagina-swap zou het
    # zoekveld tijdens het typen vervangen.
    if is_fragment_request(request):
        return _lijst_response(request, db, kind, q=q)
    return templates.TemplateResponse(request, "admin_media.html", {
        "nav_items": NAV, "error": None, **_lijst_ctx(request, db, kind, q)})


@router.get("/admin/media/nieuw", response_class=HTMLResponse)
def media_nieuw(request: Request, db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)):
    """Uploaden als volledige pagina (#627, §2.8) i.p.v. een modal.

    Hergebruikt de contextbouwer van de lijst: de dropdown met álle activiteiten en
    de huidige filterstand komen daaruit, zodat je na het uploaden terugkeert in
    dezelfde filtering.
    """
    # `kind` uit de query, zodat "+ Uploaden" vanaf de foto-filter meteen de
    # activiteit-dropdown toont (die hoort enkel bij activity_photo).
    kind = (request.query_params.get("kind") or "sponsor").strip()
    ctx = _lijst_ctx(request, db, kind=kind)
    ctx["nav_items"] = NAV
    return templates.TemplateResponse(request, "admin_media_nieuw.html", ctx)


@router.post("/admin/media", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def media_uploaden(request: Request, db: Session = Depends(get_db),
                         email: str = Depends(require_admin_ui),
                         files: List[UploadFile] = File(...),
                         kind: str = Form("sponsor"),
                         activity_id: Optional[int] = Form(None),
                         title: str = Form(""), link_url: str = Form(""),
                         q: str = Form(""), filter_activity_id: Optional[int] = Form(None)):
    from app.domains.media.api import MediaFout, upload_media

    try:
        await upload_media(db, files=files, kind=kind, activity_id=activity_id,
                           title=title.strip() or None,
                           link_url=link_url.strip() or None)
    except (LookupError, MediaFout) as exc:
        # Op het aanmaakscherm blijven mét de fout (#627): een fragment terugsturen
        # naar een pagina die geen lijst toont, laat de gebruiker in het ongewisse.
        ctx = _lijst_ctx(request, db, kind=kind, q=q, activity_id=filter_activity_id)
        ctx["nav_items"] = NAV
        ctx["error"] = str(exc)
        return templates.TemplateResponse(request, "admin_media_nieuw.html", ctx)
    # Media is met één handeling compleet, dus terug naar de lijst (#627).
    return Response(status_code=204, headers={"HX-Redirect": "/admin/media"})


@router.post("/admin/media/{asset_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def media_bijwerken(asset_id: int, request: Request,
                    db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui),
                    kind: str = Form("sponsor"), title: str = Form(""),
                    link_url: str = Form(""), sort_order: str = Form("0"),
                    is_active: str = Form(""),
                    q: str = Form(""), filter_activity_id: Optional[int] = Form(None)):
    from app.domains.media.api import MediaFout, update_media

    try:
        volgorde = int(sort_order or "0")
    except ValueError:
        return _lijst_response(request, db, kind, "Ongeldige volgorde.", q, filter_activity_id)
    try:
        update_media(db, asset_id, {
            "title": title.strip() or None, "link_url": link_url.strip() or None,
            "sort_order": volgorde, "is_active": bool(is_active),
        })
    except (LookupError, MediaFout) as exc:
        return _lijst_response(request, db, kind, str(exc), q, filter_activity_id)
    return _lijst_response(request, db, kind, q=q, activity_id=filter_activity_id)


@router.post("/admin/media/{asset_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def media_verwijderen(asset_id: int, request: Request,
                      db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui),
                      kind: str = Form("sponsor"),
                      q: str = Form(""), filter_activity_id: Optional[int] = Form(None)):
    from app.domains.media.api import delete_media

    try:
        delete_media(db, asset_id)
    except LookupError as exc:
        return _lijst_response(request, db, kind, str(exc), q, filter_activity_id)
    return _lijst_response(request, db, kind, q=q, activity_id=filter_activity_id)
