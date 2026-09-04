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
from app.ui import admin_nav, is_fragment_request, templates

router = APIRouter(include_in_schema=False)

# Bekende sleutels: (key, label, hulptekst). Secrets staan apart.
BEKENDE_SLEUTELS = [
    ("display_name", "Naam", "Merk-/afzendnaam (mails, footer, titel). Default: Raak Millegem."),
    ("tagline", "Tagline", "Ondertitel in de header. Leeg = geen ondertitel (#519)."),
    ("base_url", "Canonieke URL", "Publieke origin voor links in mails/Mollie/SEO, bv. https://raakmillegem.be."),
    ("facebook_url", "Facebook-link", "Footer-link naar je Facebook-pagina. Leeg = geen Facebook-icoon (#519)."),
    ("instagram_url", "Instagram-link", "Footer-link. Leeg = niet tonen."),
    ("tiktok_url", "TikTok-link", "Footer-link. Leeg = niet tonen."),
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
    ("payment_iban", "Rekeningnummer (IBAN)", "Voor de overschrijvingsinstructies in de bevestigingsmail. Leeg = .env-default."),
    ("payment_beneficiary", "Begunstigde", "Naam op de overschrijving. Leeg = .env-default."),
    ("payment_term_days", "Betaaltermijn (dagen)", "Aantal dagen voor een overschrijving. Default 7."),
    ("gmail_user", "Gmail-gebruiker", "Afzender-account voor uitgaande mail (SMTP). Leeg = .env-default."),
    ("gmail_from", "Afzender (From)", "Getoonde afzender; leeg = de Gmail-gebruiker."),
    ("umami_src", "Umami script-URL", "bv. https://stats.example/script.js. Leeg = geen webstatistieken."),
    ("umami_website_id", "Umami Website-ID", "Het Umami-site-ID (geen secret)."),
    ("max_item_quantity", "Max. aantal per item", "Inschrijvingslimiet per item. Default 50."),
    ("max_registrations_per_email", "Max. inschrijvingen per e-mail", "Per activiteit. Default 3."),
]

GEHEIME_SLEUTELS = [
    ("mollie_api_key", "Mollie API-key", "Versleuteld opgeslagen; wordt nooit teruggetoond."),
    ("gmail_app_password", "Gmail app-wachtwoord", "Versleuteld opgeslagen; wordt nooit teruggetoond."),
]


def _units(db: Session, *, alleen_actief: bool = False):
    from app.domains.mdm.api import list_units

    return list_units(db, alleen_actief=alleen_actief)


def _lijst_ctx(request: Request, db: Session) -> dict:
    """Lijst-index (C1): zoeken op naam/code, filter op status."""
    from app.domains.mdm.api import list_accounts

    zoek = (request.query_params.get("q") or "").strip()
    status = (request.query_params.get("status") or "").strip()
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
    waarden = {key: get_setting(db, key, tenant_id=tenant_id) or ""
               for key, _label, _hulp in BEKENDE_SLEUTELS}
    secrets_gezet = _secrets_gezet(
        db, tenant_id, [key for key, _label, _hulp in GEHEIME_SLEUTELS])
    return {"nav_items": admin_nav("/admin/tenants"), "unit": unit,
            "tenant_id": tenant_id, "sleutels": BEKENDE_SLEUTELS,
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
    from app.domains.mdm.api import update_tenant_settings

    require_operator_ui(db, email)
    if tenant_id not in {u.id for u in _units(db)}:
        raise HTTPException(status_code=404, detail=_("Onbekende tenant"))
    form = await request.form()
    update_tenant_settings(
        db, tenant_id, form,
        known=[key for key, _l, _h in BEKENDE_SLEUTELS],
        secret=[key for key, _l, _h in GEHEIME_SLEUTELS])
    ctx = _editor_ctx(request, db, tenant_id)
    ctx["opgeslagen"] = True
    return templates.TemplateResponse(request, "admin_tenant.html", ctx)
