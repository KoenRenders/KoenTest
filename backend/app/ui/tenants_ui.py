"""Tenantbeheer (/admin/tenants) — OPERATOR-only (#546, #581).

Since #1933 (CR-11 roll-out; end state §5.1, §5.2) the list stands on the list
layout with the kit's table, and a tenant is a record: read first, `?bewerken=1`
the editor with one save — the cards Tenant, Site and one per module. A secret
is typed and never shown back. Both screens' context comes from a view-model.

Eén scherm voor één object. Een tenant is een UNIT-``Organization`` mét een set
key/value-settings; die twee werden vroeger op twee schermen beheerd, met een
"Afdeling"-dropdown op /admin/instellingen als tweede manier om een tenant te
kiezen. Dat is nu één lijst-index (design-system C1): de lijst toont de units,
een tenant aanklikken opent de paginabrede editor met álle settings.

Na het aanmaken wordt de tenant_codes-cache gewist (``invalidate_tenant_codes``)
zodat de nieuwe tenant meteen resolvet (pad-prefix ``/<code>/…`` of, na het zetten
van een hostname-mapping, via de hostnaam). Composer-module: leest/schrijft via de
mdm-/kernel-facades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (  # noqa: F401
    Right,
    csrf_from_request,
    get_user_roles,
    may,
    require_csrf,
    require_platform_right,
    require_right,
    require_tenant_workspace,
)
from app.i18n import _
from app.kernel.tenant_config import SWITCH_SETTINGS, switch_is_on
from app.ui import (
    PER_PAGE_DEFAULT,
    PER_PAGE_OPTIONS,
    admin_nav,
    filterparams,
    is_fragment_request,
    list_return,
    per_page_from,
    record_frame,
    templates,
)
from app.ui.viewmodel import ViewModel

router = APIRouter(include_in_schema=False)

# Bekende sleutels: (key, label, hulptekst). Secrets staan apart.
BEKENDE_SLEUTELS = [
    # #945: `display_name` stond hier als merknaam mét de organisatienaam als
    # terugval — twee plaatsen voor één feit, en de instelling won. De naam komt
    # nu uit de organisatie. Komt er ooit een merknaam die van de statutaire naam
    # afwijkt, dan is dat een kolom op de organisatie en geen tenant-instelling.
    # An issue number belongs in a comment, never in what a user reads (#1643):
    # "(#519)" and "(#992)" stood in these help texts. #519: no hard-coded
    # tagline. #992: the header colour per tenant.
    ("tagline", "Tagline", "Korte ondertitel van de site. Leeg = geen ondertitel."),
    # #992, #1622: with the logo, the three colours of the tenant's brand file.
    # One line and an example each (#1643); the rule that refuses a colour says
    # why when it does.
    (
        "site_header_color",
        "Kleur van de kopbalk",
        "Achtergrondkleur van de kopbalk, bv. #005d29. Leeg = de standaardkleur.",
    ),
    (
        "site_brand_color",
        "Merkkleur",
        "De hoofdkleur van de huisstijl, bv. #0051a4. Leeg = de standaardkleur.",
    ),
    (
        "site_accent_color",
        "Accentkleur",
        "De kleur voor wat moet opvallen, bv. #ffd200. Leeg = de standaardkleur.",
    ),
    # #924: de sociale links staan bij de ORGANISATIE — ze bestaan ook als de
    # vereniging geen site heeft. Hier laten staan zou een tweede bewerkbare bron
    # zijn.
    (
        "base_url",
        "Canonieke URL",
        "Het webadres van de site, bv. https://…",
    ),
    # #1933: a choice and a switch, where a text field took "'send' of 'log_only'"
    # and "'1'". The stored values are the same.
    ("mail_mode", "Mail-modus", "Alleen loggen: mails worden niet verstuurd (demo)."),
    ("noindex", "Niet indexeren", "Zoekmachines nemen de site niet op (demo)."),
    ("language", "Taal", "Taal van de site, bv. nl_BE."),
    (
        "membership_price_full",
        "Lidgeld volledig",
        "Bedrag, bv. 35.00. Leeg = het bedrag van de omgeving.",
    ),
    ("membership_price_half", "Lidgeld half", "Bedrag, bv. 17.50."),
    ("membership_half_price_start_md", "Halfprijs van", "MM-DD, bv. 04-16."),
    ("membership_half_price_end_md", "Halfprijs tot", "MM-DD, bv. 09-16."),
    ("membership_next_year_from_md", "Volgend jaar vanaf", "MM-DD, bv. 09-17."),
    (
        "membership_renewal_start_md",
        "Hernieuwen vanaf",
        "MM-DD; leeg = enkel bij verlopen lidmaatschap.",
    ),
    # #924: rekeningnummer en begunstigde staan bij de ORGANISATIE. Ze hier laten
    # staan "voor het geval dat" zou een tweede bewerkbare bron zijn — dan is het
    # veld verplaatst in plaats van weggenomen.
    (
        "payment_term_days",
        "Betaaltermijn (dagen)",
        "Aantal dagen voor een overschrijving. Leeg = 7.",
    ),
    (
        "gmail_user",
        "Gmail-gebruiker",
        "Het Gmail-account waarmee de site mailt. Leeg = het account van de omgeving.",
    ),
    ("gmail_from", "Afzender (From)", "Getoonde afzender; leeg = de Gmail-gebruiker."),
    (
        "umami_src",
        "Umami script-URL",
        "bv. https://stats.example/script.js. Leeg = geen webstatistieken.",
    ),
    ("umami_website_id", "Umami Website-ID", "Het nummer van de site bij Umami."),
    (
        "max_item_quantity",
        "Max. aantal per item",
        "Hoogste aantal per product in één inschrijving. Leeg = 50.",
    ),
    (
        "max_registrations_per_email",
        "Max. inschrijvingen per e-mail",
        "Per e-mailadres en per activiteit. Leeg = 3.",
    ),
    # #1568: the two Raakje settings are switches (`SWITCH_SETTINGS` in
    # `kernel.tenant_config`), independent of each other. #917: the back-office
    # assistant needs the environment's switch too ("(#917)" stood in the help).
    (
        "admin_chat_enabled",
        "Raakje in de backoffice",
        "Werkt alleen als de omgeving Raakje toelaat.",
    ),
    (
        "public_chat_enabled",
        "Raakje op de publieke site",
        "Werkt alleen als de omgeving Raakje toelaat.",
    ),
]

# #971: hier stond `ORGANISATIEVELDEN` — naam, rechtsvorm, nummers, contact,
# rekening. Ze zijn verhuisd naar `/admin/organisaties`, en ze staan hier niet
# meer NAAST: twee schermen voor één feit is dezelfde duplicatie die #924 en #945
# uit de kolommen haalden, alleen een laag hoger.
#
# De reden dat ze ooit hier stonden was juist: er was geen ander scherm. De reden
# dat ze nu weg zijn is even eenvoudig: dit scherm bestaat alleen voor organisaties
# die een SITE draaien, en de ACCOUNT-organisatie draait er geen. Zij is nu net
# degene met een ondernemingsnummer en een rekening, en ze was daardoor nergens
# bereikbaar.
#
# Wat hier overblijft is wat dit scherm werkelijk is: de instellingen van de site.
GEHEIME_SLEUTELS = [
    ("mollie_api_key", "Mollie API-key", "Versleuteld opgeslagen; wordt nooit teruggetoond."),
    (
        "gmail_app_password",
        "Gmail app-wachtwoord",
        "Versleuteld opgeslagen; wordt nooit teruggetoond.",
    ),
]


# #854: sleutels die een platform-tenant NIET aangeboden krijgt. Een platform heeft
# geen leden en geen activiteiten, dus geen lidgeld en geen inschrijvingslimieten.
# Bood het scherm ze toch aan, dan vult iemand ooit een lidgeld in voor het platform,
# en dan staat er een waarde waarvan later niemand weet waarom.
LEDENSLEUTELS = {
    "membership_price_full",
    "membership_price_half",
    "membership_half_price_start_md",
    "membership_half_price_end_md",
    "membership_next_year_from_md",
    "membership_renewal_start_md",
    "max_item_quantity",
    "max_registrations_per_email",
    # Een platform heeft geen leden, dus ook geen vragen over leden (#917).
    "admin_chat_enabled",
}


NAV = "/admin/tenants"
OWN = "/admin/instellingen"
STATUSES = ("", "actief", "inactief")
#: CR-20 F5: by account by default, the account a column (Koen, 19 October 2026:
#: "a" — no heading per account, no change to the kit).
SORT_DEFAULT = "account"
SORTS = (SORT_DEFAULT, "-account", "naam", "-naam", "type", "-type")

#: Mail-modus as a choice (#1933): the stored values are the ones the mail
#: domain reads; an empty setting means "send".
MAIL_MODES = ("send", "log_only")


def _units(db: Session, *, alleen_actief: bool = False):
    """Wat dit scherm mag instellen: de platform-tenant én de afdelingen (#854).

    Bewust NIET `list_units`: het platform draagt dezelfde instellingen als elke
    tenant — dat is de hele winst van die keuze — dus het heeft dezelfde editor nodig.
    Waar afdelingen opgesomd worden (de platform-landing) blijft `list_units` gelden;
    het platform is geen afdeling.
    """
    from app.domains.mdm.api import list_manageable_tenants

    return list_manageable_tenants(db, alleen_actief=alleen_actief)


# ── The list ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class TenantsView(ViewModel):
    """`admin_tenants.html` and its fragment `_tn_kaarten.html`: the list of
    tenants on the kit's table (#1933)."""

    #: One dict per row: id, name, code, href, kind, account, site_org, inactive.
    rows: list[dict[str, Any]]
    columns: list[dict[str, Any]]
    segments: list[dict[str, Any]]
    figures: list[dict[str, Any]]
    status: str
    q: str
    sort: str
    sort_options: list[tuple[str, str]]
    page: int
    per_page: int
    total: int
    page_sizes: list[int]
    pager_url: str
    empty_reason: str
    #: A refused creation, and the confirmation of a good one.
    error: str | None = None
    created: bool = False
    csrf_token: str
    nav_items: list[dict[str, Any]] = field(default_factory=list)
    #: The fragment carries the toolbar's count and segment counts out-of-band.
    oob: bool = False


def _list_view(request: Request, db: Session, *, oob: bool = False, **extra: Any) -> TenantsView:
    """The list Tenants (#1933): the segments Alle · Actief · Inactief with their
    counts, the search on name and code, the sort by account (the default, CR-20
    F5), by name or by type. The state
    is in the URL; the toolbar asks this same address for the fragment."""
    state = filterparams(request)
    q = (state.get("q") or "").strip()
    status = (state.get("status") or "").strip()
    if status not in STATUSES:
        status = ""
    sort = (state.get("sort") or "").strip()
    if sort not in SORTS:
        sort = SORT_DEFAULT
    per_page = per_page_from(state.get("per_page"))
    try:
        page = max(1, int(state.get("page") or 1))
    except ValueError:
        page = 1

    everyone = _units(db)
    kinds = _kind_labels()
    kind_of = {u.id: kinds.get(u.kind.value, "") if u.kind is not None else "" for u in everyone}
    shown = everyone
    if q:
        needle = q.lower()
        shown = [
            u for u in shown if needle in (u.name or "").lower() or needle in (u.code or "").lower()
        ]
    if status == "actief":
        shown = [u for u in shown if u.is_active]
    elif status == "inactief":
        shown = [u for u in shown if not u.is_active]

    def by_name(u) -> tuple:
        return ((u.name or "").casefold(),)

    def by_kind(u) -> tuple:
        return (kind_of[u.id].casefold(), (u.name or "").casefold())

    # #1542: the account each site hangs under.
    accounts = _account_names(db, everyone)

    def by_account(u) -> tuple:
        return (accounts.get(u.id, "").casefold(), (u.name or "").casefold())

    order = {"naam": by_name, "type": by_kind, "account": by_account}[sort.lstrip("-")]
    shown = sorted(shown, key=order, reverse=sort[0] == "-")
    total = len(shown)
    page = min(page, max(1, -(-total // per_page)))
    shown = shown[(page - 1) * per_page : page * per_page]

    way_back = list_return(
        NAV,
        status=status,
        q=q,
        sort=sort if sort != SORT_DEFAULT else "",
        page=page if page > 1 else "",
        per_page=per_page if per_page != PER_PAGE_DEFAULT else "",
    )
    # #1554: the organisation behind the site, where it is not the tenant's own.
    site_orgs = _site_org_names(db, shown)
    rows = [
        {
            "id": u.id,
            "name": u.name,
            # #854: the platform is in this list but is no unit, and its code is
            # no path prefix: it reads without a slash.
            "code": u.code if u.is_platform else f"/{u.code}",
            "href": f"{NAV}/{u.id}?terug={quote(way_back, safe='/')}",
            "kind": kind_of[u.id],
            "account": accounts.get(u.id, ""),
            "site_org": site_orgs.get(u.id, ""),
            "inactive": not u.is_active,
        }
        for u in shown
    ]

    link_state = {"status": status, "q": q}

    def _query(**more: Any) -> str:
        return urlencode(
            {k: v for k, v in {**link_state, "per_page": per_page, **more}.items() if v != ""}
        )

    def _head(
        key: str, label: str, cell: str, ascending: str, descending: str, **more: Any
    ) -> dict[str, Any]:
        turned = descending if sort == ascending else ascending
        head: dict[str, Any] = {
            "key": key,
            "label": label,
            "cell": cell,
            "sort_url": f"{NAV}?{_query(sort=turned)}",
            "sort_page_url": f"{NAV}?{_query(sort=turned)}",
            **more,
        }
        if sort in (ascending, descending):
            head["sorted"] = "asc" if sort == ascending else "desc"
        return head

    active = sum(1 for u in everyone if u.is_active)
    inactive = len(everyone) - active
    if q:
        empty_reason = _("Geen tenants gevonden voor “%(q)s”.") % {"q": q}
    elif status == "inactief":
        empty_reason = _("Geen inactieve tenants.")
    else:
        empty_reason = _("Nog geen tenants. Maak er een met “Nieuwe tenant”.")
    values: dict[str, Any] = {
        "rows": rows,
        "columns": [
            _head("naam", _("Tenant"), "name", "naam", "-naam"),
            _head("type", _("Type"), "context", "type", "-type", width=150),
            _head("account", _("Account"), "extra", "account", "-account", priority=1, width=200),
            {
                "key": "site_org",
                "label": _("Organisatie achter de site"),
                "cell": "extra",
                "priority": 2,
                "width": 240,
            },
            {"key": "status", "label": _("Status"), "cell": "status"},
        ],
        "segments": [
            {"value": "", "label": _("Alle"), "count": len(everyone)},
            {"value": "actief", "label": _("Actief"), "count": active},
            {"value": "inactief", "label": _("Inactief"), "count": inactive},
        ],
        "figures": [
            {"value": str(active), "label": _("Actief"), "title": _("Tenants die actief zijn.")},
            {
                "value": str(inactive),
                "label": _("Inactief"),
                "title": _("Tenants die niet actief zijn."),
                "warning": inactive > 0,
            },
        ],
        "status": status,
        "q": q,
        "sort": sort,
        "sort_options": [("account", _("Account")), ("naam", _("Naam")), ("type", _("Type"))],
        "page": page,
        "per_page": per_page,
        "total": total,
        "page_sizes": list(PER_PAGE_OPTIONS),
        "pager_url": f"{NAV}?{_query(sort=sort)}",
        "empty_reason": empty_reason,
        "csrf_token": csrf_from_request(request),
        "nav_items": [] if oob else admin_nav(NAV, request),
        "oob": oob,
    }
    values.update(extra)
    return TenantsView(**values)


#: The choice "nieuwe organisatie" in the two selects of Tenants › Nieuw (CR-20 F5).
NEW = "nieuw"


def _new_ctx(request: Request, db: Session, *, typed: dict | None = None, error=None) -> dict:
    """What the new-tenant form needs (CR-20 F5): the creatable kinds, the
    accounts — the organisations tenants name — with "nieuwe organisatie", and
    the organisations the chosen account's site may show. `typed` is what a
    refused POST sent, shown again as it was."""
    from app.domains.mdm.api import accounts

    typed = typed or {}
    account = typed.get("account_id", "")
    return {
        "nav_items": admin_nav(NAV, request),
        "error": error,
        "typed": typed,
        # #1523: a new tenant takes one of the creatable kinds, never PLATFORM.
        "kind_options": _creatable_kind_options(),
        "account_options": [("", _("— Kies een account —"))]
        + [(str(a.id), a.name) for a in accounts(db)]
        + [(NEW, _("Nieuwe organisatie…"))],
        "shown_options": _shown_options(db, account),
        "new_choice": NEW,
        "csrf_token": csrf_from_request(request),
    }


def _shown_options(db: Session, account: str) -> list[tuple[str, str]]:
    """What a new site of this account may show (#1550, CR-20 F5): the account
    itself, the organisations its tenants show, and "nieuwe organisatie"."""
    from app.domains.mdm.api import organizations_of_account

    others = (
        [(str(o["id"]), o["name"]) for o in organizations_of_account(db, int(account))][1:]
        if account.isdigit()
        else []
    )
    return [("", _("Het account zelf")), *others, (NEW, _("Nieuwe organisatie…"))]


def _site_org_options(db: Session, unit) -> list[tuple[str, str]]:
    """The organisations a tenant's site may show (#1550): its account first,
    then the organisations the account's tenants show (CR-20)."""
    from app.domains.mdm.api import account_organization_id, organizations_of_account

    account = account_organization_id(db, unit)
    return [(str(o["id"]), o["name"]) for o in organizations_of_account(db, account)]


def _account_names(db: Session, units) -> dict[int, str]:
    """Each listed site's account name, by the site's id (#1542)."""
    from app.domains.mdm.api import organization_options

    # A tenant names its account's party (CR-26 C4.9).
    names = {o["party_id"]: o["name"] for o in organization_options(db)}
    return {u.id: names[u.account_id] for u in units if u.account_id in names}


def _site_org_names(db: Session, units) -> dict[int, str]:
    """The name of the organisation behind each listed site, by the site's id
    (#1554, CR-20 F5: "toont de gegevens van" for every tenant). Asked of the
    resolver the footer uses (#1550), so the list and the site cannot disagree."""
    from app.kernel.tenant_config import site_name_default

    return {u.id: site_name_default(db, u.id) for u in units}


def _creatable_kind_options() -> list[tuple[str, str]]:
    """The kinds a tenant may take, as (code, label): never PLATFORM (#1523).
    One list for the new-tenant form and the editor (#1533)."""
    from app.domains.mdm.api import CREATABLE_TENANT_KINDS

    creatable = {k.value for k in CREATABLE_TENANT_KINDS}
    return [(code, label) for code, label in _kind_labels().items() if code in creatable]


def _kind_labels() -> dict[str, str]:
    from app.domains.mdm.api import TENANT_KIND
    from app.kernel.codes import code_labels

    return dict(code_labels(TENANT_KIND.name))


def _settings_of(unit) -> tuple[list, list]:
    """The settings and secrets this tenant's record shows — and saves.

    #854: a platform tenant does not get the membership fields. Since #1498 the
    settings of a module that is off are on the form too: the form carries every
    key, so saving a module off keeps its values (switching off deletes nothing,
    #1478).
    """
    sleutels = [
        rij for rij in BEKENDE_SLEUTELS if not (unit.is_platform and rij[0] in LEDENSLEUTELS)
    ]
    return sleutels, list(GEHEIME_SLEUTELS)


def _hidden_cards(unit) -> set:
    """The modules without a card for this tenant: a platform has no members (#854)."""
    from app.kernel.modules import ModuleCode

    return {ModuleCode.MEMBERSHIP} if unit.is_platform else set()


# ── The record ────────────────────────────────────────────────────────────────

#: The shape of a setting's field on the record (#1933): its kind and how much
#: of the grid's row it takes. A setting that is not named is a half text field.
_QUARTER = {"span": "quarter"}
_FIELD_SHAPES: dict[str, dict[str, Any]] = {
    "tagline": {"long": True},
    "base_url": {"kind": "url"},
    "umami_src": {"kind": "url"},
    "language": _QUARTER,
    "mail_mode": {"kind": "select", **_QUARTER},
    "membership_price_full": {"kind": "number", "unit": "€", **_QUARTER},
    "membership_price_half": {"kind": "number", "unit": "€", **_QUARTER},
    "membership_half_price_start_md": _QUARTER,
    "membership_half_price_end_md": _QUARTER,
    "membership_next_year_from_md": _QUARTER,
    "membership_renewal_start_md": _QUARTER,
    "payment_term_days": {"kind": "number", **_QUARTER},
    # Half, so the label stays on one line (Koen: "maak je kolommen breder ofzo?").
    "max_item_quantity": {"kind": "number"},
    "max_registrations_per_email": {"kind": "number"},
}


def _setting_field(key: str, label: str, help_text: str, value: str) -> dict[str, Any]:
    """One setting as the template draws it: a kit field in edit mode, a fact in
    its cell in read mode (`display`)."""
    from app.kernel.tenant_config import SITE_COLOR_DEFAULTS

    shaped: dict[str, Any] = {
        "key": key,
        "label": _(label),
        "help": _(help_text),
        "value": value,
        "kind": "text",
        "span": "half",
        "long": False,
        "unit": None,
        "options": [],
        "placeholder": "",
        "switch": None,
        "display": value or "—",
        **_FIELD_SHAPES.get(key, {}),
    }
    if shaped["kind"] == "url" or shaped["long"]:
        shaped["span"] = "full"
    if key in SITE_COLOR_DEFAULTS:
        # #1643: a sample beside the input, the standard colour while it is empty.
        shaped.update(kind="color", span="quarter", placeholder=SITE_COLOR_DEFAULTS[key])
    elif key == "mail_mode":
        shaped["options"] = [("send", _("Verzenden")), ("log_only", _("Alleen loggen"))]
        shaped["value"] = value if value in MAIL_MODES else MAIL_MODES[0]
        shaped["display"] = dict(shaped["options"])[shaped["value"]]
    elif key == "noindex":
        # A yes or a no: "1" is what the site reads (#1933; it was a text field).
        shaped["switch"] = {"on": value == "1", "on_value": "1", "off_value": ""}
    elif key in SWITCH_SETTINGS:
        on_value, off_value, _default = SWITCH_SETTINGS[key]
        shaped["switch"] = {
            "on": switch_is_on(key, value),
            "on_value": on_value,
            "off_value": off_value,
        }
    if shaped["switch"] is not None:
        shaped["kind"] = "switch"
        shaped["display"] = _("ja") if shaped["switch"]["on"] else _("nee")
    elif shaped["unit"] and value:
        shaped["display"] = f"{shaped['unit']} {value}"
    return shaped


def _secret_field(key: str, label: str, help_text: str, is_set: bool) -> dict[str, Any]:
    """A secret: typed, never shown back. Read, it says whether one is set."""
    return {
        "key": key,
        "label": _(label),
        "help": _(help_text),
        "is_set": is_set,
        "placeholder": _("•••• (gezet — leeg laten = ongewijzigd)")
        if is_set
        else _("niet gezet — de waarde van de omgeving geldt"),
        "display": _("gezet") if is_set else _("niet gezet"),
        "clear_label": _("Wissen"),
    }


@dataclass(frozen=True, kw_only=True)
class TenantRecordView(ViewModel):
    """`admin_tenant.html`: a tenant's record, read first (#1933)."""

    tenant_id: int
    #: #1535: a tenant workspace's own "Instellingen" — no Tenant card, the
    #: modules read-only.
    own: bool
    edit: bool
    record_head: dict[str, Any]
    way_back: dict[str, Any] | None
    summary: dict[str, Any]
    modules_editable: bool
    #: The card Tenant: {kind, account, site_org}, each {value, label, options};
    #: None in the own scope.
    tenant_card: dict[str, Any] | None
    site_name: dict[str, str]
    #: The day the site lives by (#2156): an IANA name, edited on the platform's screen
    #: (the own scope reads it).
    time_zone: str
    #: The card Site and one card per module: {code, label, on, fields, secrets,
    #: error}; `code` None for Site.
    cards: list[dict[str, Any]]
    #: A module without a card keeps its state through the one save.
    kept_modules: list[str]
    error: str | None
    save_url: str
    cancel_href: str
    toast_opgeslagen: bool
    csrf_token: str
    nav_items: list[dict[str, Any]] = field(default_factory=list)


def _cards(db: Session, unit, *, modules_on, values, secrets_set, refused=None) -> list[dict]:
    """The record's cards (#1498): "Site" for the settings no module owns, then
    one per module in registry order.

    The grouping is the registry's (`owner_of("tenant_settings", key)`), not a
    second list here. `refused` = (module, message): a refused dependency shows
    on the card of the module concerned.
    """
    from app.kernel.modules import MODULES, owner_of

    sleutels, geheim = _settings_of(unit)

    def owned_by(code) -> tuple[list, list]:
        return (
            [
                _setting_field(key, label, hulp, values[key])
                for key, label, hulp in sleutels
                if owner_of("tenant_settings", key) == code
            ],
            [
                _secret_field(key, label, hulp, secrets_set[key])
                for key, label, hulp in geheim
                if owner_of("tenant_settings", key) == code
            ],
        )

    fields, secrets = owned_by(None)
    cards: list[dict] = [
        {
            "code": None,
            "label": _("Site"),
            "on": True,
            "fields": fields,
            "secrets": secrets,
            "error": None,
        }
    ]
    for module in MODULES:
        if module.code in _hidden_cards(unit):
            continue
        fields, secrets = owned_by(module.code)
        cards.append(
            {
                "code": module.code.value,
                "label": module.label,
                "on": module.code.value in modules_on,
                "fields": fields,
                "secrets": secrets,
                "error": refused[1] if refused and refused[0] == module.code else None,
            }
        )
    return cards


def _record_view(
    request: Request,
    db: Session,
    email: str,
    tenant_id: int,
    *,
    own: bool = False,
    edit: bool | None = None,
    modules_on=None,
    refused=None,
    typed: dict[str, str] | None = None,
    error: str | None = None,
    saved: bool = False,
) -> TenantRecordView:
    """A tenant's record (#1933; end state §2.2, §5.2): the head with Bewerken,
    the summary beside the form column, and the cards Tenant, Site and one per
    module — read first, `?bewerken=1` the editor with ONE save for every card.

    `own` (#1535) is the tenant workspace's own "Instellingen": the same record
    without the Tenant card and with the modules read-only — type, account and
    modules are platform administration (#1533). `typed` are the values of a
    refused save, shown again as they were sent (#797)."""
    from app.domains.mdm.api import enabled_modules, organization_options
    from app.domains.mdm.api import secrets_gezet as _secrets_gezet
    from app.kernel.tenant_config import get_setting, site_name_default, site_organization_id

    unit = next((u for u in _units(db) if u.id == tenant_id), None)
    if unit is None:
        raise HTTPException(status_code=404, detail=_("Onbekende tenant"))
    sleutels, geheim = _settings_of(unit)
    stored_on = enabled_modules(unit.id, db=db)
    on = set(modules_on) if modules_on is not None else stored_on
    values = {key: get_setting(db, key, tenant_id=tenant_id) or "" for key, _l, _h in sleutels}
    if typed:
        values.update({key: value for key, value in typed.items() if key in values})
    secrets_set = _secrets_gezet(db, tenant_id, [key for key, _l, _h in geheim])

    base = OWN if own else f"{NAV}/{tenant_id}"
    frame = record_frame(request, db, NAV)
    way_back = None if own else frame["way_back"]
    keep = way_back["keep"] if way_back else ""
    can_edit = may(db, email, Right.SETTINGS_MANAGE if own else Right.PLATFORM_MANAGE)
    editing = (frame["head_editing"] if edit is None else edit) and can_edit

    is_platform = unit.is_platform
    kind_label = _kind_labels().get(unit.kind.value, "") if unit.kind is not None else ""
    everyone = {o["id"]: o for o in organization_options(db)}
    account = next((o for o in everyone.values() if o["party_id"] == unit.account_id), None)
    behind_id = site_organization_id(db, tenant_id)
    behind = everyone.get(behind_id)

    # The head's facts: the code, and the two organisations as jump links —
    # platform administration answers in the platform workspace only, so the
    # own scope links to its own "Onze organisatie" and names the account.
    facts: list[dict[str, str]] = [{"text": unit.code if is_platform else f"/{unit.code}"}]
    if account is not None:
        under = _("Account %(naam)s") % {"naam": account["name"]}
        facts.append(
            {"text": under}
            if own
            else {
                "text": under,
                "kind": "reference",
                "href": f"/admin/organisaties/{account['id']}",
            }
        )
    if behind is not None:
        facts.append(
            {
                "text": _("Organisatie %(naam)s") % {"naam": behind["name"]},
                "kind": "reference",
                "href": "/admin/organisatie" if own else f"/admin/organisaties/{behind_id}",
            }
        )
    cards = _cards(db, unit, modules_on=on, values=values, secrets_set=secrets_set, refused=refused)
    module_cards = [c for c in cards if c["code"]]
    tenant_card = None
    if not own:
        site_org_options = _site_org_options(db, unit)
        site_org_value = str(unit.organization_id)
        tenant_card = {
            # #1533: a unit's kind can be changed between the creatable kinds;
            # the platform's is fixed and only shown.
            "kind": {
                "value": unit.kind.value if unit.kind is not None else "",
                "label": kind_label or "—",
                "options": [] if is_platform else _creatable_kind_options(),
            },
            # The account the tenant hangs under, a fact: chosen once, at Tenants ›
            # Nieuw — an existing tenant never changes it (CR-26; Koen,
            # 19 October 2026: "1").
            "account": {"label": account["name"] if account else "—"},
            # #1550: whose data the site shows — its account, or another
            # organisation of its account (CR-20).
            "site_org": {
                "value": site_org_value,
                "label": dict(site_org_options).get(site_org_value, "—"),
                "options": site_org_options,
            },
        }
    return TenantRecordView(
        tenant_id=tenant_id,
        own=own,
        edit=editing,
        record_head={
            "title": unit.site_name or site_name_default(db, tenant_id) or unit.name,
            "badges": [{"label": kind_label, "tone": "gray"}] if kind_label else [],
            "facts": facts,
            "primary": {
                "label": _("Bewerken"),
                "href": f"{base}?bewerken=1" + (f"&{keep}" if keep else ""),
            }
            if can_edit
            else None,
            "actions": [],
        },
        way_back=way_back,
        summary={
            "state": {
                "label": _("Actief") if unit.is_active else _("Inactief"),
                "tone": "green" if unit.is_active else "red",
            },
            "figures": [
                {"label": _("Type"), "value": kind_label or "—"},
                {"label": _("Account"), "value": account["name"] if account else "—"},
                {
                    "label": _("Modules aan"),
                    "value": _("%(on)s van %(all)s")
                    % {"on": sum(1 for c in module_cards if c["on"]), "all": len(module_cards)},
                },
            ],
        },
        modules_editable=not own,
        tenant_card=tenant_card,
        # #1546: the site's own name, and the organisation's name it falls back to.
        site_name={
            "value": (typed or {}).get("site_name", unit.site_name or ""),
            "default": site_name_default(db, tenant_id),
        },
        time_zone=(typed or {}).get("time_zone", unit.time_zone),
        cards=cards,
        kept_modules=sorted(c.value for c in _hidden_cards(unit) if c.value in stored_on),
        error=error,
        save_url=base,
        cancel_href=base + (f"?{keep}" if keep else ""),
        toast_opgeslagen=saved,
        csrf_token=csrf_from_request(request),
        nav_items=admin_nav(OWN if own else NAV, request),
    )


def _record_page(request: Request, db: Session, email: str, tenant_id: int, **kwargs):
    status_code = kwargs.pop("status_code", 200)
    view = _record_view(request, db, email, tenant_id, **kwargs)
    return templates.TemplateResponse(
        request, "admin_tenant.html", view.as_context(), status_code=status_code
    )


@router.get("/admin/instellingen", response_class=HTMLResponse)
def own_settings(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_VIEW)),
):
    """The tenant workspace's own site settings (#1535), for its ADMIN and the
    operator: the record of this workspace's tenant, its secrets included (never
    shown back), the modules read-only. Until #1535 this address was a 301 to
    /admin/tenants (#581), which is platform administration now.
    """
    return _record_page(request, db, email, require_tenant_workspace(db), own=True)


@router.post(
    "/admin/instellingen", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
async def own_settings_save(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_MANAGE)),
):
    return await _save(request, db, require_tenant_workspace(db), email, own=True)


@router.get("/admin/tenants", response_class=HTMLResponse)
def tenants(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_VIEW)),
):
    """The list Tenants (#1933). The toolbar asks this same address for the
    fragment: a page swap would replace the search field while it is typed in."""
    fragment = is_fragment_request(request)
    view = _list_view(request, db, oob=fragment)
    template = "_tn_kaarten.html" if fragment else "admin_tenants.html"
    return templates.TemplateResponse(request, template, view.as_context())


