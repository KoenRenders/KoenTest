"""Admin-upload van het Raak-Nationaal-ledenrapport (#170).

Twee stappen, met het bestand server-side gecachet tussen beide:

1. ``POST /admin/member-import/preview`` — upload het rapport (.xls of .ods),
   parse het in geheugen en draai een **dry-run** (``upsert_families(apply=False)``).
   Geeft een token + rapport terug van wat *zou* veranderen.
2. ``POST /admin/member-import/commit`` — met dat token wordt het gecachete
   bestand opnieuw geparsed en **echt** toegepast (``apply=True``) + commit.

De upsert-logica en de rapport-parsing zijn gedeeld met het CLI-script.
"""
import secrets
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.user import User
from app.services.ledenrapport import parse_families
from app.services.member_import import upsert_families

router = APIRouter(tags=["member-import"])

# Server-side cache van geüploade bestanden tussen preview en commit.
# In-memory met TTL — een import is een eenmalige, kortlevende admin-actie.
_PENDING: dict[str, dict] = {}
_TTL_SECONDS = 900          # 15 minuten
_MAX_PENDING = 20           # bovengrens op gelijktijdige imports
_MAX_FILE_BYTES = 5 * 1024 * 1024   # 5 MB


def _purge_expired() -> None:
    now = time.monotonic()
    for tok in [t for t, e in _PENDING.items() if now - e["created_at"] > _TTL_SECONDS]:
        _PENDING.pop(tok, None)


def _store(content: bytes) -> str:
    _purge_expired()
    if len(_PENDING) >= _MAX_PENDING:
        raise HTTPException(status_code=429, detail="Te veel openstaande imports. Probeer later opnieuw.")
    token = secrets.token_urlsafe(24)
    _PENDING[token] = {"content": content, "created_at": time.monotonic()}
    return token


def _take(token: str) -> dict:
    """Haal de cache-entry op en verwijder ze. 404 onbekend, 410 verlopen.

    Het verloop van dít token wordt vóór de opruiming van de overige gecheckt,
    zodat een net-verlopen token een duidelijke 410 geeft i.p.v. 404."""
    entry = _PENDING.get(token)
    if entry is None:
        raise HTTPException(status_code=404, detail="Onbekende of reeds gebruikte import. Laad het bestand opnieuw op.")
    if time.monotonic() - entry["created_at"] > _TTL_SECONDS:
        _PENDING.pop(token, None)
        raise HTTPException(status_code=410, detail="De import is verlopen. Laad het bestand opnieuw op.")
    _purge_expired()
    return _PENDING.pop(token)


def _parse_or_400(content: bytes, filename: str | None):
    if filename and filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400,
                            detail="Het .xlsx-formaat wordt niet ondersteund. Gebruik .xls (export uit Raak Nationaal) of .ods (LibreOffice Calc).")
    try:
        return parse_families(content)
    except Exception:
        raise HTTPException(status_code=400, detail="Kon het ledenrapport niet lezen. Is het een geldig .xls- of .ods-bestand?")


class CommitRequest(BaseModel):
    token: str


@router.post("/admin/member-import/preview")
async def preview(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Leeg bestand.")
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Bestand te groot (max 5 MB).")

    families, bl_index, all_bl_names, _ = _parse_or_400(content, file.filename)
    # apply=False muteert de sessie niet: het rapport beschrijft enkel wat zou
    # veranderen. Pas bij commit wordt er weggeschreven.
    report = upsert_families(db, families, bl_index, all_bl_names, apply=False,
                             actor=admin.email)

    token = _store(content)
    return {
        "token": token,
        "selected_families": len(families),
        "total_persons": sum(len(f) for f in families),
        "report": report.to_dict(),
    }


@router.post("/admin/member-import/commit")
def commit(
    req: CommitRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    entry = _take(req.token)
    families, bl_index, all_bl_names, _ = _parse_or_400(entry["content"], None)
    report = upsert_families(db, families, bl_index, all_bl_names, apply=True,
                             actor=admin.email)
    db.commit()
    return {
        "selected_families": len(families),
        "total_persons": sum(len(f) for f in families),
        "report": report.to_dict(),
    }
