"""Tenantbeheer (/admin/tenants) — OPERATOR-only (#546, #581).

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

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (  # noqa: F401
    csrf_from_request,
    get_user_roles,
    require_admin_ui,
    require_csrf,
    require_operator_ui,
)
from app.domains.mdm.api import OrganizationType
from app.i18n import _
from app.ui import admin_nav, filterparams, is_fragment_request, templates

router = APIRouter(include_in_schema=False)

# Bekende sleutels: (key, label, hulptekst). Secrets staan apart.
BEKENDE_SLEUTELS = [
    # #945: `display_name` stond hier als merknaam mét de organisatienaam als
    # terugval — twee plaatsen voor één feit, en de instelling won. De naam komt
    # nu uit de organisatie. Komt er ooit een merknaam die van de statutaire naam
    # afwijkt, dan is dat een kolom op de organisatie en geen tenant-instelling.
    ("tagline", "Tagline", "Ondertitel in de header. Leeg = geen ondertitel (#519)."),
    (
        "site_header_color",
        "Kleur van de kopbalk",
        "Achtergrond van de kopbalk op de publieke site, als #rrggbb (bv. #005d29). "
        "Moet donker genoeg zijn voor witte tekst. Leeg = de standaardkleur (#992).",
    ),
    # #924: de sociale links staan bij de ORGANISATIE — ze bestaan ook als de
    # vereniging geen site heeft. Hier laten staan zou een tweede bewerkbare bron
    # zijn.
    (
        "base_url",
        "Canonieke URL",
        "Publieke origin voor links in mails/Mollie/SEO, bv. https://raakmillegem.be.",
    ),
    (
        "privacy_url",
        "Privacyverklaring-link",
        "Footer-link naar je privacyverklaring. Leeg = niet tonen.",
    ),
    ("mail_mode", "Mail-modus", "'send' (default) of 'log_only' (mails enkel loggen — demo)."),
    ("noindex", "Noindex", "'1' = niet indexeren door zoekmachines (demo)."),
    ("language", "Taal", "Catalogustaal, bv. nl_BE (default)."),
    ("membership_price_full", "Lidgeld volledig", "Bedrag, bv. 35.00. Leeg = .env-default."),
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
        "Aantal dagen voor een overschrijving. Default 7.",
    ),
    (
        "gmail_user",
        "Gmail-gebruiker",
        "Afzender-account voor uitgaande mail (SMTP). Leeg = .env-default.",
    ),
    ("gmail_from", "Afzender (From)", "Getoonde afzender; leeg = de Gmail-gebruiker."),
    (
        "umami_src",
        "Umami script-URL",
        "bv. https://stats.example/script.js. Leeg = geen webstatistieken.",
    ),
    ("umami_website_id", "Umami Website-ID", "Het Umami-site-ID (geen secret)."),
    ("max_item_quantity", "Max. aantal per item", "Inschrijvingslimiet per item. Default 50."),
    ("max_registrations_per_email", "Max. inschrijvingen per e-mail", "Per activiteit. Default 3."),
    (
        "admin_chat_enabled",
        "Raakje in de backoffice",
        "'1' = het bestuur mag Raakje vragen stellen over de eigen cijfers. Leeg = uit. "
        "Werkt enkel als ADMIN_CHAT_ENABLED ook aan staat (#917).",
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


def _units(db: Session, *, alleen_actief: bool = False):
    """Wat dit scherm mag instellen: de platform-tenant én de afdelingen (#854).

    Bewust NIET `list_units`: het platform draagt dezelfde instellingen als elke
    tenant — dat is de hele winst van die keuze — dus het heeft dezelfde editor nodig.
    Waar afdelingen opgesomd worden (de platform-landing) blijft `list_units` gelden;
    het platform is geen afdeling.
    """
    from app.domains.mdm.api import list_manageable_tenants

    return list_manageable_tenants(db, alleen_actief=alleen_actief)


def _lijst_ctx(request: Request, db: Session) -> dict:
    """Lijst-index (C1): zoeken op naam/code, filter op status."""
    from app.domains.mdm.api import list_accounts

    # #671: uit HX-Current-URL als htmx die meestuurt, anders uit de query-string.
    stand = filterparams(request)
    zoek = (stand.get("q") or "").strip()
    status = (stand.get("status") or "").strip()
    units = _units(db)
    if zoek:
        naald = zoek.lower()
        units = [
            u for u in units if naald in (u.name or "").lower() or naald in (u.code or "").lower()
        ]
    if status == "actief":
        units = [u for u in units if u.is_active]
    elif status == "inactief":
        units = [u for u in units if not u.is_active]
    accounts = list_accounts(db)
    kinds = _kind_labels()
    return {
        "nav_items": admin_nav("/admin/tenants"),
        "units": units,
        # CR-19 (#1478): the kind of each tenant, as its label; the platform has none.
        "kind_of": {u.id: kinds[u.kind.value] for u in units if u.kind is not None},
        "kind_options": list(kinds.items()),
        # #854: the platform is in this list but is no unit; the screen marks
        # it. Decided here, because a template comparing the member with
        # "PLATFORM" is always false (CR-12 phase 2).
        "platform_id": next((u.id for u in units if u.org_type is OrganizationType.PLATFORM), None),
        "accounts": accounts,
        "q": zoek,
        "status": status,
        "error": None,
        "opgeslagen": False,
        "csrf_token": csrf_from_request(request),
    }


def _kind_labels() -> dict[str, str]:
    from app.domains.mdm.api import TENANT_KIND
    from app.kernel.codes import code_labels

    return dict(code_labels(TENANT_KIND.name))


def _settings_of(unit) -> tuple[list, list]:
    """The settings and secrets this tenant's editor shows — and saves.

    #854: a platform tenant does not get the membership fields. Since #1498 the
    settings of a module that is off are on the form too, folded away in its
    card: the form carries every key, so saving a module off keeps its values
    (switching off deletes nothing, #1478), and ticking it shows them again.
    """
    sleutels = [
        rij
        for rij in BEKENDE_SLEUTELS
        if not (unit.org_type == OrganizationType.PLATFORM and rij[0] in LEDENSLEUTELS)
    ]
    return sleutels, list(GEHEIME_SLEUTELS)


def _hidden_cards(unit) -> set:
    """The modules without a card for this tenant: a platform has no members (#854)."""
    from app.kernel.modules import ModuleCode

    return {ModuleCode.MEMBERSHIP} if unit.org_type == OrganizationType.PLATFORM else set()


def _cards(db: Session, unit, *, modules_on, refused=None) -> list[dict]:
    """The editor's cards (#1498): "Site" for the settings no module owns, then
    one per module in registry order, its checkbox in the card's header.

    The grouping is the registry's (`owner_of("tenant_settings", key)`), not a
    second list here. A module's record count is what becomes unreachable when
    it goes off. `refused` = (module, message): a refused dependency shows on
    the card of the module concerned.
    """
    from app.kernel.modules import MODULES, owner_of, record_counts

    sleutels, geheim = _settings_of(unit)
    counts = record_counts(db, unit.id)

    def owned_by(code) -> tuple[list, list]:
        return (
            [r for r in sleutels if owner_of("tenant_settings", r[0]) == code],
            [r for r in geheim if owner_of("tenant_settings", r[0]) == code],
        )

    settings, secrets = owned_by(None)
    cards: list[dict] = [
        {
            "code": None,
            "label": _("Site"),
            "count": None,
            "on": True,
            "settings": settings,
            "secrets": secrets,
            "error": None,
        }
    ]
    for module in MODULES:
        if module.code in _hidden_cards(unit):
            continue
        settings, secrets = owned_by(module.code)
        cards.append(
            {
                "code": module.code.value,
                "label": module.label,
                "count": counts.get(module.code),
                "on": module.code.value in modules_on,
                "settings": settings,
                "secrets": secrets,
                "error": refused[1] if refused and refused[0] == module.code else None,
            }
        )
    return cards


def _editor_ctx(
    request: Request, db: Session, tenant_id: int, *, modules_on=None, refused=None
) -> dict:
    from app.domains.mdm.api import enabled_modules
    from app.domains.mdm.api import secrets_gezet as _secrets_gezet
    from app.kernel.tenant_config import get_setting

    unit = next((u for u in _units(db) if u.id == tenant_id), None)
    if unit is None:
        raise HTTPException(status_code=404, detail=_("Onbekende tenant"))
    sleutels, geheim = _settings_of(unit)
    stored_on = enabled_modules(unit.id, db=db)
    on = set(modules_on) if modules_on is not None else stored_on
    waarden = {
        key: get_setting(db, key, tenant_id=tenant_id) or "" for key, _label, _hulp in sleutels
    }
    secrets_gezet = _secrets_gezet(db, tenant_id, [key for key, _label, _hulp in geheim])
    return {
        "nav_items": admin_nav("/admin/tenants"),
        "unit": unit,
        "tenant_id": tenant_id,
        # CR-19 (#1478): the kind is chosen once, at creation, and shown here.
        "kind_label": _kind_labels().get(unit.kind.value) if unit.kind is not None else None,
        "cards": _cards(db, unit, modules_on=on, refused=refused),
        # A module without a card keeps its state through the one Opslaan.
        "kept_modules": sorted(c.value for c in _hidden_cards(unit) if c.value in stored_on),
        "waarden": waarden,
        "secrets_gezet": secrets_gezet,
        "error": None,
        "opgeslagen": False,
        "csrf_token": csrf_from_request(request),
    }


@router.get("/admin/instellingen")
def instellingen_verhuisd():
    """De aparte Instellingen-pagina is opgegaan in /admin/tenants (#581).

    301 in plaats van verwijderen: bestaande bladwijzers en links blijven werken.
    """
    return RedirectResponse("/admin/tenants", status_code=301)


@router.get("/admin/tenants", response_class=HTMLResponse)
def tenants(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
):
    require_operator_ui(db, email)
    # De filterbalk haalt enkel de kaarten op; een pagina-swap zou het zoekveld
    # tijdens het typen vervangen en de focus wegnemen.
    sjabloon = "_tn_kaarten.html" if is_fragment_request(request) else "admin_tenants.html"
    return templates.TemplateResponse(request, sjabloon, _lijst_ctx(request, db))


@router.get("/admin/tenants/nieuw", response_class=HTMLResponse)
def tenant_nieuw(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
):
    """Aanmaken als volledige pagina (#627, §2.8) i.p.v. een modal.

    Hergebruikt de contextbouwer van de lijst voor de accounts-dropdown.

    CR-19 (#1478): operator-only on GET too. Until now only the POST was — an
    ADMIN could open the form, which leaked the accounts list and promised a
    save that was then refused.
    """
    require_operator_ui(db, email)
    return templates.TemplateResponse(request, "admin_tenant_nieuw.html", _lijst_ctx(request, db))


@router.get("/admin/tenants/{tenant_id}", response_class=HTMLResponse)
def tenant_editor(
    tenant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
):
    require_operator_ui(db, email)
    return templates.TemplateResponse(
        request, "admin_tenant.html", _editor_ctx(request, db, tenant_id)
    )


@router.post("/admin/tenants", response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def tenant_aanmaken(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    name: str = Form(""),
    code: str = Form(""),
    account_id: str = Form(""),
    base_url: str = Form(""),
    kind: str = Form("VERENIGING"),
):
    from app.domains.mdm.api import TenantFout, create_tenant

    require_operator_ui(db, email)
    try:
        create_tenant(
            db,
            name=name,
            code=code,
            parent_id=int(account_id) if account_id.isdigit() else None,
            base_url=base_url,
            kind=kind,
        )
    except TenantFout as fout:
        ctx = _lijst_ctx(request, db)
        ctx["error"] = _(str(fout))
        return templates.TemplateResponse(request, "admin_tenants.html", ctx)

    ctx = _lijst_ctx(request, db)
    ctx["opgeslagen"] = True
    return templates.TemplateResponse(request, "admin_tenants.html", ctx)


@router.post(
    "/admin/tenants/{tenant_id}", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
async def tenant_opslaan(
    tenant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
):
    """The editor's one Opslaan (#1498): the module set and the settings in one
    transaction (`save_tenant`); "Modules bewaren" and its route are gone. A
    refusal shows the form again as it was sent, with the 422 both routes gave
    (#797, #1478); whether htmx shows a 4xx is an open question to Koen."""
    from app.domains.mdm.api import ModuleRefused, OngeldigeInstelling, TenantFout, save_tenant

    require_operator_ui(db, email)
    unit = next((u for u in _units(db) if u.id == tenant_id), None)
    if unit is None:
        raise HTTPException(status_code=404, detail=_("Onbekende tenant"))
    sleutels, geheim = _settings_of(unit)
    form = await request.form()
    # Only what the form carries is saved: a key that is not on it is left
    # alone, never emptied, and the module set only when the form sent its
    # checkboxes (`modules_shown`) — an empty list then means "all off".
    modules = [str(v) for v in form.getlist("modules")] if form.get("modules_shown") else None
    labels = {key: label for key, label, _h in BEKENDE_SLEUTELS}

    def again(**kwargs) -> dict:
        ctx = _editor_ctx(request, db, tenant_id, modules_on=modules, **kwargs)
        # #797: the typed values stay; throwing them away makes the message worse
        # than the mistake.
        ctx["waarden"] = {**ctx["waarden"], **{k: v for k, v in form.items() if k in labels}}
        return ctx

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
        )
    except ModuleRefused as fout:
        ctx = again(refused=(fout.module, _(str(fout))))
        return templates.TemplateResponse(request, "admin_tenant.html", ctx, status_code=422)
    except TenantFout as fout:
        ctx = again()
        ctx["error"] = _(str(fout))
        return templates.TemplateResponse(request, "admin_tenant.html", ctx, status_code=422)
    except OngeldigeInstelling as fout:
        ctx = again()
        ctx["error"] = " ".join(f"{labels.get(k, k)}: {m}" for k, m in fout.fouten.items())
        return templates.TemplateResponse(request, "admin_tenant.html", ctx, status_code=422)
    ctx = _editor_ctx(request, db, tenant_id)
    # #742: een toast in plaats van de bestaande success_banner. §2.9 schrijft één
    # bevestigingspatroon voor; twee vormen naast elkaar is precies de inconsistentie
    # die dat issue wegneemt.
    ctx["toast_opgeslagen"] = True
    return templates.TemplateResponse(request, "admin_tenant.html", ctx)
