"""Server-rendered Systeeminfo-scherm (React-exit 405-d, #405 — §21).

Read-only weergave van de gecureerde runtime/config-whitelist uit de
admin-router (nooit secrets). Umami-analytics komt hier server-side uit de
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


@router.get("/admin/info", response_class=HTMLResponse)
def admin_info(request: Request, db: Session = Depends(get_db),
               email: str = Depends(require_admin_ui)):
    from app.config import settings
    from app.routers.admin import get_system_info

    info = get_system_info(_admin=None)  # type: ignore[arg-type]
    umami_dashboard = settings.umami_src.removesuffix("script.js") if settings.umami_src else ""
    return templates.TemplateResponse(request, "admin_info.html", {
        "nav_items": NAV, "info": info,
        "umami_configured": bool(settings.umami_src and settings.umami_website_id),
        "umami_dashboard": umami_dashboard,
        "umami_website_id": settings.umami_website_id,
    })
