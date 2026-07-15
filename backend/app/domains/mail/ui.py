"""Server-rendered e-maillogscherm (fase 1, #399 — §21).

Zelfde inzage als de admin-API (#328): filterbaar overzicht + verwijderen.
Sessie-auth (HttpOnly-cookie) + CSRF, zoals de werkbank.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf
from app.domains.mail.models import EMAIL_STATUSES, EMAIL_TYPES, EmailLog
from app.ui import admin_nav, templates

router = APIRouter(include_in_schema=False)

PAGE_SIZE = 50


def _ctx(request: Request, db: Session) -> dict:
    email_type = (request.query_params.get("email_type") or "").strip()
    status = (request.query_params.get("status") or "").strip()
    q = db.query(EmailLog)
    if email_type:
        q = q.filter(EmailLog.email_type == email_type)
    if status:
        q = q.filter(EmailLog.status == status)
    try:
        page = max(1, int(request.query_params.get("page", "1")))
    except ValueError:
        page = 1
    # Eén rij extra ophalen dan de paginagrootte om te weten of er nog een pagina is.
    rows = (q.order_by(EmailLog.created_at.desc())
            .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE + 1).all())
    has_next = len(rows) > PAGE_SIZE
    rows = rows[:PAGE_SIZE]
    raw = request.cookies.get(SESSION_COOKIE) or ""
    return {
        "csrf_token": csrf_token_for(raw),
        "rows": rows,
        "email_type": email_type,
        "status": status,
        "page": page,
        "has_prev": page > 1,
        "has_next": has_next,
        "email_types": EMAIL_TYPES,
        "email_statuses": EMAIL_STATUSES,
        "nav_items": admin_nav("/admin/e-maillog"),
    }


@router.get("/admin/e-maillog", response_class=HTMLResponse)
def email_log_page(request: Request, db: Session = Depends(get_db),
                   email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "email_log.html", _ctx(request, db))


@router.get("/admin/e-maillog/lijst", response_class=HTMLResponse)
def email_log_lijst(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui)):
    """Fragment voor filterwissels (htmx)."""
    return templates.TemplateResponse(request, "_email_log_lijst.html", _ctx(request, db))


@router.post("/admin/e-maillog/{log_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def email_log_verwijderen(log_id: int, request: Request, db: Session = Depends(get_db),
                          email: str = Depends(require_admin_ui)):
    row = db.query(EmailLog).filter(EmailLog.id == log_id).first()
    if row is not None:
        db.delete(row)
        db.commit()
    return templates.TemplateResponse(request, "_email_log_lijst.html", _ctx(request, db))


@router.get("/admin/emails", response_class=HTMLResponse)
def emails_redirect(request: Request):
    """URL-pariteit (React-exit 405-e): het oude React-pad → /admin/e-maillog."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/admin/e-maillog", status_code=302)
