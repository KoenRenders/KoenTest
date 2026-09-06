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
from app.i18n import _

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
        "byte_size": asset.byte_size,
        "content_type": asset.content_type,
        "is_pdf": asset.content_type == "application/pdf",
        "url": f"/api/v1/media/{asset.id}",
        "thumb_url": f"/api/v1/media/{asset.id}/thumb",
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
            # #696: v1.14 zei "Kies eerst een activiteit." en dat is wat de
            # gebruiker moet doen; "activity_id vereist" is de naam van een
            # kolom. Deze tekst komt in de foutbanner op het uploadscherm.
            raise MediaFout(_("Kies eerst een activiteit."))
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


# ── Affiches, onderdeel-info en hertekstextractie (#635 I) ───────────────────
# Deze vijf stonden als routerfuncties in `router.py` en werden door de
# beheerschermen geïmporteerd. Ze dragen domeinregels: een affiche vervangt de
# vorige (er is er één per activiteit), verwijderen neemt de geëxtraheerde tekst
# vanzelf mee, en hertekstextractie mag alleen op een leesbaar documenttype.

async def replace_activity_poster(db, activity_id: int, file, background_tasks):
    """Vervang de affiche van een activiteit.

    De tekstextractie loopt op de achtergrond (#206): de upload slaagt meteen, de
    (mogelijk betalende) OCR raakt de respons niet. De tekst komt op het
    media-record, niet op de activiteit.
    """
    from app.domains.activities.api import get_activity
    from app.domains.media.extraction import update_media_extracted_text
    from app.domains.media.router import _replace_single_asset

    activity = get_activity(db, activity_id)
    if activity is None:
        raise LookupError("Activiteit niet gevonden")
    asset = await _replace_single_asset(
        db, file, kind="activity_poster", activity_id=activity_id,
        title_base=f"{activity.name} - poster")
    background_tasks.add_task(update_media_extracted_text, asset.id)
    return meta(asset)


def delete_activity_poster(db, activity_id: int) -> None:
    """Hard delete: dat neemt de geëxtraheerde tekst vanzelf mee (#206)."""
    for asset in (db.query(MediaAsset)
                  .filter(MediaAsset.kind == "activity_poster",
                          MediaAsset.activity_id == activity_id).all()):
        db.delete(asset)
    db.commit()


def reextract_text(db, asset_id: int, background_tasks) -> dict:
    """De "Opnieuw lezen"-knop (#235).

    Draait op de achtergrond en raakt enkel `extracted_text` aan — een handmatige
    override of aanvulling in de AI-context blijft staan.
    """
    from app.domains.media.extraction import (EXTRACTABLE_KINDS,
                                              update_media_extracted_text)

    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if asset is None or asset.kind not in EXTRACTABLE_KINDS:
        raise LookupError("Document niet gevonden")
    background_tasks.add_task(update_media_extracted_text, asset_id, None, True)
    return {"status": "bezig", "asset_id": asset_id}


async def replace_component_info(db, component_id: int, file, background_tasks):
    """Vervang het info-document van een onderdeel.

    Ook info-PDF's leveren context voor Raakje, dus de tekstextractie loopt hier
    net zo goed op de achtergrond (#206).
    """
    from app.domains.activities.api import get_component
    from app.domains.media.extraction import update_media_extracted_text
    from app.domains.media.router import _replace_single_asset

    component = get_component(db, component_id)
    if component is None:
        raise LookupError("Onderdeel niet gevonden")
    activiteit_naam = component.activity.name if component.activity else "activiteit"
    asset = await _replace_single_asset(
        db, file, kind="component_info", component_id=component_id,
        title_base=f"{activiteit_naam} - {component.name} - info")
    background_tasks.add_task(update_media_extracted_text, asset.id)
    return meta(asset)


def delete_component_info(db, component_id: int) -> None:
    for asset in (db.query(MediaAsset)
                  .filter(MediaAsset.kind == "component_info",
                          MediaAsset.component_id == component_id).all()):
        db.delete(asset)
    db.commit()
