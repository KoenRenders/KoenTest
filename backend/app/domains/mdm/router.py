"""API-router van het MDM-component (fase 4c, #404): masterdata-lookups.

Het publieke postcode-endpoint hoort bij de masterdata (verhuisd uit de
members-router); de URL blijft ongewijzigd (/api/v1/postal-codes).
"""
from __future__ import annotations

import time
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.mdm.models import PostalCode
from app.domains.membership.api import PostalCodeResponse

router = APIRouter(tags=["mdm"])

POSTAL_CACHE_TTL = 3600
_postal_cache: Optional[list] = None
_postal_cache_ts: float = 0.0


@router.get("/postal-codes", response_model=List[PostalCodeResponse])
def list_postal_codes(db: Session = Depends(get_db)):
    """Alle postcodes met gemeentenaam (gecachet — referentiedata)."""
    global _postal_cache, _postal_cache_ts
    now = time.time()
    if _postal_cache is not None and (now - _postal_cache_ts) < POSTAL_CACHE_TTL:
        return _postal_cache
    rows = db.query(PostalCode).order_by(PostalCode.postal_code).all()
    _postal_cache = [PostalCodeResponse(postal_code=r.postal_code, municipality=r.municipality)
                     for r in rows]
    _postal_cache_ts = now
    return _postal_cache
