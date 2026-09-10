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

# De host waarop dit verzoek binnenkwam, als origin (#860). Absolute URL's — de
# inloglink, de Mollie-redirect, de bewerklink van een inzending, sitemap/robots —
# hoorden altijd al terug te wijzen naar de site waar je vandaan komt, maar
# `tenant_base_url` keek daar nooit naar. Op een platform-host leverde dat een
# inloglink naar een afdelingssite op: je sessiecookie belandde op de verkeerde host
# en je was op het platform nog steeds anoniem.
#
# Het SCHEMA komt uit `FRONTEND_URL` en niet uit het verzoek: er staat geen
# proxy-header-verwerking aan, dus achter Caddy leest elk verzoek als http. De
# omgeving weet of ze https draait, het verzoek weet welke host — elk levert wat het
# echt weet. De poort hoort bij de host en blijft dus staan.
#
# Leeg buiten een verzoek (achtergrondjobs, scripts): dan blijft `FRONTEND_URL` de
# enige waarheid die er is.
current_origin: ContextVar[str | None] = ContextVar("current_origin", default=None)

# Kwam dit verzoek binnen op een platform-host? Bepaalt of een afdeling zonder eigen
# domein haar adres afleidt als <platform-origin>/<code> (#860).
current_platform_host: ContextVar[bool] = ContextVar("current_platform_host", default=False)

# De code van de actieve tenant, als ze er een heeft (UNIT). None voor de
# platform-tenant zelf: die staat niet in de code→id-map en heeft geen pad-prefix.
current_tenant_code: ContextVar[str | None] = ContextVar("current_tenant_code", default=None)


def _tenant_default() -> int:
    return current_tenant_id.get() or DEFAULT_TENANT_ID


@declarative_mixin
class TenantMixin:
    """Rij-niveau tenancy: elke tenant-tabel draagt een verplichte, geïndexeerde
    ``tenant_id`` (RLS aanzetten wordt zo later een migratieregel, geen verbouwing)."""

    @declared_attr
    def tenant_id(cls):  # noqa: N805 - declarative_mixin-conventie
        return Column(Integer, nullable=False, index=True, default=_tenant_default)


# Tenant-codes (organizations.code) → id. Deze hardgecodeerde map blijft het
# vangnet/de default voor de gekende tenants; de LIVE map komt sinds #546 dynamisch
# uit `organizations` (zie tenant_codes()), zodat een nieuwe tenant zonder
# codewijziging resolvet.
TENANT_CODES: dict[str, int] = {
    "raakmillegem": TENANT_MILLEGEM_ID,
    "raakvoorbeeldafdeling": TENANT_VOORBEELD_ID,
}

# De LIVE code→id-map komt sinds #546 dynamisch uit `organizations`. Die DB-lezing
# hoort NIET in de kernel (importgrens: kernel → domains verboden): ze zit in
# `app.domains.mdm.api.tenant_codes()`. De middleware geeft het resultaat als
# `codes`-param door aan de resolve-functies hieronder; zonder param blijft de
# hardgecodeerde TENANT_CODES het vangnet.


def resolve_tenant(host: str | None, path: str,
                   hostname_map: dict[str, str],
                   codes: dict[str, int] | None = None) -> int:
    """Resolutievolgorde §7: hostname → pad-prefix → default (Millegem).

    ``hostname_map`` komt uit de settings (``TENANT_HOSTNAMES``), bv.
    ``{"raakmillegem.be": "raakmillegem"}``. Een pad-prefix als
    ``/raakvoorbeeldafdeling/...`` wint enkel als de hostname niets oplevert.
    ``codes`` = de code→id-map (default: de hardgecodeerde TENANT_CODES; de
    middleware geeft de dynamische tenant_codes() door — #546).
    """
    codes = codes if codes is not None else TENANT_CODES
    host = (host or "").split(":")[0].lower().removeprefix("www.")
    code = hostname_map.get(host)
    if code in codes:
        return codes[code]
    eerste = path.lstrip("/").split("/", 1)[0].lower()
    if eerste in codes:
        return codes[eerste]
    return DEFAULT_TENANT_ID


def resolve_request(host: str | None, path: str, cookie_code: str | None,
                    hostname_map: dict[str, str],
                    platform_hosts: set[str],
                    codes: dict[str, int] | None = None,
                    platform_tenant: int | None = None) -> tuple[int, str | None, bool]:
    """Volledige request-resolutie (§7, 5c): geeft (tenant_id, herschreven pad
    of None, platform-landing?).

    - Pad-prefix (``/raakvoorbeeldafdeling/...``) wint van alles: de prefix
      wordt van het pad gestript (de app kent maar één routetabel) en de
      middleware zet een tenant-cookie zodat vervolgnavigatie (absolute
      paden zonder prefix) op dezelfde tenant blijft.
    - Daarna hostname, dan de tenant-cookie (enkel op platform-hosts), dan
      de platform-tenant als de host er een is, en anders de default (Millegem).
    - De wortel van een platform-host (platform.example, "/") is de landingspagina.

    ``platform_tenant`` is het id van de PLATFORM-organisatie (#854). Een
    platform-host resolvet daarnaartoe op **elk** pad, niet alleen op ``/``. Daarvóór
    viel elk ander pad terug op de standaardtenant, en dan kreeg een platformbeheerder
    de schil van Raak Millegem te zien én een e-mail van die afdeling (#853). Er was
    niets om naar te resolven; nu wel.

    ``None`` betekent "die rij bestaat hier nog niet" — vóór migratie 097, in een test
    die er niet over gaat, of bij een haperende lookup. Dan blijft het oude gedrag
    gelden. Resolutie mag nooit stukvallen op een ontbrekende rij; ze wordt hooguit
    minder precies.
    """
    codes = codes if codes is not None else TENANT_CODES
    genormaliseerd = (host or "").split(":")[0].lower().removeprefix("www.")
    eerste = path.lstrip("/").split("/", 1)[0].lower()
    if eerste in codes:
        rest = path.lstrip("/")[len(eerste):] or "/"
        return codes[eerste], rest, False
    code = hostname_map.get(genormaliseerd)
    if code in codes:
        return codes[code], None, False
    if genormaliseerd in platform_hosts:
        # De cookie blijft vóór de platform-tenant staan, en dat is met opzet: wie via
        # een pad-prefix bij een afdeling binnenkwam, hoort daar te blijven als hij
        # daarna een absoluut pad volgt. Zonder cookie is de host het enige signaal,
        # en dan is dit het platform.
        if path != "/" and cookie_code in codes:
            return codes[cookie_code], None, False
        return (platform_tenant or DEFAULT_TENANT_ID), None, path == "/"
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
