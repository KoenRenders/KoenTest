"""The module registry: what a module owns, and the guard that switches it off
per tenant (CR-19 §C4.2, §C4.3; #1475).

**The registry is code; the enabled set is data.** What a module owns — its menu
items, route prefixes, tiles — changes with the code, so it lives here, one
entry per module. Which modules a tenant has on is a fact about that tenant and
lives in `mdm.tenant_modules`. A new module is one entry here plus a migration
that widens that table's CHECK.

**The registry imports no domain.** It describes; the domains do. `main.py`
puts `require_module(...)` on each module router where it includes it, so no
domain file names its module (§C4.3). `tests/test_module_gate.py` holds that
every included router is either guarded or on the shell list.

**A field a module has nothing for stays empty.** The registry describes what
exists today, not a wish list: the sitemap has the paths the sitemap lists, the
newsletter the audiences it offers.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import HTTPException, status

from app.i18n import _
from app.kernel.codes import TechnicalEnum


class ModuleCode(str, TechnicalEnum):
    """A module that can be switched off per tenant.

    Stored in `mdm.tenant_modules.module_code`, and still deliberately without a
    code table (CR-19 §C4.2, accepted by the platform owner on 2 October 2026):
    a module exists only when its code exists here, so a table would be a second
    place for this list, and the label is the menu label the registry already
    carries. The column's CHECK holds the stored values to these.
    """

    ACTIVITIES = "activities"
    MEMBERSHIP = "membership"
    PAYMENT = "payment"
    FORMS = "forms"
    CMS = "cms"
    MEDIA = "media"
    NEWSLETTER = "newsletter"
    MEETINGS = "meetings"
    DESIGNSTUDIO = "designstudio"
    REPORTING = "reporting"
    WORKFLOW = "workflow"
    CHATBOT = "chatbot"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Module:
    """What one module owns. Paths are as a visitor or a caller sees them."""

    code: ModuleCode
    label: str
    #: Admin menu items, as (href, label) — the menu of `app.ui.admin_nav`.
    admin_items: tuple[tuple[str, str], ...] = ()
    #: Public navigation items of the site shell, as (href, label).
    public_items: tuple[tuple[str, str], ...] = ()
    #: Path prefixes only this module serves; each is served by a guarded router.
    route_prefixes: tuple[str, ...] = ()
    #: Dashboard tiles, by their report key (`reporting.DASHBOARD_TEGELS`).
    dashboard_tiles: tuple[str, ...] = ()
    #: Blocks of the shell's home page that belong to this module.
    home_blocks: tuple[str, ...] = ()
    #: Fixed paths this module adds to the sitemap.
    sitemap_paths: tuple[str, ...] = ()
    #: Newsletter audiences that only exist with this module (codes).
    newsletter_audiences: tuple[str, ...] = ()
    #: Classes of the reporting universe that describe this module's data.
    reporting_folders: tuple[str, ...] = ()
    #: Other modules this one needs. A tuple of alternatives means "one of".
    depends_on: tuple[tuple[ModuleCode, ...], ...] = ()
    #: The tables whose rows the tenant editor counts for this module (#1478):
    #: its main records, and the data that becomes unreachable when it is off.
    record_tables: tuple[str, ...] = ()


M = ModuleCode

#: Every module, in menu order. The boundaries that are not obvious are written
#: out in CR-19 §C2: mdm's master data (persons, households as data,
#: organisations, postal codes, tenants) is core and never off.
MODULES: tuple[Module, ...] = (
    Module(
        M.WORKFLOW,
        "Werkbank",
        admin_items=(("/admin/werkbank", "Werkbank"),),
        route_prefixes=("/admin/werkbank",),
        dashboard_tiles=("dashboard_open_tasks",),
        reporting_folders=("Taken",),
        record_tables=("workflow.workflow_tasks",),
    ),
    Module(
        M.ACTIVITIES,
        "Activiteiten",
        admin_items=(("/admin/activiteiten", "Activiteiten"),),
        public_items=(("/archief", "Archief"),),
        route_prefixes=("/api/v1/activities", "/admin/activiteiten", "/activiteiten", "/archief"),
        dashboard_tiles=("dashboard_upcoming_activities",),
        home_blocks=("activity_cards",),
        sitemap_paths=("/activiteiten", "/activiteiten/archief"),
        reporting_folders=("Activiteiten",),
        record_tables=("activities.activities", "activities.registrations"),
    ),
    Module(
        M.MEMBERSHIP,
        "Leden",
        admin_items=(("/admin/leden", "Leden"),),
        public_items=(("/leden/gezin", "Mijn gezin"),),
        route_prefixes=("/api/v1/families", "/lid-worden", "/leden/gezin", "/admin/leden"),
        dashboard_tiles=(
            "dashboard_members",
            "dashboard_active_members",
            "dashboard_member_persons",
        ),
        home_blocks=("membership_band",),
        sitemap_paths=("/lid-worden",),
        newsletter_audiences=("members", "non_members", "both"),
        reporting_folders=("Leden",),
        record_tables=("mdm.members", "membership.memberships"),
    ),
    Module(
        M.FORMS,
        "Formulieren",
        admin_items=(("/admin/formulieren", "Formulieren"),),
        route_prefixes=("/api/v1/forms", "/admin/formulieren", "/f/", "/formulier/"),
        sitemap_paths=("/berichten",),
        reporting_folders=("Formulieren",),
        record_tables=("form.forms", "form.form_submissions"),
    ),
    Module(
        M.CMS,
        "Pagina's",
        admin_items=(("/admin/paginas", "Pagina's"),),
        route_prefixes=("/api/v1/pages", "/admin/paginas"),
        record_tables=("cms.cms_pages",),
    ),
    Module(
        M.MEDIA,
        "Media",
        admin_items=(("/admin/media", "Media"),),
        public_items=(("/fotos", "Foto's"),),
        route_prefixes=("/api/v1/media", "/admin/media", "/fotos"),
        sitemap_paths=("/fotos",),
        record_tables=("media.media_assets",),
    ),
    Module(
        M.CHATBOT,
        "Raakje",
        admin_items=(("/admin/ai-context", "Raakje"), ("/admin/rapporten/raakje", "AI · Raakje")),
        route_prefixes=("/api/v1/chat", "/admin/ai-context", "/raakje/"),
        record_tables=("ai.chatbot_info",),
    ),
    Module(
        M.PAYMENT,
        "Betalingen",
        admin_items=(("/admin/betalingen", "Betalingen"),),
        route_prefixes=("/admin/betalingen", "/api/v1/payment-gateway"),
        dashboard_tiles=("dashboard_outstanding",),
        reporting_folders=("Betalingen",),
        # Payments pay for a registration or a membership (`PayableType`).
        depends_on=((M.ACTIVITIES, M.MEMBERSHIP),),
        record_tables=("payment.payment_records",),
    ),
    Module(
        M.MEETINGS,
        "Vergaderingen",
        admin_items=(("/admin/vergaderingen", "Vergaderingen"),),
        route_prefixes=("/admin/vergaderingen",),
        record_tables=("meetings.meetings",),
    ),
    Module(
        M.NEWSLETTER,
        "Nieuwsbrief",
        admin_items=(("/admin/nieuwsbrieven", "Nieuwsbrief"),),
        route_prefixes=("/admin/nieuwsbrieven", "/nieuwsbrief"),
        record_tables=("newsletter.newsletters", "newsletter.subscribers"),
    ),
    Module(
        M.DESIGNSTUDIO,
        "Design Studio",
        admin_items=(("/admin/ontwerpen", "Design Studio"),),
        route_prefixes=("/admin/ontwerpen",),
        # A design is made for an activity (`designs.activity_id NOT NULL`).
        depends_on=((M.ACTIVITIES,),),
        record_tables=("designstudio.designs",),
    ),
    Module(
        M.REPORTING,
        "Rapporten",
        admin_items=(("/admin/rapporten", "Rapporten"),),
        route_prefixes=("/admin/rapporten",),
    ),
)

REGISTRY: dict[ModuleCode, Module] = {module.code: module for module in MODULES}

#: Modules the tenant editor shows without a count (#1478), each with its
#: reason. Reporting is a terminus (CR-07 §6.6): nothing outside its domain
#: addresses its schema, so its saved reports are not counted from here.
UNCOUNTED: dict[ModuleCode, str] = {
    M.REPORTING: "a terminus: its schema is addressed only from its own domain",
}

#: The modules a new tenant starts with, per kind (CR-19 §C2 kernel). The kind
#: itself arrives with #1478; until then every tenant is a VERENIGING.
DEFAULTS: dict[str, frozenset[ModuleCode]] = {
    "VERENIGING": frozenset(ModuleCode),
    "BEDRIJF": frozenset({M.CMS, M.MEDIA, M.FORMS, M.WORKFLOW}),
}


def record_counts(db, tenant_id: int) -> dict[ModuleCode, int]:
    """How many records each module holds for this tenant (#1478, CR-19 F12).

    The tenant editor shows it next to each module, because switching a module
    off deletes nothing: its data stays, unreachable until it is switched on
    again, and the operator should see how much that is before the click.

    Here beside the registry and not in a domain, so no domain reads another
    domain's tables; it only reads, and only counts. Each table is filtered on
    its own `tenant_id` explicitly (a Core select gets no ORM tenant filter),
    and a soft-deleted row does not count. Every table listed has `tenant_id`;
    `test_module_gate` holds that.
    """
    from sqlalchemy import func, select

    from app.database import Base

    counts: dict[ModuleCode, int] = {}
    for module in MODULES:
        if module.code in UNCOUNTED:
            continue
        total = 0
        for name in module.record_tables:
            table = Base.metadata.tables[name]
            query = select(func.count()).select_from(table).where(table.c.tenant_id == tenant_id)
            if "deleted_at" in table.c:
                query = query.where(table.c.deleted_at.is_(None))
            total += db.execute(query).scalar_one()
        counts[module.code] = total
    return counts


# ── The guard ────────────────────────────────────────────────────────────────

#: The enabled set of the tenant this request resolved to, put here by the
#: tenancy middleware in `main.py`. None outside a request (a job, a script, a
#: test calling a service): no request, nothing to refuse.
current_modules: ContextVar[frozenset[str] | None] = ContextVar("current_modules", default=None)


def require_module(code: ModuleCode):
    """A FastAPI dependency: 404 when `code` is off for the resolved tenant.

    404 and not 403: for that tenant the pages do not exist (§C4.3). Applied
    at include time in `main.py`, so it runs before any role guard of the
    router — a module that is off is 404 for that tenant's admin too. Its data
    stays, unreachable until the module is switched on again.

    The returned function carries `module_code`, so the gate can read which
    module a router is guarded by.
    """

    def guard() -> None:
        enabled = current_modules.get()
        if enabled is not None and code.value not in enabled:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Niet gevonden"))

    guard.module_code = code  # type: ignore[attr-defined]
    guard.__name__ = f"require_module_{code.value}"
    return guard