@router.get("/admin/tenants/nieuw", response_class=HTMLResponse)
def tenant_nieuw(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_VIEW)),
):
    """Aanmaken als volledige pagina (#627, §2.8) i.p.v. een modal.

    CR-19 (#1478): operator-only on GET too. Until now only the POST was — an
    ADMIN could open the form, which leaked the accounts list and promised a
    save that was then refused.
    """
    return templates.TemplateResponse(request, "admin_tenant_nieuw.html", _new_ctx(request, db))


@router.get("/admin/tenants/{tenant_id}", response_class=HTMLResponse)
def tenant_editor(
    tenant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_VIEW)),
):
    return _record_page(request, db, email, tenant_id)


@router.get("/admin/tenants/nieuw/getoond", response_class=HTMLResponse)
def new_tenant_shown_field(
    request: Request,
    account_id: str = "",
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_VIEW)),
):
    """The field "Toont de gegevens van" for the chosen account (CR-20 F5): the
    form asks it again when the account changes."""
    ctx = _new_ctx(request, db, typed={"account_id": account_id})
    return templates.TemplateResponse(request, "_tenant_nieuw_getoond.html", ctx)


@router.post("/admin/tenants", response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def tenant_aanmaken(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_MANAGE)),
    site_name: str = Form(""),
    code: str = Form(""),
    account_id: str = Form(""),
    new_account_name: str = Form(""),
    organization_id: str = Form(""),
    new_organization_name: str = Form(""),
    base_url: str = Form(""),
    kind: str = Form("VERENIGING"),
    time_zone: str = Form(""),
):
    """Creates the tenant — and the organisation chosen as "nieuwe organisatie",
    in the same transaction (CR-20 F5). A refusal shows the form again with what
    was typed."""
    from app.domains.mdm.api import TenantFout, create_tenant

    try:
        create_tenant(
            db,
            code=code,
            account_id=int(account_id) if account_id.isdigit() else None,
            new_account_name=new_account_name if account_id == NEW else None,
            organization_id=int(organization_id) if organization_id.isdigit() else None,
            new_organization_name=new_organization_name if organization_id == NEW else None,
            site_name=site_name,
            base_url=base_url,
            kind=kind,
            time_zone=time_zone,
        )
    except TenantFout as fout:
        typed = {
            "site_name": site_name,
            "code": code,
            "account_id": account_id,
            "new_account_name": new_account_name,
            "organization_id": organization_id,
            "new_organization_name": new_organization_name,
            "base_url": base_url,
            "kind": kind,
            "time_zone": time_zone,
        }
        ctx = _new_ctx(request, db, typed=typed, error=_(str(fout)))
        return templates.TemplateResponse(request, "admin_tenant_nieuw.html", ctx)
    view = _list_view(request, db, created=True)
    return templates.TemplateResponse(request, "admin_tenants.html", view.as_context())


