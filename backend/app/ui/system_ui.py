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
from app.domains.auth.api import require_admin_ui
from app.ui import admin_nav, templates

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/info")


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui)):
    """Dashboard-startpagina met de kerncijfers (URL-pariteit met React /admin)."""
    from app.ui.admin_api import get_stats

    stats = get_stats(db=db, _admin=None)  # type: ignore[arg-type]
    tegels = [
        ("Leden", stats["members"], "bg-blue-50 text-blue-800", "/admin/leden"),
        ("Actieve leden", stats["active_members"], "bg-green-50 text-green-800", "/admin/leden"),
        ("Leden (personen)", stats["active_member_persons"], "bg-teal-50 text-teal-800", "/admin/leden"),
        ("Komende activiteiten", stats["upcoming_activities"], "bg-purple-50 text-purple-800", "/admin/activiteiten"),
        ("Open taken (werkbank)", stats["open_tasks"], "bg-yellow-50 text-yellow-800", "/admin/werkbank"),
        ("Openstaand saldo", "€%.2f" % stats["outstanding_balance"], "bg-orange-50 text-orange-800", "/admin/betalingen"),
    ]
    return templates.TemplateResponse(request, "admin_dashboard.html", {
        "nav_items": admin_nav("/admin"), "tegels": tegels})


@router.get("/admin/info", response_class=HTMLResponse)
def admin_info(request: Request, db: Session = Depends(get_db),
               email: str = Depends(require_admin_ui)):
    from app.kernel.tenant_config import tenant_umami_src, tenant_umami_website_id
    from app.ui.admin_api import get_system_info

    info = get_system_info(_admin=None)  # type: ignore[arg-type]
    umami_src = tenant_umami_src(db)
    umami_website_id = tenant_umami_website_id(db)
    umami_dashboard = umami_src.removesuffix("script.js") if umami_src else ""
    return templates.TemplateResponse(request, "admin_info.html", {
        "nav_items": NAV, "info": info,
        "umami_configured": bool(umami_src and umami_website_id),
        "umami_dashboard": umami_dashboard,
        "umami_website_id": umami_website_id,
    })
