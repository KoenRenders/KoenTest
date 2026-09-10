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
# `geld=True` op de laatste: die tegel toont een bedrag. LET OP, en dit is bewust
# NIET rechtgezet in #848: het bestaande scherm schrijft `€45.00` met een punt,
# terwijl §735 de komma voorschrijft en `ui.geld` daarvoor bestaat. Dit issue
# verplaatst waar het cijfer vandaan komt en verandert niets aan wat er staat;
# de opmaak is als bevinding gemeld en hoort in een eigen wijziging.
DASHBOARD_TEGELS = [
    ("Leden", "dashboard_members", "member_total_count",
     "bg-blue-50 text-blue-700", "/admin/leden", False),
    ("Actieve leden", "dashboard_active_members", "membership_active_count",
     "bg-green-50 text-green-800", "/admin/leden", False),
    ("Leden (personen)", "dashboard_member_persons", "membership_person_unique",
     "bg-teal-50 text-teal-800", "/admin/leden", False),
    ("Komende activiteiten", "dashboard_upcoming_activities", "activity_count",
     "bg-purple-50 text-purple-800", "/admin/activiteiten", False),
    ("Open taken (werkbank)", "dashboard_open_tasks", "task_count",
     "bg-yellow-50 text-yellow-800", "/admin/werkbank", False),
    ("Openstaand saldo", "dashboard_outstanding", "payment_outstanding",
     "bg-orange-50 text-orange-800", "/admin/betalingen", True),
]


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui)):
    """Dashboard-startpagina met de kerncijfers (URL-pariteit met React /admin).

    De cijfers komen sinds #848 uit de bewaarde rapporten van het
    rapportagedomein. `app.ui.admin_api.get_stats` blijft bestaan — het is de
    JSON-API — maar het scherm rekent niet meer zelf.
    """
    from app.domains.reporting.api import dashboard_numbers

    cijfers = dashboard_numbers(
        db, [(sleutel, maat) for _l, sleutel, maat, _k, _h, _g in DASHBOARD_TEGELS],
        tenant_id=current_tenant_id.get() or DEFAULT_TENANT_ID, viewer=email)

    def _toon(sleutel: str, geld: bool):
        getal = cijfers[sleutel].value
        if getal is None:
            return "—"
        return ("€%.2f" % float(getal)) if geld else getal

    tegels = [
        {"label": label, "waarde": _toon(sleutel, geld), "kleur": kleur,
         "href": href,
         "rapport_href": (f"/admin/rapporten/{cijfers[sleutel].report_id}"
                          if cijfers[sleutel].report_id else None)}
        for label, sleutel, _maat, kleur, href, geld in DASHBOARD_TEGELS
    ]
    # #693: het dashboard zette een LEEG csrf-token in `hx-headers`. Landde je hier
    # en boostte je daarna naar een beheerscherm, dan hield de body die lege waarde
    # en faalde elke mutatie met een 403 — dezelfde fout als op de publieke schil,
    # en even stil.
    return templates.TemplateResponse(request, "admin_dashboard.html", {
        "nav_items": admin_nav("/admin"), "tegels": tegels,
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
