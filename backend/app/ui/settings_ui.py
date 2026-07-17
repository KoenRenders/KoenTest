"""Tenant-instellingen-scherm (/admin/instellingen) — OPERATOR-only (#406/#407).

Beheer van de per-tenant config zonder server-commando's: branding, adressen,
mail-modus, taal, lidmaatschapsbedragen en de Mollie-key (secret: nooit
teruggetoond, enkel "gezet"). Leeg opslaan = sleutel wissen → de .env-default
geldt weer. Composer-module: leest/schrijft via de kernel-config-store.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import csrf_from_request, require_admin_ui, require_csrf
from app.i18n import _
from app.ui import admin_nav, templates

router = APIRouter(include_in_schema=False)

# Bekende sleutels: (key, label, hulptekst). Secrets staan apart.
BEKENDE_SLEUTELS = [
    ("display_name", "Naam", "Merk-/afzendnaam (mails, footer, titel). Default: Raak Millegem."),
    ("tagline", "Tagline", "Ondertitel in de header. Default: Beleef meer in Millegem."),
    ("base_url", "Canonieke URL", "Publieke origin voor links in mails/Mollie/SEO, bv. https://raakmillegem.be."),
    ("facebook_url", "Facebook-link", "Footer-link. Default: de Millegem-pagina."),
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


def _require_operator(db: Session, email: str) -> None:
    from app.domains.auth.api import get_user_roles

    if "OPERATOR" not in get_user_roles(db, email):
        raise HTTPException(status_code=403,
                            detail=_("Alleen de platformbeheerder (OPERATOR) mag tenant-instellingen wijzigen."))


def _units(db: Session):
    from app.domains.mdm.api import Organization

    return (db.query(Organization)
            .filter(Organization.org_type == "UNIT", Organization.is_active == True)  # noqa: E712
            .order_by(Organization.id).all())


def _ctx(request: Request, db: Session, tenant_id: int) -> dict:
    from app.kernel.tenant_config import TenantSetting, get_setting

    units = _units(db)
    if tenant_id not in {u.id for u in units}:
        tenant_id = units[0].id if units else tenant_id
    waarden = {key: get_setting(db, key, tenant_id=tenant_id) or ""
               for key, _label, _hulp in BEKENDE_SLEUTELS}
    secrets_gezet = {
        key: bool(db.query(TenantSetting)
                  .filter(TenantSetting.tenant_id == tenant_id,
                          TenantSetting.key == key,
                          TenantSetting.value_encrypted.isnot(None)).first())
        for key, _label, _hulp in GEHEIME_SLEUTELS}
    return {"nav_items": admin_nav("/admin/instellingen"), "units": units,
            "tenant_id": tenant_id, "sleutels": BEKENDE_SLEUTELS,
            "geheime_sleutels": GEHEIME_SLEUTELS, "waarden": waarden,
            "secrets_gezet": secrets_gezet, "error": None, "opgeslagen": False,
            "csrf_token": csrf_from_request(request)}


@router.get("/admin/instellingen", response_class=HTMLResponse)
def instellingen(request: Request, tenant: int = 0, db: Session = Depends(get_db),
                 email: str = Depends(require_admin_ui)):
    _require_operator(db, email)
    return templates.TemplateResponse(request, "admin_instellingen.html",
                                      _ctx(request, db, tenant))


@router.post("/admin/instellingen/{tenant_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def instellingen_opslaan(tenant_id: int, request: Request,
                               db: Session = Depends(get_db),
                               email: str = Depends(require_admin_ui)):
    from app.kernel.tenant_config import set_setting

    _require_operator(db, email)
    if tenant_id not in {u.id for u in _units(db)}:
        raise HTTPException(status_code=404, detail=_("Onbekende tenant"))
    form = await request.form()
    for key, _label, _hulp in BEKENDE_SLEUTELS:
        raw = form.get(key)
        waarde = raw.strip() if isinstance(raw, str) else ""
        set_setting(db, key, waarde or None, tenant_id=tenant_id)
    for key, _label, _hulp in GEHEIME_SLEUTELS:
        raw = form.get(key)
        nieuw = raw.strip() if isinstance(raw, str) else ""
        if form.get(f"{key}_wissen"):
            set_setting(db, key, None, tenant_id=tenant_id)
        elif nieuw:  # leeg laten = ongewijzigd
            set_setting(db, key, nieuw, secret=True, tenant_id=tenant_id)
    db.commit()
    ctx = _ctx(request, db, tenant_id)
    ctx["opgeslagen"] = True
    return templates.TemplateResponse(request, "admin_instellingen.html", ctx)
