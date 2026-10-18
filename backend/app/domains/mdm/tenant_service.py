"""Tenants aanmaken en hun instellingen bewaren (#635 G).

Stond volledig inline in `app/ui/tenants_ui.py`: de slug-regex, de uniciteitscheck
op de code, de basis-settings, het wissen van de
tenant-cache, en de "leeg laten = ongewijzigd"-semantiek voor geheime sleutels.
Dat laatste is de gevoeligste regel van het scherm — een lege invoer mag een
opgeslagen Mollie-key of Gmail-wachtwoord níet wissen — en ze was alleen als
scherm-code testbaar.

Woont in `domains/mdm/` en niet in de kernel, omdat `Tenant` hier woont: de
kernel mag per laagmodel (§8) niet uit een domein importeren, en die regel is
terecht — de kernel draagt geen domeinkennis. Sinds CR-20 is een tenant een eigen
rij (`mdm.tenants`) en geen organisatie meer; hij blijft mdm-data.

De schrijffuncties committen zélf. Dat is de regel uit #635-2: de transactiegrens
ligt in de service, niet in het scherm — zo geldt ze voor élke ingang en niet
alleen voor de route die er toevallig aan dacht.
"""

import logging
import re
from typing import Iterable, Mapping

from app.domains.mdm.models import TenantKind

logger = logging.getLogger(__name__)

_CODE = re.compile(r"[a-z0-9-]+")


class TenantFout(ValueError):
    """Een invoerfout die het scherm als banner toont. Bewust geen HTTPException:
    de service kent geen HTTP, en de UI-route bepaalt zelf welke statuscode of
    welk sjabloon erbij hoort."""


class ModuleRefused(TenantFout):
    """A module set refused because a module lacks one it depends on (#1478).
    Carries that module, so the editor shows the refusal on its card (#1498)."""

    def __init__(self, message: str, module) -> None:
        super().__init__(message)
        self.module = module


#: The kinds a new tenant may take (#1523): every kind but PLATFORM — there is
#: one platform, and a new tenant is never it.
CREATABLE_TENANT_KINDS = (TenantKind.ASSOCIATION, TenantKind.COMPANY)


def create_tenant(
    db,
    *,
    code: str,
    account_id: int | None,
    organization_id: int | None = None,
    site_name: str = "",
    base_url: str = "",
    kind=None,
    new_account_name: str | None = None,
    new_organization_name: str | None = None,
):
    """Make a tenant — a row of `mdm.tenants` — with its base settings (CR-20 F6).

    A tenant is a site, never a party: it names an organisation as its account
    and one as the organisation it shows (the account when none is given). Both
    are existing organisations, or — the "nieuwe organisatie" of Tenants › Nieuw
    (CR-20 F5) — one made here by its name (`new_account_name`,
    `new_organization_name`), in the same transaction, so a refused tenant leaves
    no organisation behind. The code is the key an incoming request resolves to,
    so it must have the slug form and be unique. After the commit the code cache
    is cleared, or the new tenant only resolves after a restart (#546).

    CR-19 (#1478): the kind — VERENIGING unless given — sets the modules the
    tenant starts with.
    """
    from app.domains.mdm.models import Tenant, TenantModule
    from app.domains.mdm.tenant_lookup import invalidate_tenant_codes
    from app.kernel.modules import DEFAULTS
    from app.kernel.tenant_config import set_setting

    code = _check_code(db, code)
    try:
        kind = TenantKind(kind) if kind else TenantKind.ASSOCIATION
    except ValueError:
        raise TenantFout("Kies het type: vereniging of bedrijf.") from None
    if kind not in CREATABLE_TENANT_KINDS:
        raise TenantFout("Kies het type: vereniging of bedrijf.")
    # Everything is checked before an organisation is made, so a refusal
    # writes nothing.
    new_account = _checked_name(new_account_name) if new_account_name is not None else None
    new_shown = _checked_name(new_organization_name) if new_organization_name is not None else None
    if new_account is None:
        account = _checked_account(db, None, str(account_id) if account_id is not None else "")
        if new_shown is None:
            shown = _checked_site_organization(
                db, None, str(organization_id) if organization_id else "", account
            )
    elif new_shown is None and organization_id:
        # A new account owns nothing yet: it may show an organisation that no
        # tenant names, never one of another account.
        from app.domains.mdm.models import Organization, Tenant

        other = db.get(Organization, organization_id)
        named = (
            db.query(Tenant.id)
            .filter(
                (Tenant.account_id == organization_id) | (Tenant.organization_id == organization_id)
            )
            .first()
        )
        if other is None or other.deleted_at is not None or named is not None:
            raise TenantFout("Kies een organisatie van het eigen account.")
    if new_account is not None:
        account = _new_party(db, new_account).id
        if new_shown is None:
            shown = organization_id or account
    if new_shown is not None:
        shown = _new_party(db, new_shown).id
    tenant = Tenant(
        code=code,
        kind=kind,
        account_id=account,
        organization_id=shown,
        site_name=_checked_site_name(site_name),
        is_active=True,
    )
    db.add(tenant)
    db.flush()

    # Basis-settings; de rest zet de OPERATOR in de editor van deze tenant.
    if (base_url or "").strip():
        set_setting(db, "base_url", base_url.strip(), tenant_id=tenant.id)
    # CR-19: a new tenant starts with its kind's modules (#1475, #1478).
    db.add_all(
        TenantModule(tenant_id=tenant.id, module_code=module.value)
        for module in sorted(DEFAULTS[kind.value], key=lambda c: c.value)
    )
    from app.kernel.contracts.mdm import TenantCreated
    from app.kernel.events import publish

    publish(TenantCreated(tenant_id=tenant.id, name=tenant.name), db)
    db.commit()
    # Cache wissen zodat de nieuwe tenant meteen resolvet (#546) — ná de commit,
    # anders vult een gelijktijdig verzoek de cache met de oude toestand.
    invalidate_tenant_codes()
    return tenant


