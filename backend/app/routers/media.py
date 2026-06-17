"""Assetbibliotheek: upload (admin) en serveren (publiek) van afbeeldingen.

Afbeeldingen worden in Postgres (BYTEA) bewaard, dus ze zitten automatisch mee
in de DB-backup. Bij upload worden ze verkleind en van een thumbnail voorzien
(zie :mod:`app.services.images`).
"""
import hashlib
import re
from typing import List, Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, Query, Request,
)
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.asset import MediaAsset
from app.models.activity import Activity
from app.models.activity_sub_registration import ActivitySubRegistration
from app.models.user import User
from app.services.media_extraction import EXTRACTABLE_KINDS, update_media_extracted_text
from app.services.images import (
    process_image, ImageError, ALLOWED_CONTENT_TYPES, MAX_UPLOAD_BYTES,
)

router = APIRouter(tags=["media"])

VALID_KINDS = {"sponsor", "activity_photo"}
MAX_BATCH = 20

# Poster/reglement mag een afbeelding óf een PDF zijn (#223).
DOC_CONTENT_TYPES = ALLOWED_CONTENT_TYPES | {"application/pdf"}
_EXT_BY_TYPE = {
    "application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg",
    "image/webp": ".webp", "image/gif": ".gif",
}


def _process_document(raw: bytes, content_type: str) -> dict:
    """Verwerk een poster/reglement-upload: PDF wordt ongewijzigd bewaard (geen
    thumbnail), een afbeelding gaat door de gewone verkleining + thumbnail."""
    if content_type == "application/pdf":
        if not raw:
            raise ImageError("Leeg bestand")
        if len(raw) > MAX_UPLOAD_BYTES:
            raise ImageError("Bestand te groot")
        return {
            "data": raw, "content_type": "application/pdf",
            "thumbnail": None, "thumb_content_type": None,
            "width": None, "height": None, "byte_size": len(raw),
        }
    return process_image(raw)


