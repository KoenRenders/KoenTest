"""Mediabestanden: lezen, uploaden, bijwerken, verwijderen (#635 I).

Deze functies stonden als routerfuncties in `router.py` en werden door beide
UI-modules geïmporteerd — de JSON-router als servicelaag. Ze bevatten wel degelijk
domeinregels: welke soorten er bestaan, dat een activiteitenfoto een bestaande
activiteit nodig heeft, dat sponsors juist géén activiteit hebben, hoeveel
bestanden er in één keer mogen, en waar de volgende `sort_order` vandaan komt.

Fouten komen naar buiten als `MediaFout` (invoer) of `LookupError` (niet
gevonden); de route vertaalt die naar een statuscode.
"""
from typing import Optional, Sequence

from app.domains.media.images import ALLOWED_CONTENT_TYPES, ImageError, process_image
from app.domains.media.models import MediaAsset

VALID_KINDS = {"sponsor", "activity_photo"}
MAX_BATCH = 20


class MediaFout(ValueError):
    """Een invoerfout die het scherm toont. Geen HTTPException: de service kent
    geen HTTP."""


def meta(asset: MediaAsset) -> dict:
    """Lichte metadata-respons (zonder de blobs)."""
    return {
        "id": asset.id,
        "kind": asset.kind,
        "activity_id": asset.activity_id,
        "component_id": asset.component_id,
        "title": asset.title,
        "link_url": asset.link_url,
        "sort_order": asset.sort_order,
        "is_active": asset.is_active,
        "width": asset.width,
        "height": asset.height,
    }


def activity_photo_covers(db) -> list[dict]:
    """Per activiteit met foto's één cover-thumbnail — in één query.

    Gebruikt door de fotopagina om albumkaartjes met een echte beeld-preview te
    tonen i.p.v. een placeholder-icoon. DISTINCT ON (activity_id) pakt per
    activiteit de eerste foto (laagste sort_order, dan id).
    """
    rijen = (db.query(MediaAsset)
             .filter(MediaAsset.kind == "activity_photo",
                     MediaAsset.is_active.is_(True),
                     MediaAsset.activity_id.isnot(None))
             .order_by(MediaAsset.activity_id, MediaAsset.sort_order.asc(),
                       MediaAsset.id.asc())
             .distinct(MediaAsset.activity_id).all())
    return [{"activity_id": a.activity_id, "thumb_url": f"/api/v1/media/{a.id}/thumb"}
            for a in rijen]


def list_activity_photos(db, activity_id: int) -> list[dict]:
    rijen = (db.query(MediaAsset)
             .filter(MediaAsset.kind == "activity_photo",
                     MediaAsset.activity_id == activity_id,
                     MediaAsset.is_active.is_(True))
             .order_by(MediaAsset.sort_order.asc(), MediaAsset.id.asc()).all())
    return [meta(a) for a in rijen]


def list_media(db, *, kind: Optional[str] = None,
               activity_id: Optional[int] = None) -> list[dict]:
    query = db.query(MediaAsset)
    if kind:
        query = query.filter(MediaAsset.kind == kind)
    if activity_id is not None:
        query = query.filter(MediaAsset.activity_id == activity_id)
    rijen = query.order_by(MediaAsset.sort_order.asc(), MediaAsset.id.desc()).all()
    return [meta(a) for a in rijen]


def update_media(db, asset_id: int, payload: dict) -> dict:
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if asset is None:
        raise LookupError("Niet gevonden")
    for veld in ("title", "link_url", "sort_order", "is_active"):
        if veld in payload:
            setattr(asset, veld, payload[veld])
    db.commit()
    db.refresh(asset)
    return meta(asset)


def delete_media(db, asset_id: int) -> None:
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if asset is None:
        raise LookupError("Niet gevonden")
    db.delete(asset)
    db.commit()


async def upload_media(db, *, files: Sequence, kind: str,
                       activity_id: Optional[int] = None,
                       title: Optional[str] = None,
                       link_url: Optional[str] = None) -> list[dict]:
    """Verwerk en bewaar een reeks geüploade afbeeldingen.

    Async omdat een `UploadFile` async gelezen wordt; verder gewone servicecode.
    De regels die hier wonen: alleen bekende soorten, een activiteitenfoto hoort
    bij een bestaande activiteit, een sponsor hangt juist níet aan een activiteit,
    hoogstens MAX_BATCH bestanden per keer, en de nieuwe `sort_order` volgt op wat
    er al in die groep staat.
    """
    from app.domains.activities.api import Activity

    if kind not in VALID_KINDS:
        raise MediaFout("Ongeldige 'kind'")
    if kind == "activity_photo":
        if activity_id is None:
            raise MediaFout("activity_id vereist voor activiteitenfoto's")
        if not db.query(Activity).filter(Activity.id == activity_id).first():
            raise LookupError("Activiteit niet gevonden")
    else:
        activity_id = None      # sponsors hangen niet aan een activiteit

    if not files:
        raise MediaFout("Geen bestanden")
    if len(files) > MAX_BATCH:
        raise MediaFout(f"Maximaal {MAX_BATCH} bestanden per keer")

    basis = db.query(MediaAsset).filter(MediaAsset.kind == kind)
    if activity_id is not None:
        basis = basis.filter(MediaAsset.activity_id == activity_id)
    volgende = basis.count()

    gemaakt = []
    for index, upload in enumerate(files):
        if upload.content_type not in ALLOWED_CONTENT_TYPES:
            raise MediaFout(f"Niet-ondersteund bestandstype: {upload.filename}")
        rauw = await upload.read()
        try:
            verwerkt = process_image(rauw)
        except ImageError as exc:
            raise MediaFout(f"{upload.filename}: {exc}")

        asset = MediaAsset(kind=kind, activity_id=activity_id,
                           title=title or upload.filename, link_url=link_url,
                           sort_order=volgende + index, is_active=True, **verwerkt)
        db.add(asset)
        gemaakt.append(asset)

    db.commit()
    for asset in gemaakt:
        db.refresh(asset)
    return [meta(a) for a in gemaakt]


def activity_ids_with_media(db) -> set[int]:
    """De activiteiten die al media hebben — voor de filter-dropdown (#459).

    Bewust een aparte functie: de dropdown toont alleen wat iets oplevert, terwijl
    de upload-keuzelijst juist álle activiteiten toont (#476). Twee lijsten met
    twee bedoelingen.
    """
    return {rij[0] for rij in db.query(MediaAsset.activity_id)
            .filter(MediaAsset.activity_id.isnot(None)).distinct()}
