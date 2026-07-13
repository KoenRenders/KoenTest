"""Tenant-context + mixin + globale filter (§7, fase 5 #406).

Rij-niveau tenancy in een gedeeld schema: elke tenant-tabel draagt een
verplichte, geïndexeerde ``tenant_id`` (UNIT uit ``mdm.organizations``).
RLS-klaar vanaf dag één: RLS aanzetten wordt later een migratieregel.

De actieve tenant komt uit ``current_tenant_id`` (gezet door de
resolutie-middleware in ``main.py``: hostname → pad-prefix → default).
``None`` = geen filtering (single-tenant-compatibel; ook voor achtergrondjobs
die bewust over alle tenants werken). Een query die dwars over tenants moet
(operator-rapportage) zet ``.execution_options(include_all_tenants=True)``.
"""
from __future__ import annotations

from contextvars import ContextVar

from sqlalchemy import Column, Integer, event
from sqlalchemy.orm import Session, declarative_mixin, declared_attr, with_loader_criteria

# Vaste organization-ids uit de seed (migratie 086) — bewust deterministisch,
# zodat code en migraties dezelfde ids kennen zonder lookup.
ACCOUNT_RAAK_ID = 1
TENANT_MILLEGEM_ID = 2
TENANT_VOORBEELD_ID = 3

# Zolang er geen expliciete tenant-context is (achtergrondjobs, scripts, de
# overgangsfase) schrijven nieuwe rijen naar de standaard-tenant: Millegem.
DEFAULT_TENANT_ID = TENANT_MILLEGEM_ID

# Actieve tenant voor dit request. None = geen filtering.
current_tenant_id: ContextVar[int | None] = ContextVar("current_tenant_id", default=None)


def _tenant_default() -> int:
    return current_tenant_id.get() or DEFAULT_TENANT_ID


@declarative_mixin
class TenantMixin:
    """Rij-niveau tenancy: elke tenant-tabel draagt een verplichte, geïndexeerde
    ``tenant_id`` (RLS aanzetten wordt zo later een migratieregel, geen verbouwing)."""

    @declared_attr
    def tenant_id(cls):  # noqa: N805 - declarative_mixin-conventie
        return Column(Integer, nullable=False, index=True, default=_tenant_default)


# Tenant-codes (organizations.code) → id, voor pad-prefix- en hostnaamresolutie.
TENANT_CODES: dict[str, int] = {
    "raakmillegem": TENANT_MILLEGEM_ID,
    "raakvoorbeeldafdeling": TENANT_VOORBEELD_ID,
}


def resolve_tenant(host: str | None, path: str,
                   hostname_map: dict[str, str]) -> int:
    """Resolutievolgorde §7: hostname → pad-prefix → default (Millegem).

    ``hostname_map`` komt uit de settings (``TENANT_HOSTNAMES``), bv.
    ``{"raakmillegem.be": "raakmillegem"}``. Een pad-prefix als
    ``/raakvoorbeeldafdeling/...`` wint enkel als de hostname niets oplevert.
    """
    host = (host or "").split(":")[0].lower().removeprefix("www.")
    code = hostname_map.get(host)
    if code in TENANT_CODES:
        return TENANT_CODES[code]
    eerste = path.lstrip("/").split("/", 1)[0].lower()
    if eerste in TENANT_CODES:
        return TENANT_CODES[eerste]
    return DEFAULT_TENANT_ID


def resolve_request(host: str | None, path: str, cookie_code: str | None,
                    hostname_map: dict[str, str],
                    platform_hosts: set[str]) -> tuple[int, str | None, bool]:
    """Volledige request-resolutie (§7, 5c): geeft (tenant_id, herschreven pad
    of None, platform-landing?).

    - Pad-prefix (``/raakvoorbeeldafdeling/...``) wint van alles: de prefix
      wordt van het pad gestript (de app kent maar één routetabel) en de
      middleware zet een tenant-cookie zodat vervolgnavigatie (absolute
      paden zonder prefix) op dezelfde tenant blijft.
    - Daarna hostname, dan de tenant-cookie (enkel op platform-hosts), dan
      de default (Millegem).
    - De wortel van een platform-host (renko.be, "/") is de landingspagina.
    """
    genormaliseerd = (host or "").split(":")[0].lower().removeprefix("www.")
    eerste = path.lstrip("/").split("/", 1)[0].lower()
    if eerste in TENANT_CODES:
        rest = path.lstrip("/")[len(eerste):] or "/"
        return TENANT_CODES[eerste], rest, False
    code = hostname_map.get(genormaliseerd)
    if code in TENANT_CODES:
        return TENANT_CODES[code], None, False
    if genormaliseerd in platform_hosts:
        if path == "/":
            return DEFAULT_TENANT_ID, None, True
        if cookie_code in TENANT_CODES:
            return TENANT_CODES[cookie_code], None, False
    return DEFAULT_TENANT_ID, None, False


def parse_hostname_map(raw: str) -> dict[str, str]:
    """Parseer ``TENANT_HOSTNAMES`` ("host=code,host=code") naar een dict."""
    mapping: dict[str, str] = {}
    for paar in raw.split(","):
        if "=" in paar:
            host, code = paar.split("=", 1)
            mapping[host.strip().lower()] = code.strip().lower()
    return mapping


@event.listens_for(Session, "do_orm_execute")
def _filter_tenant(execute_state):
    """Globale tenant-filter — zelfde canonieke recept als de soft-delete-filter
    (#166): elke ORM-SELECT (incl. relationship-loads) krijgt automatisch
    ``tenant_id = <actieve tenant>``. Geen actieve tenant (None) = geen filter."""
    tenant = current_tenant_id.get()
    if (
        tenant is not None
        and execute_state.is_select
        and not execute_state.is_column_load
        and not execute_state.execution_options.get("include_all_tenants", False)
    ):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                TenantMixin,
                lambda cls: cls.tenant_id == tenant,
                include_aliases=True,
            )
        )