@router.post(
    "/admin/tenants/{tenant_id}", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
async def tenant_opslaan(
    tenant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_MANAGE)),
):
    """The record's one Opslaan (#1498): the module set and the settings in one
    transaction (`save_tenant`). A refusal shows the form again as it was sent,
    with a 422 (#797, #1478), which the browser swaps in (#1515)."""
    return await _save(request, db, tenant_id, email, own=False)


async def _save(request: Request, db: Session, tenant_id: int, email: str, *, own: bool):
    """One save path for both scopes (#1535): the same `save_tenant`. The own
    scope saves the settings only; the module switch, the kind and the account
    are the operator's, on the platform, and a form that sends them is refused
    with 403 rather than quietly ignored.
    """
    from app.domains.mdm.api import ModuleRefused, OngeldigeInstelling, TenantFout, save_tenant

    unit = next((u for u in _units(db) if u.id == tenant_id), None)
    if unit is None:
        raise HTTPException(status_code=404, detail=_("Onbekende tenant"))
    sleutels, geheim = _settings_of(unit)
    form = await request.form()
    if own and any(
        k in form
        for k in ("modules_shown", "modules", "kind", "account_id", "site_organization_id")
    ):
        raise HTTPException(
            status_code=403,
            detail=_("Modules, type en account beheert de platformbeheerder."),
        )
    # Only what the form carries is saved: a key that is not on it is left
    # alone, never emptied, and the module set only when the form sent its
    # switches (`modules_shown`) — an empty list then means "all off". A switch
    # that is off sends an empty value (the kit's hidden field): no module.
    modules = [str(v) for v in form.getlist("modules") if v] if form.get("modules_shown") else None
    labels = {key: label for key, label, _h in BEKENDE_SLEUTELS}

    def again(**kwargs) -> Any:
        # #797: the typed values stay; throwing them away makes the message worse
        # than the mistake.
        typed = {
            k: str(v) for k, v in form.items() if k in labels or k in ("site_name", "time_zone")
        }
        return _record_page(
            request,
            db,
            email,
            tenant_id,
            own=own,
            edit=True,
            modules_on=modules,
            typed=typed,
            status_code=422,
            **kwargs,
        )

    # #971: enkel nog de instellingen van de site. Wat de organisatie IS, wordt op
    # `/admin/organisaties` bewerkt — één scherm per feit.
    try:
        save_tenant(
            db,
            tenant_id,
            form,
            known=[key for key, _l, _h in sleutels if key in form],
            secret=[key for key, _l, _h in geheim],
            modules=modules,
            # #1533: only what the form sends; the platform's editor sends none.
            kind=str(form["kind"]) if "kind" in form else None,
            # The editor sends no account; one that is posted all the same is refused.
            account=str(form["account_id"]) if "account_id" in form else None,
            site_organization=str(form["site_organization_id"])
            if "site_organization_id" in form
            else None,
            site_name=str(form["site_name"]) if "site_name" in form else None,
            time_zone=str(form["time_zone"]) if "time_zone" in form else None,
            actor=email,
        )
    except ModuleRefused as fout:
        return again(refused=(fout.module, _(str(fout))))
    except TenantFout as fout:
        return again(error=_(str(fout)))
    except OngeldigeInstelling as fout:
        return again(error=" ".join(f"{_(labels.get(k, k))}: {m}" for k, m in fout.fouten.items()))
    # #742: the one confirmation pattern (§2.9) — a toast, rendered by the shell
    # in its host because this answer replaces the whole page. Back in read mode,
    # at the record's own address.
    response = _record_page(request, db, email, tenant_id, own=own, edit=False, saved=True)
    response.headers["HX-Push-Url"] = OWN if own else f"{NAV}/{tenant_id}"
    return response