def _check_code(db, code: str) -> str:
    """A code in the slug form that no tenant carries yet (CR-20 C4.5: a code
    names a site; an organisation has none)."""
    from app.domains.mdm.models import Tenant

    code = (code or "").strip().lower()
    if not _CODE.fullmatch(code):
        raise TenantFout("Een geldige code (kleine letters, cijfers, streepjes) is verplicht.")
    if db.query(Tenant).filter(Tenant.code == code).first():
        raise TenantFout("Die code bestaat al.")
    # #1951: a code is a path prefix, and the prefix wins over the route — a
    # tenant `admin` would take the back office from every tenant. The reserved
    # words come from the route table itself (`kernel.route_table`).
    from app.kernel.route_table import colliding

    if colliding([code]):
        raise TenantFout(
            "De code %(code)s is een adres van de toepassing zelf (/%(code)s/…). "
            "Kies een andere code." % {"code": code}
        )
    return code


def _checked_name(name: str | None) -> str:
    """The name of a new organisation, refused before anything is written."""
    name = (name or "").strip()
    if not name:
        raise TenantFout("Geef de nieuwe organisatie een naam.")
    if len(name) > 255:
        raise TenantFout("De naam van de organisatie is te lang (maximaal 255 tekens).")
    return name


def _new_party(db, name: str):
    """An organisation of this (checked) name, flushed — the commit is the caller's."""
    from app.domains.mdm.models import Organization

    org = Organization(name=name, is_active=True)
    db.add(org)
    db.flush()
    return org


def create_organization(db, *, name: str):
    """Create an organisation — a party, no code (CR-20 F6, C4.7). It becomes
    an account when a tenant names it as one. Legal form, identifiers, address
    and bank account are filled in on the organisation screen it lands on.
    Commits."""
    from app.domains.mdm.models import Organization

    name = (name or "").strip()
    if not name:
        raise TenantFout("Een naam is verplicht.")
    org = Organization(name=name, is_active=True)
    db.add(org)
    db.commit()
    return org


def set_modules(db, tenant_id: int, codes) -> None:
    """Switch a tenant's modules to exactly these (CR-19 §C4.5, #1478).

    Refused, before anything changes, when a module lacks one it depends on:
    the Design Studio needs activities (a design is made for one), payments
    need activities or membership (there must be something to pay for). The
    refusal names the missing module, in the registry's words. Switching off
    deletes nothing — the module's data stays, unreachable until it is back on.
    Commits, and clears the cached sets so the next request reads the new one.
    """
    from app.domains.mdm.tenant_lookup import invalidate_tenant_codes

    chosen = _checked_modules(codes)
    _write_modules(db, tenant_id, chosen)
    db.commit()
    invalidate_tenant_codes()