async def _replace_single_asset(db, file: UploadFile, *, kind: str,
                                activity_id=None, component_id=None,
                                title_base: Optional[str] = None) -> MediaAsset:
    """Bewaar één poster/reglement-bestand en vervang het vorige (hard delete —
    media kent geen soft delete). ``title_base`` geeft een betekenisvolle naam
    (zonder extensie); de extensie volgt uit het type. Geeft het nieuwe asset terug."""
    if file.content_type not in DOC_CONTENT_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"Niet-ondersteund bestandstype: {file.filename}")
    raw = await file.read()
    try:
        processed = _process_document(raw, file.content_type)
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=f"{file.filename}: {exc}")

    q = db.query(MediaAsset).filter(MediaAsset.kind == kind)
    q = q.filter(MediaAsset.activity_id == activity_id) if activity_id is not None \
        else q.filter(MediaAsset.component_id == component_id)
    for old in q.all():
        db.delete(old)  # hard delete, geen ballast

    if title_base:
        title = f"{title_base}{_EXT_BY_TYPE.get(processed['content_type'], '')}"
    else:
        title = file.filename
    asset = MediaAsset(
        kind=kind, activity_id=activity_id, component_id=component_id,
        title=title, sort_order=0, is_active=True, **processed,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _meta(a: MediaAsset) -> dict:
    """Lichte metadata-respons (zonder de blobs)."""
    return {
        "id": a.id,
        "kind": a.kind,
        "activity_id": a.activity_id,
        "component_id": a.component_id,
        "title": a.title,
        "link_url": a.link_url,
        "sort_order": a.sort_order,
        "is_active": a.is_active,
        "width": a.width,
        "height": a.height,
        "byte_size": a.byte_size,
        "content_type": a.content_type,
        "is_pdf": a.content_type == "application/pdf",
        "url": f"/api/v1/media/{a.id}",
        "thumb_url": f"/api/v1/media/{a.id}/thumb",
    }


# ---------------------------------------------------------------------------
# Publiek serveren
# ---------------------------------------------------------------------------
def _safe_filename(name: Optional[str], fallback: str) -> str:
    """Header-veilige bestandsnaam (ASCII-subset) voor Content-Disposition."""
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", (name or "").strip())
    return cleaned or fallback


def _serve(blob: Optional[bytes], content_type: Optional[str], request: Request,
           etag_seed: str, *, filename: Optional[str] = None):
    if not blob:
        raise HTTPException(status_code=404, detail="Niet gevonden")
    etag = '"' + hashlib.md5(etag_seed.encode()).hexdigest() + '"'  # noqa: S324 - alleen cache-validatie
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    headers = {
        # Inhoud verandert nooit na upload → lang en immutable cachen.
        "Cache-Control": "public, max-age=31536000, immutable",
        "ETag": etag,
    }
    if filename:
        # Inline tonen (PDF in de native viewer, afbeelding gewoon) met een nette
        # naam bij delen/bewaren (#223).
        headers["Content-Disposition"] = f'inline; filename="{filename}"'
    return Response(
        content=blob,
        media_type=content_type or "application/octet-stream",
        headers=headers,
    )


@router.get("/media/{asset_id}")
def serve_media(asset_id: int, request: Request, db: Session = Depends(get_db)):
    a = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Niet gevonden")
    return _serve(a.data, a.content_type, request, f"full-{a.id}",
                  filename=_safe_filename(a.title, f"bestand-{a.id}"))


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


# ---------------------------------------------------------------------------
# Poster (activiteit) en info/reglement (onderdeel): één bestand, vervangbaar (#223)
# ---------------------------------------------------------------------------

@router.post("/admin/activities/{activity_id}/poster")
async def upload_activity_poster(
    activity_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activiteit niet gevonden")
    asset = await _replace_single_asset(
        db, file, kind="activity_poster", activity_id=activity_id,
        title_base=f"{activity.name} - poster",
    )
    # Tekstextractie op de achtergrond (#206): de upload slaagt direct, de
    # (eventueel betalende) OCR loopt erachteraan en raakt de respons niet. De
    # tekst komt op het media-record (extracted_text), niet op de activiteit.
    background_tasks.add_task(update_media_extracted_text, asset.id)
    return _meta(asset)


@router.delete("/admin/activities/{activity_id}/poster", status_code=204)
def delete_activity_poster(
    activity_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    # Hard delete van het asset-record neemt extracted_text vanzelf mee (#206).
    for a in db.query(MediaAsset).filter(
        MediaAsset.kind == "activity_poster", MediaAsset.activity_id == activity_id
    ).all():
        db.delete(a)
    db.commit()


@router.post("/admin/components/{component_id}/info")
async def upload_component_info(
    component_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    component = db.query(ActivitySubRegistration).filter(
        ActivitySubRegistration.id == component_id
    ).first()
    if not component:
        raise HTTPException(status_code=404, detail="Onderdeel niet gevonden")
    activity_name = component.activity.name if component.activity else "activiteit"
    asset = await _replace_single_asset(
        db, file, kind="component_info", component_id=component_id,
        title_base=f"{activity_name} - {component.name} - info",
    )
    # Ook reglement/info-PDF's leveren context voor de chatbot (#206).
    background_tasks.add_task(update_media_extracted_text, asset.id)
    return _meta(asset)


@router.delete("/admin/components/{component_id}/info", status_code=204)
def delete_component_info(
    component_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    for a in db.query(MediaAsset).filter(
        MediaAsset.kind == "component_info", MediaAsset.component_id == component_id
    ).all():
        db.delete(a)
    db.commit()


@router.post("/admin/media/{asset_id}/extract", status_code=202)
def reextract_media_text(
    asset_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """De 'Opnieuw lezen'-knop (#235): her-extraheer de tekst van dit document.

    Draait op de achtergrond (force=True) en raakt enkel ``extracted_text`` aan —
    handmatige override/aanvulling in chatbot_info blijven staan."""
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not asset or asset.kind not in EXTRACTABLE_KINDS:
        raise HTTPException(status_code=404, detail="Document niet gevonden")
    background_tasks.add_task(update_media_extracted_text, asset_id, None, True)
    return {"status": "bezig", "asset_id": asset_id}


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
