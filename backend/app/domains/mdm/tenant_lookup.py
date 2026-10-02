"""Dynamische tenant-code→id-lookup (#546).

De live map komt uit de actieve UNIT-organizations, met de kernel-hardgecodeerde
``TENANT_CODES`` als vangnet. Woont in het mdm-domein (Organization hoort hier);
de kernel mag `app.domains` niet importeren, dus de resolve-functies krijgen het
resultaat als `codes`-param via de middleware. Gecachet omdat resolutie per request
draait; ``invalidate_tenant_codes()`` wist de cache na een tenant-mutatie.
"""

from __future__ import annotations

from app.domains.mdm.models import OrganizationType
from app.kernel.tenancy import TENANT_CODES

_cache: dict[str, int] | None = None


def _query(db) -> dict[str, int]:
    from app.domains.mdm.models import Organization

    rows = (
        db.query(Organization.code, Organization.id)
        .filter(Organization.org_type == OrganizationType.UNIT, Organization.is_active == True)
        .all()
    )  # noqa: E712
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

    row = (
        db.query(Organization.id)
        .filter(Organization.org_type == OrganizationType.PLATFORM, Organization.is_active == True)
        .first()
    )  # noqa: E712
    return row[0] if row else None


_modules_cache: dict[int, frozenset[str]] | None = None


def _query_modules(db) -> dict[int, frozenset[str]]:
    from app.domains.mdm.models import TenantModule

    found: dict[int, set[str]] = {}
    for tenant_id, code in db.query(TenantModule.tenant_id, TenantModule.module_code).all():
        found.setdefault(tenant_id, set()).add(code)
    return {tenant_id: frozenset(codes) for tenant_id, codes in found.items()}


def enabled_modules(tenant_id: int, db=None) -> frozenset[str]:
    """The module codes switched on for this tenant (CR-19, #1475).

    Read per request by the tenancy middleware, so cached like the code map:
    one query for every tenant, then none per request (C6 test 12 — the set must
    not add a session or a query to a request). `invalidate_tenant_codes()`
    clears it with the rest. A tenant without rows has nothing on.

    No fallback to "everything" on a failed read: a missing table is a missing
    migration, and that must show instead of hiding behind a full menu.
    """
    global _modules_cache
    if db is not None:
        return _query_modules(db).get(tenant_id, frozenset())
    if _modules_cache is None:
        from app.database import SessionLocal

        session = SessionLocal()
        try:
            _modules_cache = _query_modules(session)
        finally:
            session.close()
    return _modules_cache.get(tenant_id, frozenset())


def current_enabled_modules() -> frozenset[str]:
    """The modules on for the tenant of this request (#1475; split out for the
    menu, #1476).

    Reads the set the middleware put on the request; outside a request, the
    active (or default) tenant's set.
    """
    from app.kernel.modules import current_modules
    from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id

    enabled = current_modules.get()
    if enabled is None:
        enabled = enabled_modules(current_tenant_id.get() or DEFAULT_TENANT_ID)
    return enabled


def module_enabled(code) -> bool:
    """Is this module on for the tenant of this request? (#1475)"""
    return str(code) in current_enabled_modules()


def invalidate_tenant_codes() -> None:
    """Wis de tenant_codes-cache (na het aanmaken/wijzigen van een tenant).
    Sinds #1475 ook de modulesets."""
    global _cache, _platform_cache, _modules_cache
    _cache = None
    _platform_cache = None
    _modules_cache = None
