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
    time_zone: str = "",
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
    checked_site_name = _checked_site_name(site_name)
    checked_time_zone = _checked_time_zone(time_zone) if (time_zone or "").strip() else None
    if new_account is None:
        account = _checked_account(db, str(account_id) if account_id is not None else "")
        if new_shown is None:
            shown = _checked_site_organization(
                db, None, str(organization_id) if organization_id else "", account
            )
    elif new_shown is None and organization_id:
        # A new account owns nothing yet: it may show an organisation that is
        # free (CR-26), never one of another account.
        other = _organization(db, organization_id)
        if other is None or other.deleted_at is not None or not _free(db, other):
            raise TenantFout("Kies een organisatie van het eigen account.")
    if new_account is not None:
        account = _new_party(db, new_account)
        if new_shown is None:
            shown = other if organization_id else account
    if new_shown is not None:
        shown = _new_party(db, new_shown)
    # CR-26: the account is its own account, and what the site shows is the
    # account's — a free organisation moves along (`_move_to_account`).
    _move_to_account(db, account, account.party_id)
    _move_to_account(db, shown, account.party_id)
    tenant = Tenant(
        code=code,
        kind=kind,
        account_id=account.party_id,
        organization_id=shown.id,
        site_name=checked_site_name,
        **({"time_zone": checked_time_zone} if checked_time_zone else {}),
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

    org = Organization(name=name, is_active=True, account_id=_platform_account(db))
    db.add(org)
    db.flush()
    return org


def current_account_id(db) -> int | None:
    """The account of the current tenant — the party it belongs to (CR-26 F2)."""
    from app.domains.mdm.models import Tenant
    from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id

    tenant = db.get(Tenant, current_tenant_id.get() or DEFAULT_TENANT_ID)
    return tenant.account_id if tenant is not None else None


def create_organization(db, *, name: str, account_id: int | None = None):
    """Create an organisation — a party, no code (CR-20 F6, C4.7). It becomes
    an account when a tenant names it as one. Until a tenant names it, it is
    free in the platform's account (CR-26 F1), whatever tenant made it — unless a
    department makes it (`account_id`: the department's account, F9), so that the
    department that made it sees it. Legal form, identifiers, address and bank
    account are filled in on the organisation screen it lands on. Commits."""
    from app.domains.mdm.models import Organization

    name = (name or "").strip()
    if not name:
        raise TenantFout("Een naam is verplicht.")
    org = Organization(name=name, is_active=True, account_id=account_id or _platform_account(db))
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
    time_zone: str | None = None,
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

    `account` is what a form sent as the account, None when it sent none: an
    existing tenant never changes its account (CR-26; Koen, 19 October 2026),
    so anything but its own is refused. Only Tenants › Nieuw chooses it."""
    from app.domains.mdm.models import Tenant
    from app.domains.mdm.tenant_lookup import invalidate_tenant_codes

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise TenantFout("Onbekende tenant.")
    new_kind = _checked_kind(db, tenant_id, kind) if kind is not None else None
    account_org = _account_organization(db, tenant)
    if account is not None and account != str(account_org.id):
        # CR-26 C5: its parties belong to its account. Koen, 19 October 2026, to
        # whether a tenant may still move while it is empty: "1" — never.
        raise TenantFout("Het account van een bestaande tenant verandert niet.")
    site_org = _checked_site_organization(db, tenant_id, site_organization, account_org)
    new_site_name = _checked_site_name(site_name) if site_name is not None else None
    new_time_zone = _checked_time_zone(time_zone) if time_zone is not None else None
    chosen = _checked_modules(modules) if modules is not None else None
    _write_settings(db, tenant_id, form, known=known, secret=secret)
    if chosen is not None:
        _write_modules(db, tenant_id, chosen)
    if new_kind is not None:
        _write_kind(db, tenant, new_kind, actor=actor)
    _move_to_account(db, site_org, account_org.party_id)
    _write_reference(db, tenant, "organization_id", "site organisation", site_org.id, actor=actor)
    if site_name is not None:
        tenant.site_name = new_site_name
    if new_time_zone is not None:
        tenant.time_zone = new_time_zone
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


def _checked_account(db, account: str):
    """The organisation that is the account a new tenant hangs under (#1533,
    CR-20): an active organisation, refused before anything is written. The
    account grants nothing — no role is read from it.

    Since CR-26 an organisation belongs to an account (`account_id`, its
    party's): it can be the account only when it is one already, or when it is
    free (`_free`) and becomes one — never when it belongs to another account,
    because its data would then be in two."""
    chosen = _organization(db, int(account)) if account.isdigit() else None
    if chosen is None or chosen.deleted_at is not None or not chosen.is_active:
        raise TenantFout("Kies een actief account.")
    if chosen.account_id != chosen.party_id and not _free(db, chosen):
        raise TenantFout("Kies een actief account.")
    return chosen


def _organization(db, organization_id: int | None):
    """One organisation, whatever its account: the tenant screens are the
    operator's, on the platform, and see every account (CR-26 C3)."""
    from app.domains.mdm.models import Organization

    if not organization_id:
        return None
    return (
        db.query(Organization)
        .execution_options(include_all_tenants=True)
        .filter(Organization.id == organization_id)
        .first()
    )


def _account_organization(db, tenant):
    """The organisation whose party is the tenant's account (C4.9)."""
    from app.domains.mdm.models import Organization

    return (
        db.query(Organization)
        .execution_options(include_all_tenants=True)
        .filter(Organization.party_id == tenant.account_id)
        .one()
    )


def _platform_account(db) -> int | None:
    platform = platform_tenant(db)
    return platform.account_id if platform is not None else None


def _free(db, organization, tenant_id: int | None = None) -> bool:
    """Is this organisation free to join an account (CR-26)? It is when it lies
    in the platform's account — where an organisation the operator made in
    Organisaties lands — is no account itself, and no tenant names it, as
    account or as the one it shows. The tenant being saved does not count."""
    from app.domains.mdm.models import Tenant

    if organization.account_id != _platform_account(db):
        return False
    if organization.account_id == organization.party_id:
        return False
    named = db.query(Tenant.id).filter(
        (Tenant.account_id == organization.party_id) | (Tenant.organization_id == organization.id)
    )
    if tenant_id is not None:
        named = named.filter(Tenant.id != tenant_id)
    return named.first() is None


def _move_to_account(db, organization, account: int) -> None:
    """Give an organisation, its party and what hangs on it — addresses,
    contacts, bank accounts, identifications, their history — this account
    (CR-26 F1, F3). Nothing
    when it has it already. Read across accounts: the rows are of another
    account than the current tenant's, which the filter would hide."""
    from app.domains.mdm.models import (
        Address,
        AddressHistory,
        BankAccount,
        ContactDetail,
        ContactDetailHistory,
        Party,
        PartyIdentification,
    )

    if organization.account_id == account:
        return
    for model in (
        Address,
        ContactDetail,
        BankAccount,
        PartyIdentification,
        AddressHistory,
        ContactDetailHistory,
    ):
        rows = (
            db.query(model)
            .execution_options(include_all_tenants=True)
            .filter(model.party_id == organization.party_id)
        )
        for row in rows:
            row.account_id = account
    party = (
        db.query(Party)
        .execution_options(include_all_tenants=True)
        .filter(Party.id == organization.party_id)
        .one()
    )
    party.account_id = account
    organization.account_id = account


def _checked_site_organization(db, tenant_id: int | None, value: str | None, account):
    """The organisation behind the tenant's site after this save (#1550): the
    account, or another organisation of that account — never one of another
    account (Koen: no data across accounts). Since CR-26 an organisation
    belongs to an account (`account_id`); a free one (`_free`) may join it.

    `value` is what the form sent: "" for the account itself, an id, or None
    when the form sent nothing; then the current choice stays, unless the
    account moves away from under it — a choice outside the new account falls
    back to the account (and is logged by `_write_reference`).
    """
    from app.domains.mdm.models import Tenant

    tenant = db.get(Tenant, tenant_id) if tenant_id is not None else None
    if value is None:
        chosen = tenant.organization_id if tenant is not None else account.id
    elif value == "":
        chosen = account.id
    elif value.isdigit():
        chosen = int(value)
    else:
        raise TenantFout("Kies een organisatie van het eigen account.")
    if chosen == account.id:
        return account
    other = _organization(db, chosen)
    within = (
        other is not None
        and other.deleted_at is None
        and (other.account_id == account.party_id or _free(db, other, tenant_id))
    )
    if within:
        return other
    if value is None:
        return account
    raise TenantFout("Kies een organisatie van het eigen account.")


def _checked_site_name(value: str) -> str | None:
    """The name the tenant's site shows (#1546); empty clears it, so the site
    shows its organisation's name again."""
    name = (value or "").strip()
    if len(name) > 255:
        raise TenantFout("De naam van de site is te lang (maximaal 255 tekens).")
    return name or None


def _checked_time_zone(value: str) -> str:
    """The time zone a tenant lives by (#2156): a name of the IANA time zone database
    (`Europe/Brussels`), checked here because a CHECK cannot hold the list. The day of
    a tenant is decided from it everywhere (`kernel.clock`, `mdm.tenant_today()`), so a
    name the database does not know is refused before anything is written."""
    from zoneinfo import available_timezones

    name = (value or "").strip()
    if name not in available_timezones():
        raise TenantFout(
            "Dit is geen tijdzone uit de IANA-lijst. Bv. Europe/Brussels of America/New_York."
        )
    return name


def _write_reference(db, tenant, column: str, what: str, chosen: int, *, actor: str | None) -> None:
    """Point the tenant at the organisation its site shows; a change is logged
    (#1550): there is no history table for tenants, so the application log
    records who, which tenant, old and new."""
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

    party = _organization_party(db, organization_id)
    if party is None:
        return []
    return db.query(Tenant).filter(Tenant.account_id == party).order_by(Tenant.id).all()


def tenants_naming_each(db) -> dict[int, list]:
    """Per organisation id, the tenants that name its party — as the
    organisation they show or as their account — by id: what makes a party "in
    use" (CR-20 C4.4), the one place that rule stands. Nothing else does: a
    relation goes with the party, an order keeps its buyer copy. The list of
    Organisaties counts from it, the delete refuses from it."""
    from app.domains.mdm.models import Organization, Tenant

    organization_of_party = dict(
        db.query(Organization.party_id, Organization.id)
        .execution_options(include_all_tenants=True)
        .all()
    )
    naming: dict[int, list] = {}
    for tenant in db.query(Tenant).order_by(Tenant.id):
        named = {tenant.organization_id, organization_of_party.get(tenant.account_id)}
        for organization_id in named - {None}:
            naming.setdefault(organization_id, []).append(tenant)
    return naming


def tenants_naming(db, organization_id: int) -> list:
    """The tenants that name this organisation's party (`tenants_naming_each`)."""
    return tenants_naming_each(db).get(organization_id, [])


def delete_organization(db, organization_id: int, *, actor: str | None = None) -> None:
    """Delete an organisation (CR-20 F6, C4.4). A party a tenant names refuses,
    naming those tenants. Otherwise the organisation goes softly with its party
    row and its details — addresses, contacts, bank accounts, identifications,
    relations — in one transaction, with a history row where the table has one.
    No cascade through the keys: this decides, the keys only guard. Commits."""
    from app.domains.mdm.history import snapshot_address, snapshot_contact_detail
    from app.domains.mdm.models import (
        Address,
        BankAccount,
        ContactDetail,
        Party,
        PartyIdentification,
        PartyRelationship,
    )
    from app.i18n import _
    from app.kernel.tenant_config import tenant_display_name
    from app.soft_delete import soft_delete

    organization = _organization(db, organization_id)
    if organization is None:
        raise OngeldigeInstelling({"": _("Onbekende organisatie.")})
    naming = tenants_naming(db, organization_id)
    if naming:
        names = ", ".join(tenant_display_name(db, t.id) for t in naming)
        raise OngeldigeInstelling(
            {"": _("Deze organisatie is in gebruik door %(tenants)s.") % {"tenants": names}}
        )

    def rows(model, column, value):
        return (
            db.query(model)
            .execution_options(include_all_tenants=True)
            .filter(column == value)
            .all()
        )

    history = {"operation": "delete", "action": "organization_deleted", "source": "admin_manual"}
    for address in rows(Address, Address.party_id, organization.party_id):
        snapshot_address(db, address, actor=actor, **history)
        soft_delete(address)
    for contact in rows(ContactDetail, ContactDetail.party_id, organization.party_id):
        snapshot_contact_detail(db, contact, actor=actor, **history)
        soft_delete(contact)
    for model in (BankAccount, PartyIdentification):
        for row in rows(model, model.party_id, organization.party_id):
            soft_delete(row)
    # A relation with the party on either end: the people in its circle and the
    # people who act for it (CR-26 F4). `rows` takes one column, so two reads.
    for column in (PartyRelationship.to_party_id, PartyRelationship.from_party_id):
        for relation in rows(PartyRelationship, column, organization.party_id):
            soft_delete(relation)
    for party in rows(Party, Party.id, organization.party_id):
        soft_delete(party)
    soft_delete(organization)
    db.commit()


def _organization_party(db, organization_id: int) -> int | None:
    organization = _organization(db, organization_id)
    return organization.party_id if organization is not None else None


def is_account(db, organization_id: int) -> bool:
    """Is this organisation an account? Yes when a tenant names it as its
    account — the role is read from that fact, never stored (CR-20 C4.2)."""
    from app.domains.mdm.models import Tenant

    party = _organization_party(db, organization_id)
    return (
        party is not None
        and db.query(Tenant.id).filter(Tenant.account_id == party).first() is not None
    )


def accounts(db):
    """The active organisations that tenants name as their account, by id
    (CR-20 F6): the accounts a tenant can be moved under."""
    from app.domains.mdm.models import Organization, Tenant

    named = db.query(Tenant.account_id)
    return (
        db.query(Organization)
        .execution_options(include_all_tenants=True)
        .filter(Organization.party_id.in_(named), Organization.is_active.is_(True))
        .order_by(Organization.id)
        .all()
    )


def active_sites_by_account(db):
    """The active sites, grouped by the active account they belong to (#1525,
    #1543): the tenants, the platform among them under its account (#1542).

    A list of ``(account, sites)``: ``account`` an organisation, or None for the
    tenants whose account is inactive — a live tenant must not vanish from the
    list. Since CR-20 every tenant has an account (F1); until then a tenant
    without one stood in the None group — measured on UAT and PROD on 18
    October 2026, every tenant and the platform had one. The platform is listed
    only under a live account other than its own party: without an account it
    was left out before CR-20, and the migration made it its own account (R4,
    the same sites per account as before). The groups follow the account's name, the None group last;
    the sites within a group are sorted by the caller, which knows their display
    names.
    """
    from app.domains.mdm.models import Organization, Tenant

    groups: dict[int | None, list] = {}
    active = db.query(Tenant).filter(Tenant.is_active.is_(True)).order_by(Tenant.id).all()
    account_ids = {t.account_id for t in active}
    # Every account's: the placeholder lists the sites of all accounts (CR-26).
    every = db.query(Organization).execution_options(include_all_tenants=True)
    live = {
        a.party_id: a
        for a in every.filter(
            Organization.party_id.in_(account_ids), Organization.is_active.is_(True)
        )
    }
    shown_party = dict(
        every.with_entities(Organization.id, Organization.party_id).filter(
            Organization.id.in_({t.organization_id for t in active})
        )
    )
    for site in active:
        if site.is_platform and (
            site.account_id not in live or site.account_id == shown_party.get(site.organization_id)
        ):
            continue
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
    account first, then the other organisations of the account, by name.
    `account_id` is the account's organisation. Plain dicts for a screen
    (`test_layer_gate`). Since CR-26 an organisation belongs to an account
    (`account_id`, its party's)."""
    from app.domains.mdm.models import Organization

    party = _organization_party(db, account_id)
    rows = (
        db.query(Organization)
        .execution_options(include_all_tenants=True)
        .filter(Organization.deleted_at.is_(None), Organization.account_id == party)
        .all()
        if party is not None
        else []
    )
    rows.sort(key=lambda o: (o.id != account_id, (o.name or "").casefold(), o.id))
    return [{"id": o.id, "name": o.name} for o in rows]


def account_organization_id(db, tenant) -> int:
    """The id of the organisation that is this tenant's account — what the
    tenant screens show and send (CR-26 C4.9: the tenant stores its party)."""
    return _account_organization(db, tenant).id
