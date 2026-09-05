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
from app.domains.mail.api import (EMAIL_STATUSES, EMAIL_TYPES,
                                  delete_email_log, list_email_log)
from app.ui import admin_nav, templates

router = APIRouter(include_in_schema=False)

PAGE_SIZE = 50


_TYPE_LABELS = {
    "membership_confirmation": "Lidmaatschap",
    "activity_confirmation": "Activiteit",
    "idea_ack": "Idee (bevestiging)",
    "idea_board": "Idee (bestuur)",
    "magic_link": "Inloglink",
    "member_contact_notice": "Contactbericht",
    "form_confirmation": "Formulier (bevestiging)",
    "other": "Overig",
}
_STATUS_LABELS = {"sent": "Verstuurd", "failed": "Mislukt", "skipped": "Overgeslagen"}


def _ctx(request: Request, db: Session) -> dict:
    email_type = (request.query_params.get("email_type") or "").strip()
    status = (request.query_params.get("status") or "").strip()
    recipient = (request.query_params.get("recipient") or "").strip()
    try:
        page = max(1, int(request.query_params.get("page", "1")))
    except ValueError:
        page = 1
    rows, has_next = list_email_log(db, email_type=email_type, status=status,
                                    recipient=recipient, page=page,
                                    page_size=PAGE_SIZE)
    raw = request.cookies.get(SESSION_COOKIE) or ""
    return {
        "csrf_token": csrf_token_for(raw),
        "rows": rows,
        "email_type": email_type,
        "status": status,
        "recipient": recipient,
        "page": page,
        "has_prev": page > 1,
        "has_next": has_next,
        "email_types": EMAIL_TYPES,
        "email_statuses": EMAIL_STATUSES,
        "type_labels": _TYPE_LABELS,
        "status_labels": _STATUS_LABELS,
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
    delete_email_log(db, log_id)
    return templates.TemplateResponse(request, "_email_log_lijst.html", _ctx(request, db))


@router.get("/admin/emails", response_class=HTMLResponse)
def emails_redirect(request: Request):
    """URL-pariteit (React-exit 405-e): het oude React-pad → /admin/e-maillog."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/admin/e-maillog", status_code=302)