def _dutch_enumeration(labels: list[str]) -> str:
    """The labels as Dutch writes a list of alternatives: commas between all but
    the last two, " of " before the last ("A", "A of B", "A, B of C") (#1888)."""
    if len(labels) < 2:
        return "".join(labels)
    return f"{', '.join(labels[:-1])} of {labels[-1]}"


def _checked_modules(codes) -> set:
    """The module codes as members, refused before anything changes when one is
    unknown or lacks a module it depends on (`ModuleRefused`, naming it)."""
    from app.kernel.modules import REGISTRY, ModuleCode

    try:
        chosen = {ModuleCode(str(code)) for code in codes}
    except ValueError:
        raise TenantFout("Onbekende module.") from None
    for code in sorted(chosen, key=lambda c: c.value):
        for alternatives in REGISTRY[code].depends_on:
            if not chosen & set(alternatives):
                needed = _dutch_enumeration([REGISTRY[a].label for a in alternatives])
                raise ModuleRefused(f"{REGISTRY[code].label} heeft {needed} nodig.", code)
    return chosen


def _write_modules(db, tenant_id: int, chosen) -> None:
    """Make the stored set exactly `chosen`. Does not commit."""
    from app.domains.mdm.models import TenantModule
    from app.kernel.modules import ModuleCode

    stored = {
        row.module_code: row
        for row in db.query(TenantModule).filter(TenantModule.tenant_id == tenant_id).all()
    }
    for code, row in stored.items():
        if code not in {c.value for c in chosen}:
            db.delete(row)
    for code in chosen - {ModuleCode(c) for c in stored}:
        db.add(TenantModule(tenant_id=tenant_id, module_code=code.value))


def save_tenant(
    db,
    tenant_id: int,
    form: Mapping,
    *,
    known: Iterable[str],
    secret: Iterable[str],
    modules: Iterable[str] | None,
    kind: str | None = None,
    account: str | None = None,
    site_organization: str | None = None,
    site_name: str | None = None,
    actor: str | None = None,
) -> None:
    """The tenant editor's one Opslaan (#1498): the module set and the settings
    in ONE transaction. Both are checked before anything is written — a refused
    dependency (`ModuleRefused`) or an invalid value (`OngeldigeInstelling`)
    saves nothing. Switching a module off deletes nothing: its settings stay,
    as they are on the form. `modules=None` leaves the module set as it is.
    Commits, and clears the cached module sets.

    #1533: `kind` changes the tenant's kind in the same transaction, checked
    first like the rest (`_checked_kind`); None leaves it as it is. The modules
    do not follow a new kind — the kind sets the starting modules at creation
    only, and what the tenant has switched on since is its own.

    `account` moves the tenant under another account, the same way: its id as
    text, None to leave it. Every tenant has an account since CR-20 (F1), so
    "none" is no longer a choice. Modules and data stay."""
    from app.domains.mdm.models import Tenant
    from app.domains.mdm.tenant_lookup import invalidate_tenant_codes

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise TenantFout("Onbekende tenant.")
    new_kind = _checked_kind(db, tenant_id, kind) if kind is not None else None
    account_after = (
        _checked_account(db, tenant_id, account) if account is not None else tenant.account_id
    )
    # #1550: checked against the account the tenant will have after this save.
    site_org = _checked_site_organization(db, tenant_id, site_organization, account_after)
    new_site_name = _checked_site_name(site_name) if site_name is not None else None
    chosen = _checked_modules(modules) if modules is not None else None
    _write_settings(db, tenant_id, form, known=known, secret=secret)
    if chosen is not None:
        _write_modules(db, tenant_id, chosen)
    if new_kind is not None:
        _write_kind(db, tenant, new_kind, actor=actor)
    _write_reference(db, tenant, "account_id", "account", account_after, actor=actor)
    _write_reference(db, tenant, "organization_id", "site organisation", site_org, actor=actor)
    if site_name is not None:
        tenant.site_name = new_site_name
    db.commit()
    invalidate_tenant_codes()


