"""Dynamische tenant-code→id-lookup (#546).

De live map komt uit de actieve UNIT-organizations, met de kernel-hardgecodeerde
``TENANT_CODES`` als vangnet. Woont in het mdm-domein (Organization hoort hier);
de kernel mag `app.domains` niet importeren, dus de resolve-functies krijgen het
resultaat als `codes`-param via de middleware. Gecachet omdat resolutie per request
draait; ``invalidate_tenant_codes()`` wist de cache na een tenant-mutatie.
"""
from __future__ import annotations

from app.kernel.tenancy import TENANT_CODES

_cache: dict[str, int] | None = None


def _query(db) -> dict[str, int]:
    from app.domains.mdm.models import Organization

    rows = (db.query(Organization.code, Organization.id)
            .filter(Organization.org_type == "UNIT",
                    Organization.is_active == True).all())  # noqa: E712
    return {code.lower(): oid for code, oid in rows}


def tenant_codes(db=None) -> dict[str, int]:
    """Live code→id-map van de actieve UNIT-organizations. Met ``db`` (tests) leest
    hij rechtstreeks uit die sessie; zonder db gebruikt hij een cache met een eigen
    sessie. Vangnet bij een lege/kapotte bron: de hardgecodeerde map — resolutie mag
    nooit breken op een infrastructuurhapering."""
    global _cache
    if db is not None:
        return _query(db)
    if _cache is None:
        try:
            from app.database import SessionLocal

            s = SessionLocal()
            try:
                _cache = _query(s) or dict(TENANT_CODES)
            finally:
                s.close()
        except Exception:
            return dict(TENANT_CODES)
    return _cache


_platform_cache: int | None = None


def platform_tenant_id(db=None) -> int | None:
    """The id of the PLATFORM organization, or None if this database has none (#854).

    Looked up by ``org_type`` and never by number. Migration 086 could hand out ids
    1..3 because it created the table; by now an environment may have created tenants
    of its own through /admin/tenants, so id 4 is not free everywhere. A constant here
    would be right on one machine and wrong on the next.

    None is a normal answer, not a failure: before migration 097, and in any test that
    is not about the platform. The caller falls back to the previous behaviour, because
    request resolution must never break on a missing row.
    """
    global _platform_cache
    if db is not None:
        return _query_platform(db)
    if _platform_cache is None:
        try:
            from app.database import SessionLocal

            session = SessionLocal()
            try:
                _platform_cache = _query_platform(session)
            finally:
                session.close()
        except Exception:
            return None
    return _platform_cache


def _query_platform(db) -> int | None:
    from app.domains.mdm.models import Organization

    row = (db.query(Organization.id)
           .filter(Organization.org_type == "PLATFORM",
                   Organization.is_active == True).first())  # noqa: E712
    return row[0] if row else None


def invalidate_tenant_codes() -> None:
    """Wis de tenant_codes-cache (na het aanmaken/wijzigen van een tenant)."""
    global _cache, _platform_cache
    _cache = None
    _platform_cache = None
