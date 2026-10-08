"""Assetbibliotheek: serveren (publiek) van afbeeldingen en documenten.

Afbeeldingen worden in Postgres (BYTEA) bewaard, dus ze zitten automatisch mee
in de DB-backup. Bij upload worden ze verkleind en van een thumbnail voorzien
(zie :mod:`app.domains.media.images`).
"""

import hashlib
import re
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.media import service as _service
from app.domains.media.models import MediaAsset
from app.domains.media.svg import SVG_CONTENT_TYPE
from app.i18n import _

router = APIRouter(tags=["media"])

# #1005: hier stond een tweede kopie van VALID_KINDS, die niemand las. Weg in
# plaats van bijgewerkt: twee lijsten van dezelfde soorten lopen uit elkaar, en
# de service heeft de enige die telt.
SVG_CSP = "default-src 'none'; style-src 'unsafe-inline'"


# ---------------------------------------------------------------------------
# Publiek serveren
# ---------------------------------------------------------------------------
def _safe_filename(name: Optional[str], fallback: str) -> str:
    """Header-veilige bestandsnaam (ASCII-subset) voor Content-Disposition."""
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", (name or "").strip())
    return cleaned or fallback


def _serve(
    blob: Optional[bytes],
    content_type: Optional[str],
    request: Request,
    etag_seed: str,
    *,
    filename: Optional[str] = None,
):
    if not blob:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
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
    if (content_type or "").split(";")[0].strip().lower() == SVG_CONTENT_TYPE:
        # #989: an SVG opened directly is rendered as a document on this origin.
        # The upload is cleaned (media/svg.py); these headers are the second line,
        # so that a cleaning that ever misses something still runs nothing.
        headers["Content-Security-Policy"] = SVG_CSP
        headers["X-Content-Type-Options"] = "nosniff"
    return Response(
        content=blob,
        media_type=content_type or "application/octet-stream",
        headers=headers,
    )


@router.get("/media/{asset_id}")
def serve_media(asset_id: int, request: Request, db: Session = Depends(get_db)):
    a = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not a:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    return _serve(
        a.data,
        a.content_type,
        request,
        f"full-{a.id}",
        filename=_safe_filename(a.title, f"bestand-{a.id}"),
    )


@router.get("/media/{asset_id}/thumb")
def serve_thumb(asset_id: int, request: Request, db: Session = Depends(get_db)):
    a = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not a:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    _service.give_pdf_its_picture(db, a)
    blob = a.thumbnail or a.data
    ctype = a.thumb_content_type or a.content_type
    return _serve(blob, ctype, request, f"thumb-{a.id}")


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Poster (activiteit) en info/reglement (onderdeel): één bestand, vervangbaar (#223)
# ---------------------------------------------------------------------------
