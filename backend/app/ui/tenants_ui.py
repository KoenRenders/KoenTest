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

import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (  # noqa: F401
    require_operator_ui,
    csrf_from_request, get_user_roles, require_admin_ui, require_csrf,
)
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
    # #924: de sociale links staan bij de ORGANISATIE — ze bestaan ook als de
    # vereniging geen site heeft. Hier laten staan zou een tweede bewerkbare bron
    # zijn.
    ("base_url", "Canonieke URL", "Publieke origin voor links in mails/Mollie/SEO, bv. https://raakmillegem.be."),
    ("privacy_url", "Privacyverklaring-link", "Footer-link naar je privacyverklaring. Leeg = niet tonen."),
    ("mail_mode", "Mail-modus", "'send' (default) of 'log_only' (mails enkel loggen — demo)."),
    ("noindex", "Noindex", "'1' = niet indexeren door zoekmachines (demo)."),
    ("language", "Taal", "Catalogustaal, bv. nl_BE (default)."),
    ("membership_price_full", "Lidgeld volledig", "Bedrag, bv. 35.00. Leeg = .env-default."),
    ("membership_price_half", "Lidgeld half", "Bedrag, bv. 17.50."),
    ("membership_half_price_start_md", "Halfprijs van", "MM-DD, bv. 04-16."),
    ("membership_half_price_end_md", "Halfprijs tot", "MM-DD, bv. 09-16."),
    ("membership_next_year_from_md", "Volgend jaar vanaf", "MM-DD, bv. 09-17."),
    ("membership_renewal_start_md", "Hernieuwen vanaf", "MM-DD; leeg = enkel bij verlopen lidmaatschap."),
    # #924: rekeningnummer en begunstigde staan bij de ORGANISATIE. Ze hier laten
    # staan "voor het geval dat" zou een tweede bewerkbare bron zijn — dan is het
    # veld verplaatst in plaats van weggenomen.
    ("payment_term_days", "Betaaltermijn (dagen)", "Aantal dagen voor een overschrijving. Default 7."),
    ("gmail_user", "Gmail-gebruiker", "Afzender-account voor uitgaande mail (SMTP). Leeg = .env-default."),
    ("gmail_from", "Afzender (From)", "Getoonde afzender; leeg = de Gmail-gebruiker."),
    ("umami_src", "Umami script-URL", "bv. https://stats.example/script.js. Leeg = geen webstatistieken."),
    ("umami_website_id", "Umami Website-ID", "Het Umami-site-ID (geen secret)."),
    ("max_item_quantity", "Max. aantal per item", "Inschrijvingslimiet per item. Default 50."),
    ("max_registrations_per_email", "Max. inschrijvingen per e-mail", "Per activiteit. Default 3."),
    ("admin_chat_enabled", "Raakje in de backoffice",
     "'1' = het bestuur mag Raakje vragen stellen over de eigen cijfers. Leeg = uit. "
     "Werkt enkel als ADMIN_CHAT_ENABLED ook aan staat (#917)."),
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
    ("gmail_app_password", "Gmail app-wachtwoord", "Versleuteld opgeslagen; wordt nooit teruggetoond."),
]


