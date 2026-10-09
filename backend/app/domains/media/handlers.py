"""What media handles for the others: its three ports (`kernel/contracts/media.py`)
and the job that reads a document's text.

A port handler is thin: it turns the contract into one call of the service
function that does the work and the result into the outcome. It runs in the
caller's transaction and never commits; a refusal of the service passes through
`call` unchanged. Loaded through `app.main`, like every handler module.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.media import service
from app.domains.media.extraction import update_media_extracted_text
from app.kernel.contracts.media import (
    AssetsRemoved,
    AssetStored,
    RemoveAsset,
    RemoveFileOf,
    StoreFile,
)
from app.kernel.jobs import job
from app.kernel.ports import handles


@handles(StoreFile)
def store_file(port: StoreFile, db: Session) -> AssetStored:
    asset = service.store_file(
        db,
        kind=port.kind,
        filename=port.filename,
        content_type=port.content_type,
        content=port.content,
        activity_id=port.activity_id,
        component_id=port.component_id,
        title_base=port.title_base,
    )
    return AssetStored(asset_id=asset.id, title=asset.title, content_type=asset.content_type)


@handles(RemoveAsset)
def remove_asset(port: RemoveAsset, db: Session) -> AssetsRemoved:
    service.remove_media(db, port.asset_id)
    return AssetsRemoved(count=1)


@handles(RemoveFileOf)
def remove_file_of(port: RemoveFileOf, db: Session) -> AssetsRemoved:
    removed = service.remove_file_of(
        db, kind=port.kind, activity_id=port.activity_id, component_id=port.component_id
    )
    return AssetsRemoved(count=removed)


@job(service.EXTRACT_JOB)
def extract_text(db: Session, payload: dict) -> None:
    """Read the text of one document into the AI context. The job and not the
    request reaches the OCR provider; a failed read is logged and leaves the
    document as it was."""
    update_media_extracted_text(payload["asset_id"], db, bool(payload.get("force")))
