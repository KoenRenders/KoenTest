"""Server-rendered Systeeminfo-scherm (React-exit 405-d, #405 — §21).

Read-only weergave van de gecureerde runtime/config-whitelist uit de
admin-api-composer (`app.ui.admin_api`, #444 — nooit secrets). Umami-analytics komt hier server-side uit de
settings i.p.v. NEXT_PUBLIC_*-variabelen.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import csrf_from_request, require_admin_ui
from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id
from app.ui import admin_nav, templates

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/info")


# De zes tegels, elk met het bewaarde rapport waar haar cijfer uit komt (#848).
# Het dashboard blijft op /admin en wordt CONSUMENT van rapportering in plaats van
# een tweede implementatie: dit is de landingspagina van het beheer, en die
# leeghalen betekent dat een bestuurder moet leren waar "het dashboard" nu woont.
#
# De operationele link blijft de hoofdlink van de tegel — bij "Open taken" wil je
# meestal naar de werkbank — en de doorklik naar het rapport komt eronder, niet
# ervoor in de plaats.
#
# `geld=True` op de laatste: die tegel toont een bedrag — sinds golf 7 (#913)
# via dezelfde geld-formatter als overal ("€ 45,00", §735). #848 had de oude
# punt-notatie bewust laten staan; die eigen wijziging is dit.
# F12/F13 (#996, door Koen goedgekeurd op ronde 2): één neutrale kaart voor
# elk kengetal — zes kleuren gaven gewone categorieën het gewicht van
# statussen — en de labels benoemen de daadwerkelijk getelde eenheid: een
# Member is een GEZIN, dus "Leden" telde geen leden.
DASHBOARD_TEGELS = [
    ("Gezinnen", "dashboard_members", "member_total_count",
     "/admin/leden", False),
    ("Actieve gezinnen", "dashboard_active_members", "membership_active_count",
     "/admin/leden", False),
    ("Personen (actief lid)", "dashboard_member_persons", "membership_person_unique",
     "/admin/leden", False),
    ("Komende activiteiten", "dashboard_upcoming_activities", "activity_count",
     "/admin/activiteiten", False),
    ("Open taken (werkbank)", "dashboard_open_tasks", "task_count",
     "/admin/werkbank", False),
    ("Openstaand saldo", "dashboard_outstanding", "payment_amount",
     "/admin/betalingen", True),
]


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui)):
    """Dashboard-startpagina met de kerncijfers (URL-pariteit met React /admin).

    De cijfers komen sinds #848 uit de bewaarde rapporten van het
    rapportagedomein. `app.ui.admin_api.get_stats` blijft bestaan — het is de
    JSON-API — maar het scherm rekent niet meer zelf.
    """
    from datetime import datetime

    from app.domains.reporting.api import dashboard_numbers
    from app.kernel.geld import bedrag

    # Golf 7 (#913, B3): één peilmoment voor het hele scherm — de tegels resolven
    # hun symbolische filters ("vandaag", "dit jaar") op déze ene klok, en het
    # scherm zegt eronder van wanneer de cijfers zijn.
    peilmoment = datetime.now()
    cijfers = dashboard_numbers(
        db, [(sleutel, maat) for _l, sleutel, maat, _h, _g in DASHBOARD_TEGELS],
        tenant_id=current_tenant_id.get() or DEFAULT_TENANT_ID, viewer=email,
        today=peilmoment.date())

    def _toon(sleutel: str, geld: bool):
        getal = cijfers[sleutel].value
        if getal is None:
            return "—"
        # Golf 7: de bevinding uit #848 bewust rechtgezet — €45.00 met een punt
        # werd "€ 45,00" via dezelfde formatter als overal (§735).
        return ("€ " + bedrag(getal)) if geld else getal

    tegels = [
        {"label": label, "waarde": _toon(sleutel, geld),
         "href": href,
         "rapport_href": (f"/admin/rapporten/{cijfers[sleutel].report_id}"
                          if cijfers[sleutel].report_id else None)}
        for label, sleutel, _maat, href, geld in DASHBOARD_TEGELS
    ]
    # #693: het dashboard zette een LEEG csrf-token in `hx-headers`. Landde je hier
    # en boostte je daarna naar een beheerscherm, dan hield de body die lege waarde
    # en faalde elke mutatie met een 403 — dezelfde fout als op de publieke schil,
    # en even stil.
    return templates.TemplateResponse(request, "admin_dashboard.html", {
        "nav_items": admin_nav("/admin"), "tegels": tegels,
        "peilmoment": peilmoment,
        "csrf_token": csrf_from_request(request)})


def _werkruimte_namen(db) -> dict:
    """id → naam van elke werkruimte (platform + afdelingen), voor de
    accountschermen. Eén bron: dezelfde lijst als /admin/tenants."""
    from app.domains.mdm.api import list_manageable_tenants

    return {org.id: org.name for org in list_manageable_tenants(db)}


def _mijn_werkruimtes(db, email: str) -> list:
    """De werkruimtes waar dit account iets mag (#963): de werkruimtes met een
    eigen rolrij, of álle werkruimtes voor wie een platformbrede rij heeft
    (vandaag alleen OPERATOR). Gesorteerd op id, elk als (id, naam)."""
    from app.domains.auth.api import get_user_role_rows

    rows = get_user_role_rows(db, email)
    namen = _werkruimte_namen(db)
    if any(t is None for _, t in rows):
        ids = sorted(namen)
    else:
        ids = sorted({t for _, t in rows if t is not None})
    return [(t, namen.get(t, f"Werkruimte #{t}")) for t in ids]


@router.get("/admin/profiel", response_class=HTMLResponse)
def admin_profiel(request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui)):
    """Mijn profiel (golf 9, #913): read-only — e-mail, werkruimte, en sinds
    #963 de rollen pér werkruimte, met de platformbrede rollen apart."""
    from app.domains.auth.api import get_user_role_rows

    rows = get_user_role_rows(db, email)
    namen = _werkruimte_namen(db)
    per_werkruimte: dict = {}
    for code, tenant in rows:
        if tenant is not None:
            per_werkruimte.setdefault(tenant, set()).add(code)
    return templates.TemplateResponse(request, "admin_profiel.html", {
        "nav_items": admin_nav(""), "profiel_email": email,
        "profiel_platform_rollen": sorted(
            {c for c, t in rows if t is None}),
        "profiel_werkruimtes": [
            {"naam": namen.get(t, f"Werkruimte #{t}"),
             "rollen": sorted(codes)}
            for t, codes in sorted(per_werkruimte.items())],
        "csrf_token": csrf_from_request(request)})


@router.get("/admin/accountmenu", response_class=HTMLResponse)
def admin_accountmenu(request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui)):
    """De inhoud van het accountmenu (#963): lui geladen zodra het menu
    opengaat, want of "Werkruimte wisselen" bestaat hangt aan de database en
    de schil-chrome mag geen query per paginaweergave kosten (dezelfde
    afweging als werkruimte_naam)."""
    return templates.TemplateResponse(request, "_account_menu.html", {
        "toon_wisselen": len(_mijn_werkruimtes(db, email)) > 1})


@router.get("/admin/werkruimte-wisselen", response_class=HTMLResponse)
def admin_werkruimte_wisselen(request: Request, db: Session = Depends(get_db),
                              email: str = Depends(require_admin_ui)):
    """Kies een werkruimte (#963): elke werkruimte waar dit account een rol
    heeft, met de padprefix-link die de tenantkeuze zet (§7). De actieve
    werkruimte staat gemarkeerd i.p.v. weggelaten — je wil zien waar je bent."""
    from app.domains.mdm.api import list_manageable_tenants, platform_tenant_id
    from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id
    from app.kernel.tenant_config import tenant_base_url

    actief = current_tenant_id.get() or DEFAULT_TENANT_ID
    platform = platform_tenant_id(db)
    codes = {org.id: org.code for org in list_manageable_tenants(db)}

    def _href(t: int) -> str:
        # Afdelingen wisselen via de padprefix (§7 — werkt ook wanneer alle
        # werkruimtes op één host wonen); het platform kent geen prefix
        # (tenant_codes bevat alleen UNITs) en gaat via zijn eigen host.
        if t == platform:
            return f"{tenant_base_url(db, tenant_id=t)}/admin"
        return f"/{codes.get(t, '')}/admin"

    keuzes = [{"naam": naam, "actief": t == actief, "href": _href(t)}
              for t, naam in _mijn_werkruimtes(db, email)]
    return templates.TemplateResponse(request, "admin_werkruimte_wisselen.html", {
        "nav_items": admin_nav(""), "keuzes": keuzes,
        "csrf_token": csrf_from_request(request)})


@router.get("/admin/info", response_class=HTMLResponse)
def admin_info(request: Request, db: Session = Depends(get_db),
               email: str = Depends(require_admin_ui)):
    from app.kernel.tenant_config import tenant_umami_src, umami_tracking
    from app.ui.admin_api import get_system_info

    info = get_system_info(_admin=None)  # type: ignore[arg-type]
    # #808: dezelfde functie als de publieke schil, zodat dit scherm niet iets
    # anders kan beweren dan er gebeurt. Vóór #808 stond hier `bool(src and id)` en
    # dat toetste of er tekst stond — het scherm meldde "geconfigureerd" terwijl er
    # sinds de React-exit nergens een script gerenderd werd.
    umami_src, umami_website_id = umami_tracking(db)
    # De dashboard-link hangt alleen aan de script-URL: de historische cijfers zijn
    # ook te bekijken wanneer het meten (nog) niet aan staat.
    losse_src = tenant_umami_src(db)
    umami_dashboard = losse_src.removesuffix("script.js") if losse_src else ""
    return templates.TemplateResponse(request, "admin_info.html", {
        "nav_items": NAV, "info": info,
        "umami_actief": bool(umami_src and umami_website_id),
        "umami_dashboard": umami_dashboard,
        "umami_website_id": umami_website_id,
    })
