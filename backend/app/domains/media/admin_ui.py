"""Server-rendered mediabeheer (React-exit 405-d, #405 — §21).

Sponsors en activiteitenfoto's: uploaden (multipart via htmx), metadata
bewerken (titel, link, volgorde, actief) en verwijderen. Hergebruikt de
media-routerfuncties als servicelaag.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    admin_user_by_email, csrf_from_request,
    SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf,
)
from app.ui import admin_nav, templates

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/media")


def _lijst_ctx(request: Request, db: Session, kind: str) -> dict:
    from app.domains.media.router import VALID_KINDS, admin_list_media
    from app.domains.media.api import MediaAsset
    from app.domains.activities.api import Activity

    actief_kind = kind if kind in VALID_KINDS else "sponsor"
    raw = request.query_params.get("activity_id")
    activity_id = int(raw) if raw and raw.isdigit() else None

    # Activiteiten die media hebben — voor de filter-dropdown (#459).
    aids = [a for (a,) in db.query(MediaAsset.activity_id)
            .filter(MediaAsset.activity_id.isnot(None)).distinct()]
    activiteiten = (db.query(Activity).execution_options(include_deleted=True)
                    .filter(Activity.id.in_(aids)).order_by(Activity.name).all()
                    if aids else [])

    return {"assets": admin_list_media(kind=actief_kind, activity_id=activity_id,
                                       db=db, _admin=None),  # type: ignore[arg-type]
            "kind": actief_kind, "kinds": sorted(VALID_KINDS),
            "activity_id": activity_id, "activiteiten": activiteiten,
            "csrf_token": csrf_from_request(request)}


def _lijst_response(request: Request, db: Session, kind: str,
                    error: str | None = None):
    ctx = _lijst_ctx(request, db, kind)
    ctx["error"] = error
    return templates.TemplateResponse(request, "_me_lijst.html", ctx)


@router.get("/admin/media", response_class=HTMLResponse)
def admin_media(request: Request, kind: str = "sponsor",
                db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "admin_media.html", {
        "nav_items": NAV, "error": None, **_lijst_ctx(request, db, kind)})


@router.get("/admin/media/lijst", response_class=HTMLResponse)
def media_lijst(request: Request, kind: str = "sponsor",
                db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)):
    return _lijst_response(request, db, kind)


@router.post("/admin/media", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def media_uploaden(request: Request, db: Session = Depends(get_db),
                         email: str = Depends(require_admin_ui),
                         files: List[UploadFile] = File(...),
                         kind: str = Form("sponsor"),
                         activity_id: Optional[int] = Form(None),
                         title: str = Form(""), link_url: str = Form("")):
    from app.domains.media.router import upload_media

    try:
        await upload_media(files=files, kind=kind, activity_id=activity_id,
                           title=title.strip() or None,
                           link_url=link_url.strip() or None,
                           db=db, _admin=None)  # type: ignore[arg-type]
    except HTTPException as exc:
        return _lijst_response(request, db, kind, str(exc.detail))
    return _lijst_response(request, db, kind)


@router.post("/admin/media/{asset_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def media_bijwerken(asset_id: int, request: Request,
                    db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui),
                    kind: str = Form("sponsor"), title: str = Form(""),
                    link_url: str = Form(""), sort_order: str = Form("0"),
                    is_active: str = Form("")):
    from app.domains.media.router import update_media

    try:
        volgorde = int(sort_order or "0")
    except ValueError:
        return _lijst_response(request, db, kind, "Ongeldige volgorde.")
    try:
        update_media(asset_id, {
            "title": title.strip() or None, "link_url": link_url.strip() or None,
            "sort_order": volgorde, "is_active": bool(is_active),
        }, db=db, _admin=None)  # type: ignore[arg-type]
    except HTTPException as exc:
        return _lijst_response(request, db, kind, str(exc.detail))
    return _lijst_response(request, db, kind)


@router.post("/admin/media/{asset_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def media_verwijderen(asset_id: int, request: Request,
                      db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui),
                      kind: str = Form("sponsor")):
    from app.domains.media.router import delete_media

    try:
        delete_media(asset_id, db=db, _admin=None)  # type: ignore[arg-type]
    except HTTPException as exc:
        return _lijst_response(request, db, kind, str(exc.detail))
    return _lijst_response(request, db, kind)
