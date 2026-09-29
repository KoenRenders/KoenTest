"""API-router van het MDM-component (fase 4c, #404): masterdata-lookups.

Het publieke postcode-endpoint hoort bij de masterdata (verhuisd uit de
members-router); de URL blijft ongewijzigd (/api/v1/postal-codes).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

router = APIRouter(tags=["mdm"])

POSTAL_CACHE_TTL = 3600
_postal_cache: Optional[list] = None
_postal_cache_ts: float = 0.0