# #854: sleutels die een platform-tenant NIET aangeboden krijgt. Een platform heeft
# geen leden en geen activiteiten, dus geen lidgeld en geen inschrijvingslimieten.
# Bood het scherm ze toch aan, dan vult iemand ooit een lidgeld in voor het platform,
# en dan staat er een waarde waarvan later niemand weet waarom.
LEDENSLEUTELS = {
    "membership_price_full", "membership_price_half",
    "membership_half_price_start_md", "membership_half_price_end_md",
    "membership_next_year_from_md", "membership_renewal_start_md",
    "max_item_quantity", "max_registrations_per_email",
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
        units = [u for u in units
                 if naald in (u.name or "").lower() or naald in (u.code or "").lower()]
    if status == "actief":
        units = [u for u in units if u.is_active]
    elif status == "inactief":
        units = [u for u in units if not u.is_active]
    accounts = list_accounts(db)
    return {"nav_items": admin_nav("/admin/tenants"), "units": units,
            "accounts": accounts, "q": zoek, "status": status,
            "error": None, "opgeslagen": False,
            "csrf_token": csrf_from_request(request)}


def _editor_ctx(request: Request, db: Session, tenant_id: int) -> dict:
    from app.kernel.tenant_config import get_setting
    from app.domains.mdm.api import secrets_gezet as _secrets_gezet

    unit = next((u for u in _units(db) if u.id == tenant_id), None)
    if unit is None:
        raise HTTPException(status_code=404, detail=_("Onbekende tenant"))
    # #854: een platform-tenant krijgt de ledenvelden niet te zien.
    sleutels = [rij for rij in BEKENDE_SLEUTELS
                if not (unit.org_type == "PLATFORM" and rij[0] in LEDENSLEUTELS)]
    waarden = {key: get_setting(db, key, tenant_id=tenant_id) or ""
               for key, _label, _hulp in sleutels}
    secrets_gezet = _secrets_gezet(
        db, tenant_id, [key for key, _label, _hulp in GEHEIME_SLEUTELS])
    return {"nav_items": admin_nav("/admin/tenants"), "unit": unit,
            "tenant_id": tenant_id, "sleutels": sleutels,
            "geheime_sleutels": GEHEIME_SLEUTELS, "waarden": waarden,
            "secrets_gezet": secrets_gezet, "error": None, "opgeslagen": False,
            "csrf_token": csrf_from_request(request)}


@router.get("/admin/instellingen")
def instellingen_verhuisd():
    """De aparte Instellingen-pagina is opgegaan in /admin/tenants (#581).

    301 in plaats van verwijderen: bestaande bladwijzers en links blijven werken.
    """
    return RedirectResponse("/admin/tenants", status_code=301)


@router.get("/admin/tenants", response_class=HTMLResponse)
def tenants(request: Request, db: Session = Depends(get_db),
            email: str = Depends(require_admin_ui)):
    require_operator_ui(db, email)
    # De filterbalk haalt enkel de kaarten op; een pagina-swap zou het zoekveld
    # tijdens het typen vervangen en de focus wegnemen.
    sjabloon = ("_tn_kaarten.html" if is_fragment_request(request)
                else "admin_tenants.html")
    return templates.TemplateResponse(request, sjabloon, _lijst_ctx(request, db))


@router.get("/admin/tenants/nieuw", response_class=HTMLResponse)
def tenant_nieuw(request: Request, db: Session = Depends(get_db),
                 email: str = Depends(require_admin_ui)):
    """Aanmaken als volledige pagina (#627, §2.8) i.p.v. een modal.

    Hergebruikt de contextbouwer van de lijst voor de accounts-dropdown.
    """
    return templates.TemplateResponse(request, "admin_tenant_nieuw.html", _lijst_ctx(request, db))


@router.get("/admin/tenants/{tenant_id}", response_class=HTMLResponse)
def tenant_editor(tenant_id: int, request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui)):
    require_operator_ui(db, email)
    return templates.TemplateResponse(request, "admin_tenant.html",
                                      _editor_ctx(request, db, tenant_id))


@router.post("/admin/tenants", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def tenant_aanmaken(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui),
                    name: str = Form(""), code: str = Form(""),
                    account_id: str = Form(""), base_url: str = Form("")):
    from app.domains.mdm.api import TenantFout, create_tenant

    require_operator_ui(db, email)
    try:
        create_tenant(db, name=name, code=code,
                      parent_id=int(account_id) if account_id.isdigit() else None,
                      base_url=base_url)
    except TenantFout as fout:
        ctx = _lijst_ctx(request, db)
        ctx["error"] = _(str(fout))
        return templates.TemplateResponse(request, "admin_tenants.html", ctx)

    ctx = _lijst_ctx(request, db)
    ctx["opgeslagen"] = True
    return templates.TemplateResponse(request, "admin_tenants.html", ctx)


@router.post("/admin/tenants/{tenant_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def tenant_opslaan(tenant_id: int, request: Request,
                         db: Session = Depends(get_db),
                         email: str = Depends(require_admin_ui)):
    from app.domains.mdm.api import OngeldigeInstelling, update_tenant_settings

    require_operator_ui(db, email)
    if tenant_id not in {u.id for u in _units(db)}:
        raise HTTPException(status_code=404, detail=_("Onbekende tenant"))
    form = await request.form()
    # #971: enkel nog de instellingen van de site. Wat de organisatie IS, wordt op
    # `/admin/organisaties` bewerkt — één scherm per feit.
    try:
        update_tenant_settings(
            db, tenant_id, form,
            known=[key for key, _l, _h in BEKENDE_SLEUTELS],
            secret=[key for key, _l, _h in GEHEIME_SLEUTELS])
    except OngeldigeInstelling as fout:
        # #797: het formulier terug tonen mét de ingetypte waarden. Ze wegwerpen zou
        # betekenen dat één tikfout in een bedrag het hele scherm leegveegt, en dan
        # is de melding erger dan de fout.
        ctx = _editor_ctx(request, db, tenant_id)
        labels = {key: label for key, label, _h in BEKENDE_SLEUTELS}
        ctx["error"] = " ".join(f"{labels.get(k, k)}: {m}" for k, m in fout.fouten.items())
        ctx["waarden"] = {**ctx["waarden"],
                          **{k: v for k, v in form.items() if k in labels}}
        return templates.TemplateResponse(request, "admin_tenant.html", ctx,
                                          status_code=422)
    ctx = _editor_ctx(request, db, tenant_id)
    # #742: een toast in plaats van de bestaande success_banner. §2.9 schrijft één
    # bevestigingspatroon voor; twee vormen naast elkaar is precies de inconsistentie
    # die dat issue wegneemt.
    ctx["toast_opgeslagen"] = True
    return templates.TemplateResponse(request, "admin_tenant.html", ctx)