def _checked_kind(db, tenant_id: int, kind: str) -> TenantKind:
    """The kind a tenant may be given (#1533), refused before anything is
    written: one of `CREATABLE_TENANT_KINDS`. The platform's kind is fixed —
    there is one platform, and it is never an association or a company."""
    from app.domains.mdm.models import Tenant

    tenant = db.get(Tenant, tenant_id)
    if tenant is None or tenant.is_platform:
        raise TenantFout("Het type van het platform ligt vast.")
    try:
        chosen = TenantKind(kind)
    except ValueError:
        raise TenantFout("Kies het type: vereniging of bedrijf.") from None
    if chosen not in CREATABLE_TENANT_KINDS:
        raise TenantFout("Kies het type: vereniging of bedrijf.")
    return chosen


def _checked_account(db, tenant_id: int | None, account: str) -> int:
    """The account a tenant may hang under (#1533, CR-20): an active
    organisation, refused before anything is written. On every tenant, the
    platform too (#1542): the account grants nothing — no role is read from it —
    and the platform stays the platform."""
    from app.domains.mdm.models import Organization

    chosen = db.get(Organization, int(account)) if account.isdigit() else None
    if chosen is None or chosen.deleted_at is not None or not chosen.is_active:
        raise TenantFout("Kies een actief account.")
    return chosen.id


def _named_by_another_account(
    db, organization_id: int, account_id: int, tenant_id: int | None = None
) -> bool:
    """Does a tenant of another account name this organisation, as its account
    or as the organisation it shows? Koen: no data across accounts (#1550). The
    tenant being saved does not count: it is the one moving."""
    from app.domains.mdm.models import Tenant

    query = db.query(Tenant.id).filter(
        Tenant.account_id != account_id,
        (Tenant.account_id == organization_id) | (Tenant.organization_id == organization_id),
    )
    if tenant_id is not None:
        query = query.filter(Tenant.id != tenant_id)
    return query.first() is not None


def _checked_site_organization(
    db, tenant_id: int | None, value: str | None, account_id: int
) -> int:
    """The organisation behind the tenant's site after this save (#1550): the
    account, or another organisation of that account — never one that a tenant
    of another account names (Koen: no data across accounts). Since CR-20 an
    organisation carries no account of its own (CR-26 gives it one); what ties
    it to an account is the tenants that name it.

    `value` is what the form sent: "" for the account itself, an id, or None
    when the form sent nothing; then the current choice stays, unless the
    account moves away from under it — a choice outside the new account falls
    back to the account (and is logged by `_write_reference`).
    """
    from app.domains.mdm.models import Organization, Tenant

    tenant = db.get(Tenant, tenant_id) if tenant_id is not None else None
    if value is None:
        chosen = tenant.organization_id if tenant is not None else account_id
    elif value == "":
        chosen = account_id
    elif value.isdigit():
        chosen = int(value)
    else:
        raise TenantFout("Kies een organisatie van het eigen account.")
    if chosen == account_id:
        return chosen
    other = db.get(Organization, chosen)
    within = (
        other is not None
        and other.deleted_at is None
        and not _named_by_another_account(db, chosen, account_id, tenant_id)
    )
    if within:
        return chosen
    if value is None:
        return account_id
    raise TenantFout("Kies een organisatie van het eigen account.")


def _checked_site_name(value: str) -> str | None:
    """The name the tenant's site shows (#1546); empty clears it, so the site
    shows its organisation's name again."""
    name = (value or "").strip()
    if len(name) > 255:
        raise TenantFout("De naam van de site is te lang (maximaal 255 tekens).")
    return name or None


def _write_reference(db, tenant, column: str, what: str, chosen: int, *, actor: str | None) -> None:
    """Point the tenant at an organisation — its account or the one its site
    shows; a change is logged (#1533, #1550): there is no history table for
    tenants, so the application log records who, which tenant, old and new."""
    old = getattr(tenant, column)
    if old == chosen:
        return
    setattr(tenant, column, chosen)
    logger.info(
        "tenant %s changed: tenant=%s code=%s %s -> %s by %s",
        what,
        tenant.id,
        tenant.code,
        old,
        chosen,
        actor or "unknown",
    )


