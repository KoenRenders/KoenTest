"""Server-rendered Wijzigingen-scherm (React-exit 405-d, #405 — §21).

Eén primaire weergave over de append-only history (#512, v1.4-pariteit): het
uniforme audit-logboek met groep-/actorfilter. De ledendata-wijzigingen voor
manuele overname in Raak Nationaal blijven beschikbaar als .ods-export (aparte
route), niet meer als altijd-zichtbare tabel. Composer-module: leest via de
audit-facade (`app.domains.audit.api`, #444), geen domein-internals.
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


PER_PAGE = 50  # §2.5: server-side, 50 per pagina zodra een lijst kan groeien.


def _ctx(request: Request, db: Session, since: str, group: str, actor: str,
         page: int = 1) -> dict:
    from app.domains.audit.api import GROUPS, all_changes_since

    vanaf = _since(since)
    # #512 (v1.4-pariteit): één algemeen audit-logboek als primaire, gefilterde
    # tabel. De ledendata-mutaties voor Raak Nationaal blijven als .ods-export
    # (aparte route), niet meer als altijd-zichtbare tabel bovenaan.
    alle = all_changes_since(db, vanaf, group=group or None, actor=actor or None)

    # Paginering (#620). Bewust ná het sorteren en in Python: all_changes_since()
    # verenigt ~10 history-tabellen in Python, dus een server-side LIMIT/OFFSET op
    # één query bestaat niet. De "Vanaf"-datum blijft de echte begrenzing en bij
    # deze volumes volstaat dit. Groeit het logboek fors, dan is een echte UNION ALL
    # in SQL de duurzame oplossing — dat is opvolging, niet iets om nu te bouwen.
    totaal = len(alle)
    page = max(1, page)
    feed_rows = alle[(page - 1) * PER_PAGE:page * PER_PAGE]
    return {
        "since": vanaf.isoformat(),
        "group": group, "actor": actor,
        "groups": GROUPS, "feed_rows": feed_rows,
        "page": page, "per_page": PER_PAGE, "totaal": totaal,
        "csrf_token": csrf_token_for(request.cookies.get(SESSION_COOKIE) or ""),
    }


@router.get("/admin/ledenwijzigingen", response_class=HTMLResponse)
def admin_ledenwijzigingen(request: Request, since: str = "", group: str = "",
                           actor: str = "", page: int = 1,
                           db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui)):
    ctx = _ctx(request, db, since, group, actor, page)
    template = ("_lw_inhoud.html" if request.headers.get("hx-request")
                else "admin_ledenwijzigingen.html")
    if template == "admin_ledenwijzigingen.html":
        ctx["nav_items"] = NAV
    return templates.TemplateResponse(request, template, ctx)


@router.get("/admin/ledenwijzigingen/export")
def ledenwijzigingen_export(request: Request, since: str = "",
                            db: Session = Depends(get_db),
                            email: str = Depends(require_admin_ui)) -> Response:
    from app.domains.audit.api import build_member_changes_ods, member_changes_since

    vanaf = _since(since)
    content = build_member_changes_ods(member_changes_since(db, vanaf))
    return Response(
        content=content,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={"Content-Disposition": f'attachment; filename="ledenwijzigingen-vanaf-{vanaf}.ods"'},
    )
