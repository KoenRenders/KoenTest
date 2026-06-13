"""Assetbibliotheek: upload (admin) en serveren (publiek) van afbeeldingen.

Afbeeldingen worden in Postgres (BYTEA) bewaard, dus ze zitten automatisch mee
in de DB-backup. Bij upload worden ze verkleind en van een thumbnail voorzien
(zie :mod:`app.services.images`).
"""
import hashlib
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.asset import MediaAsset
from app.models.activity import Activity
from app.models.user import User
from app.services.images import process_image, ImageError, ALLOWED_CONTENT_TYPES

router = APIRouter(tags=["media"])

VALID_KINDS = {"sponsor", "activity_photo"}
MAX_BATCH = 20


def _meta(a: MediaAsset) -> dict:
    """Lichte metadata-respons (zonder de blobs)."""
    return {
        "id": a.id,
        "kind": a.kind,
        "activity_id": a.activity_id,
        "title": a.title,
        "link_url": a.link_url,
        "sort_order": a.sort_order,
        "is_active": a.is_active,
        "width": a.width,
        "height": a.height,
        "byte_size": a.byte_size,
        "url": f"/api/v1/media/{a.id}",
        "thumb_url": f"/api/v1/media/{a.id}/thumb",
    }


# ---------------------------------------------------------------------------
# Publiek serveren
# ---------------------------------------------------------------------------
def _serve(blob: Optional[bytes], content_type: Optional[str], request: Request, etag_seed: str):
    if not blob:
        raise HTTPException(status_code=404, detail="Niet gevonden")
    etag = '"' + hashlib.md5(etag_seed.encode()).hexdigest() + '"'  # noqa: S324 - alleen cache-validatie
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return Response(
        content=blob,
        media_type=content_type or "application/octet-stream",
        headers={
            # Inhoud verandert nooit na upload → lang en immutable cachen.
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": etag,
        },
    )


@router.get("/media/{asset_id}")
def serve_media(asset_id: int, request: Request, db: Session = Depends(get_db)):
    a = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Niet gevonden")
    return _serve(a.data, a.content_type, request, f"full-{a.id}")


@router.get("/media/{asset_id}/thumb")
def serve_thumb(asset_id: int, request: Request, db: Session = Depends(get_db)):
    a = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Niet gevonden")
    blob = a.thumbnail or a.data
    ctype = a.thumb_content_type or a.content_type
    return _serve(blob, ctype, request, f"thumb-{a.id}")


@router.get("/sponsors")
def list_sponsors(db: Session = Depends(get_db)):
    """Actieve sponsorlogo's voor footer en homepage."""
    rows = (
        db.query(MediaAsset)
        .filter(MediaAsset.kind == "sponsor", MediaAsset.is_active == True)  # noqa: E712
        .order_by(MediaAsset.sort_order.asc(), MediaAsset.id.asc())
        .all()
    )
    return [_meta(a) for a in rows]


@router.get("/media/activity-photos/availability")
def activity_photos_availability(db: Session = Depends(get_db)):
    """Activity-id's die actieve foto's hebben — in één query.

    Laat de frontend de "Foto's"-knop tonen zonder per activiteit een aparte
    fotorequest te doen (vermijdt het N+1-patroon op de archieflijst). Blijft
    volledig binnen het media-domein; raakt het activiteiten-schema niet aan.
    """
    rows = (
        db.query(MediaAsset.activity_id)
        .filter(
            MediaAsset.kind == "activity_photo",
            MediaAsset.is_active == True,  # noqa: E712
            MediaAsset.activity_id.isnot(None),
        )
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


@router.get("/media/activity-photos/covers")
def activity_photo_covers(db: Session = Depends(get_db)):
    """Per activiteit met foto's één cover-thumbnail — in één query.

    Gebruikt door de fotopagina om albumkaartjes met een echte beeld-preview
    te tonen i.p.v. een placeholder-icoon. DISTINCT ON (activity_id) pakt per
    activiteit de eerste foto (laagste sort_order, dan id). Blijft binnen het
    media-domein; raakt het activiteiten-schema niet aan.
    """
    rows = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.kind == "activity_photo",
            MediaAsset.is_active == True,  # noqa: E712
            MediaAsset.activity_id.isnot(None),
        )
        .order_by(MediaAsset.activity_id, MediaAsset.sort_order.asc(), MediaAsset.id.asc())
        .distinct(MediaAsset.activity_id)
        .all()
    )
    return [{"activity_id": a.activity_id, "thumb_url": f"/api/v1/media/{a.id}/thumb"} for a in rows]


@router.get("/activities/{activity_id}/photos")
def list_activity_photos(activity_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.kind == "activity_photo",
            MediaAsset.activity_id == activity_id,
            MediaAsset.is_active == True,  # noqa: E712
        )
        .order_by(MediaAsset.sort_order.asc(), MediaAsset.id.asc())
        .all()
    )
    return [_meta(a) for a in rows]


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
@router.get("/admin/media")
def admin_list_media(
    kind: Optional[str] = Query(None),
    activity_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    q = db.query(MediaAsset)
    if kind:
        q = q.filter(MediaAsset.kind == kind)
    if activity_id is not None:
        q = q.filter(MediaAsset.activity_id == activity_id)
    rows = q.order_by(MediaAsset.sort_order.asc(), MediaAsset.id.desc()).all()
    return [_meta(a) for a in rows]


@router.post("/admin/media")
async def upload_media(
    files: List[UploadFile] = File(...),
    kind: str = Form(...),
    activity_id: Optional[int] = Form(None),
    title: Optional[str] = Form(None),
    link_url: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=400, detail="Ongeldige 'kind'")
    if kind == "activity_photo":
        if activity_id is None:
            raise HTTPException(status_code=400, detail="activity_id vereist voor activiteitenfoto's")
        if not db.query(Activity).filter(Activity.id == activity_id).first():
            raise HTTPException(status_code=404, detail="Activiteit niet gevonden")
    else:
        activity_id = None  # sponsors hangen niet aan een activiteit

    if not files:
        raise HTTPException(status_code=400, detail="Geen bestanden")
    if len(files) > MAX_BATCH:
        raise HTTPException(status_code=400, detail=f"Maximaal {MAX_BATCH} bestanden per keer")

    # Volgende sort_order na de bestaande items in deze groep.
    base_q = db.query(MediaAsset).filter(MediaAsset.kind == kind)
    if activity_id is not None:
        base_q = base_q.filter(MediaAsset.activity_id == activity_id)
    next_order = base_q.count()

    created = []
    for idx, up in enumerate(files):
        if up.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail=f"Niet-ondersteund bestandstype: {up.filename}")
        raw = await up.read()
        try:
            processed = process_image(raw)
        except ImageError as exc:
            raise HTTPException(status_code=400, detail=f"{up.filename}: {exc}")

        asset = MediaAsset(
            kind=kind,
            activity_id=activity_id,
            title=title or up.filename,
            link_url=link_url,
            sort_order=next_order + idx,
            is_active=True,
            **processed,
        )
        db.add(asset)
        created.append(asset)

    db.commit()
    for a in created:
        db.refresh(a)
    return [_meta(a) for a in created]


@router.patch("/admin/media/{asset_id}")
def update_media(
    asset_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    a = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Niet gevonden")
    for field in ("title", "link_url", "sort_order", "is_active"):
        if field in payload:
            setattr(a, field, payload[field])
    db.commit()
    db.refresh(a)
    return _meta(a)


@router.delete("/admin/media/{asset_id}")
def delete_media(
    asset_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    a = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Niet gevonden")
    db.delete(a)
    db.commit()
    return {"detail": "Verwijderd"}