def _write_kind(db, tenant, kind: TenantKind, *, actor: str | None) -> None:
    """Give the tenant its kind; a change is logged (#1533). There is no history
    table for tenants or tenant settings, so the application log is where the
    change is recorded: who, which tenant, the old and the new kind."""
    old = tenant.kind
    if old is kind:
        return
    tenant.kind = kind
    logger.info(
        "tenant kind changed: tenant=%s code=%s %s -> %s by %s",
        tenant.id,
        tenant.code,
        old.value if old is not None else None,
        kind.value,
        actor or "unknown",
    )


# #797: welke instellingen een getal moeten zijn. Een tenant-instelling is door
# mensen te bewerken data die op élke publieke pagina gelezen wordt, dus een
# onleesbare waarde is geen lokaal probleem: `17,5` bij `membership_price_half`
# gaf een `decimal.InvalidOperation` in `tenant_membership_config`, en die hangt
# onder `site_context` — dus 500 op de homepage.
BEDRAG_SLEUTELS = ("membership_price_full", "membership_price_half")
GEHEEL_SLEUTELS = ("payment_term_days", "max_item_quantity", "max_registrations_per_email")


class OngeldigeInstelling(TenantFout):
    """Eén of meer velden bevatten geen bruikbaar getal.

    Draagt de meldingen per sleutel mee, zodat het scherm kan zeggen wélk veld het
    is in plaats van "er ging iets mis".
    """

    def __init__(self, fouten: dict[str, str]):
        self.fouten = fouten
        super().__init__("; ".join(f"{k}: {v}" for k, v in fouten.items()))


def _als_bedrag(ruw: str) -> str:
    """`17,50` → `17.50`. De komma wordt AANVAARD, niet geweigerd.

    De hele applicatie toont bedragen als `€ 17,50`; iemand die dat overtypt doet
    wat de interface hem voordoet. Hem corrigeren voor de notatie van zijn eigen
    taal is de verkeerde kant op — dus normaliseren we naar het punt dat `Decimal`
    verwacht, en slaan we die genormaliseerde vorm op.
    """
    from decimal import Decimal, InvalidOperation

    genormaliseerd = ruw.replace(",", ".")
    try:
        waarde = Decimal(genormaliseerd)
    except InvalidOperation:
        raise ValueError("Geef een bedrag, bv. 17,50.")
    if waarde < 0:
        raise ValueError("Een bedrag kan niet negatief zijn.")
    return genormaliseerd


def _als_geheel(ruw: str) -> str:
    if not ruw.lstrip("+").isdigit():
        raise ValueError("Geef een geheel getal, bv. 7.")
    return str(int(ruw))


def update_tenant_settings(
    db, tenant_id: int, form: Mapping, *, known: Iterable[str], secret: Iterable[str]
) -> None:
    """Schrijf de instellingen van één tenant weg.

    Twee soorten sleutels, met verschillende semantiek:

    - **gewone sleutels**: wat in het formulier staat, is de nieuwe waarde; leeg
      betekent leeg.
    - **geheime sleutels**: leeg laten = **ongewijzigd**. Ze worden nooit
      teruggetoond, dus een leeg veld betekent "ik heb niets ingetypt", niet "wis
      dit". Wissen gebeurt expliciet met `<sleutel>_wissen`. Zonder die regel
      wist elke opslag van een ander veld stilzwijgend de Mollie-key.

    Getalvelden worden eerst gecontroleerd (#797). ALLE velden eerst, en pas daarna
    schrijven: anders staat de helft van het formulier in de databank en de andere
    helft niet, en dan is de toestand na een tikfout onduidelijker dan ervoor.
    """
    _write_settings(db, tenant_id, form, known=known, secret=secret)
    db.commit()


