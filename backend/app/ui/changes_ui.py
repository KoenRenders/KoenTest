"""Server-rendered Wijzigingen-scherm (React-exit 405-d, #405 — §21).

Twee weergaven over de append-only history: de ledendata-wijzigingen sinds een
datum (voor manuele overname in Raak Nationaal, incl. .ods-export) en de
uniforme audit-feed met groep-/actorfilter. Composer-module: leest via de
bestaande admin-routerfuncties (oude wereld), geen domein-internals.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, require_admin_ui
from app.ui import admin_nav, templates

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/ledenwijzigingen")


def _since(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.today() - timedelta(days=30)


def _ctx(request: Request, db: Session, since: str, group: str, actor: str) -> dict:
    from app.routers.admin import list_all_changes, list_member_changes

    vanaf = _since(since)
    feed = list_all_changes(since=vanaf, group=group or None, actor=actor or None,
                            db=db, _admin=None)  # type: ignore[arg-type]
    return {
        "since": vanaf.isoformat(),
        "group": group, "actor": actor,
        "member_rows": list_member_changes(since=vanaf, db=db, _admin=None),  # type: ignore[arg-type]
        "groups": feed["groups"], "feed_rows": feed["rows"],
        "csrf_token": csrf_token_for(request.cookies.get(SESSION_COOKIE) or ""),
    }


@router.get("/admin/ledenwijzigingen", response_class=HTMLResponse)
def admin_ledenwijzigingen(request: Request, since: str = "", group: str = "",
                           actor: str = "", db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui)):
    ctx = _ctx(request, db, since, group, actor)
    template = ("_lw_inhoud.html" if request.headers.get("hx-request")
                else "admin_ledenwijzigingen.html")
    if template == "admin_ledenwijzigingen.html":
        ctx["nav_items"] = NAV
    return templates.TemplateResponse(request, template, ctx)


@router.get("/admin/ledenwijzigingen/export")
def ledenwijzigingen_export(request: Request, since: str = "",
                            db: Session = Depends(get_db),
                            email: str = Depends(require_admin_ui)) -> Response:
    from app.routers.admin import export_member_changes

    return export_member_changes(since=_since(since), db=db, _admin=None)  # type: ignore[arg-type]
