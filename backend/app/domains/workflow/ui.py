"""Werkbank-embryo (#398, §20.5): open taken tonen, behartigen, sluiten door
beslissing. Rol-gefilterd; verversen via htmx-polling (§20.5 — geen SSE)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.workflow import api
from app.ui import templates
from app.domains.auth.api import csrf_token_for, require_admin_ui, require_csrf, SESSION_COOKIE

router = APIRouter(include_in_schema=False)


def _ctx(request: Request, db: Session, email: str) -> dict:
    from app.domains.auth.api import get_user_roles

    roles = sorted(get_user_roles(db, email))
    raw = request.cookies.get(SESSION_COOKIE) or ""
    return {
        "csrf_token": csrf_token_for(raw),
        "roles": roles,
        "tasks": api.open_tasks(db, roles),
        "nav_items": [
            {"href": "/admin/werkbank", "label": "Werkbank", "active": True},
            {"href": "/admin/e-maillog", "label": "E-maillog", "active": False},
        ],
    }


@router.get("/admin/werkbank", response_class=HTMLResponse)
def werkbank(request: Request, db: Session = Depends(get_db),
             email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "werkbank.html", _ctx(request, db, email))


@router.get("/admin/werkbank/lijst", response_class=HTMLResponse)
def werkbank_lijst(request: Request, db: Session = Depends(get_db),
                   email: str = Depends(require_admin_ui)):
    """Polling-fragment: enkel de takenlijst (elke 30s ververst, §20.5)."""
    return templates.TemplateResponse(request, "_werkbank_lijst.html", _ctx(request, db, email))


@router.get("/admin/werkbank/taken/{task_id}", response_class=HTMLResponse)
def taak_detail(task_id: int, request: Request, db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)):
    task = api.get_task(db, task_id)
    detail_rows: list[tuple[str, str]] = []
    if task and task.subject_type == "form_submission":
        from app.domains.forms.api import submission_view

        detail_rows = submission_view(db, task.subject_id)
    raw = request.cookies.get(SESSION_COOKIE) or ""
    return templates.TemplateResponse(request, "_werkbank_detail.html", {
        "task": task, "detail_rows": detail_rows, "csrf_token": csrf_token_for(raw),
    })


@router.post("/admin/werkbank/taken/{task_id}/afgehandeld", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def taak_afhandelen(task_id: int, request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui), besluit: str = Form("")):
    api.close_task(db, task_id, done_by=email, decision=besluit.strip() or None)
    db.commit()
    return templates.TemplateResponse(request, "_werkbank_lijst.html", _ctx(request, db, email))