def _write_settings(
    db, tenant_id: int, form: Mapping, *, known: Iterable[str], secret: Iterable[str]
) -> None:
    """Check every value, then write them — `update_tenant_settings` without the
    commit, so `save_tenant` can write the modules in the same transaction."""
    from app.kernel.tenant_config import (
        SITE_ACCENT_COLOR_KEY,
        SITE_BRAND_COLOR_KEY,
        SITE_HEADER_COLOR_KEY,
        accent_color_problem,
        brand_color_problem,
        header_color_problem,
        set_setting,
    )

    # A colour is refused, never repaired: it goes into a style attribute, and
    # text stands on it or is drawn in it (#992, #1622).
    colour_rules = {
        SITE_HEADER_COLOR_KEY: header_color_problem,
        SITE_BRAND_COLOR_KEY: brand_color_problem,
        SITE_ACCENT_COLOR_KEY: accent_color_problem,
    }

    def _tekst(key: str) -> str:
        waarde = form.get(key)
        return waarde.strip() if isinstance(waarde, str) else ""

    schoon: dict[str, str | None] = {}
    fouten: dict[str, str] = {}
    for key in known:
        ruw = _tekst(key)
        if not ruw:
            schoon[key] = None  # leeg = terug naar de .env-default
            continue
        try:
            if key in BEDRAG_SLEUTELS:
                schoon[key] = _als_bedrag(ruw)
            elif key in GEHEEL_SLEUTELS:
                schoon[key] = _als_geheel(ruw)
            elif key in colour_rules:
                probleem = colour_rules[key](ruw)
                if probleem:
                    raise ValueError(probleem)
                schoon[key] = ruw.lower()
            else:
                schoon[key] = ruw
        except ValueError as fout:
            fouten[key] = str(fout)
    if fouten:
        raise OngeldigeInstelling(fouten)

    for key, waarde in schoon.items():
        set_setting(db, key, waarde, tenant_id=tenant_id)

    for key in secret:
        if form.get(f"{key}_wissen"):
            set_setting(db, key, None, tenant_id=tenant_id)
        elif _tekst(key):
            set_setting(db, key, _tekst(key), secret=True, tenant_id=tenant_id)


def list_units(db, *, alleen_actief: bool = False):
    """The tenants that are no platform — the sites with a path prefix — by id."""
    from app.domains.mdm.models import Tenant

    query = db.query(Tenant).filter(Tenant.kind != TenantKind.PLATFORM)
    if alleen_actief:
        query = query.filter(Tenant.is_active.is_(True))
    return query.order_by(Tenant.id).all()


def tenants(db):
    """Every tenant, the platform included, by id (CR-20 F6)."""
    from app.domains.mdm.models import Tenant

    return db.query(Tenant).order_by(Tenant.id).all()


def tenant(db, tenant_id: int):
    """One tenant, or None (CR-20 F6)."""
    from app.domains.mdm.models import Tenant

    return db.get(Tenant, tenant_id)


def tenant_by_code(db, code: str):
    """The tenant with this code, or None (CR-20 F6)."""
    from app.domains.mdm.models import Tenant

    return db.query(Tenant).filter(Tenant.code == (code or "").strip().lower()).first()


def tenants_of_account(db, organization_id: int):
    """The tenants that name this organisation as their account, by id
    (CR-20 F6, R6: the door to an account workspace is this query)."""
    from app.domains.mdm.models import Tenant

    return db.query(Tenant).filter(Tenant.account_id == organization_id).order_by(Tenant.id).all()


def is_account(db, organization_id: int) -> bool:
    """Is this organisation an account? Yes when a tenant names it as its
    account — the role is read from that fact, never stored (CR-20 C4.2)."""
    from app.domains.mdm.models import Tenant

    return db.query(Tenant.id).filter(Tenant.account_id == organization_id).first() is not None


def accounts(db):
    """The active organisations that tenants name as their account, by id
    (CR-20 F6): the accounts a tenant can be moved under."""
    from app.domains.mdm.models import Organization, Tenant

    named = db.query(Tenant.account_id)
    return (
        db.query(Organization)
        .filter(Organization.id.in_(named), Organization.is_active.is_(True))
        .order_by(Organization.id)
        .all()
    )


def active_sites_by_account(db):
    """The active sites, grouped by the active account they belong to (#1525,
    #1543): the tenants, the platform among them under its account (#1542).

    A list of ``(account, sites)``: ``account`` an organisation, or None for the
    tenants whose account is inactive — a live tenant must not vanish from the
    list. Since CR-20 every tenant has an account (F1); until then a tenant
    without one stood in the None group and the platform without one was left
    out — measured on UAT and PROD on 18 October 2026, every tenant and the
    platform had one. The groups follow the account's name, the None group last;
    the sites within a group are sorted by the caller, which knows their display
    names.
    """
    from app.domains.mdm.models import Organization, Tenant

    groups: dict[int | None, list] = {}
    active = db.query(Tenant).filter(Tenant.is_active.is_(True)).order_by(Tenant.id).all()
    account_ids = {t.account_id for t in active}
    live = {
        a.id: a
        for a in db.query(Organization).filter(
            Organization.id.in_(account_ids), Organization.is_active.is_(True)
        )
    }
    for site in active:
        groups.setdefault(site.account_id if site.account_id in live else None, []).append(site)
    named = sorted(
        ((live[k], sites) for k, sites in groups.items() if k is not None),
        key=lambda group: (group[0].name.casefold(), group[0].id),
    )
    return named + ([(None, groups[None])] if None in groups else [])


def circle_organization(db):
    """The organisation a circle hangs on: the one the current tenant shows
    (CR-20 F11). Until CR-20 every circle hung on the PLATFORM row; under the
    party model a department's persons and the platform's party lie in two
    accounts, so each tenant's circle hangs on its own shown party. While the
    tenant has none, nobody can be put in a circle — refused here, in the words
    the two circle screens always gave."""
    from app.domains.mdm.models import MasterDataError
    from app.i18n import _

    organization = shown_organization(db)
    if organization is None:
        raise MasterDataError(_("Er is nog geen organisatie ingesteld."))
    return organization


def shown_organization(db):
    """The organisation the current tenant shows (#1550, CR-20), or None when it
    has none that is live."""
    from app.domains.mdm.models import Organization
    from app.kernel.tenant_config import site_organization_id

    organization = db.get(Organization, site_organization_id(db))
    if organization is None or organization.deleted_at is not None:
        return None
    return organization


def platform_tenant(db):
    """The platform tenant, or None if this database has none (#854).

    Separate from ``list_units`` on purpose: the platform is not a department
    and must not appear where afdelingen are listed — the landing page of the
    platform lists its afdelingen, and the platform itself is not one of them.
    """
    from app.domains.mdm.models import Tenant

    return db.query(Tenant).filter(Tenant.kind == TenantKind.PLATFORM).order_by(Tenant.id).first()


def list_manageable_tenants(db, *, alleen_actief: bool = False):
    """What /admin/tenants may configure: the platform first, then the units (#854).

    The platform carries the same settings as any tenant — that is the whole point of
    making it one — so it needs the same editor. It leads the list because it is the
    thing you are standing in when you are on a platform host.
    """
    platform = platform_tenant(db)
    units = list_units(db, alleen_actief=alleen_actief)
    if platform is None or (alleen_actief and not platform.is_active):
        return units
    return [platform] + units


def secrets_gezet(db, tenant_id: int, keys) -> dict[str, bool]:
    """Per geheime sleutel: staat er een waarde? (niet wélke — die wordt nooit
    teruggetoond)

    Het scherm heeft dit nodig om "ingesteld" of "nog niet ingesteld" te tonen
    naast een veld dat leeg blijft. Eén query voor alle sleutels samen: het waren
    er twee per sleutel.
    """
    from app.kernel.tenant_config import TenantSetting

    gezet = {
        rij.key
        for rij in db.query(TenantSetting.key)
        .filter(
            TenantSetting.tenant_id == tenant_id,
            TenantSetting.key.in_(list(keys)),
            TenantSetting.value_encrypted.isnot(None),
        )
        .all()
    }
    return {key: key in gezet for key in keys}


def organizations_of_account(db, account_id: int) -> list[dict]:
    """The organisations a site of this account may show (#1550, CR-20): the
    account first, then the organisations that the account's tenants show, by
    name. Plain dicts for a screen (`test_layer_gate`). Until CR-26 gives an
    organisation an account of its own, what ties it to an account is the
    tenants that name it."""
    from app.domains.mdm.models import Organization, Tenant

    shown = db.query(Tenant.organization_id).filter(Tenant.account_id == account_id)
    rows = (
        db.query(Organization)
        .filter(
            Organization.deleted_at.is_(None),
            (Organization.id == account_id) | Organization.id.in_(shown),
        )
        .all()
    )
    rows.sort(key=lambda o: (o.id != account_id, (o.name or "").casefold(), o.id))
    return [{"id": o.id, "name": o.name} for o in rows]
