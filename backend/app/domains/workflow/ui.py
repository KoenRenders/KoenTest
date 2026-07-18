"""Werkbank-embryo (#398, §20.5): open taken tonen, behartigen, sluiten door
beslissing. Rol-gefilterd; verversen via htmx-polling (§20.5 — geen SSE)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.workflow import api
from app.ui import admin_nav, templates
from app.domains.auth.api import csrf_token_for, require_admin_ui, require_csrf, SESSION_COOKIE

router = APIRouter(include_in_schema=False)


def _ctx(request: Request, db: Session, email: str, kind: str = "") -> dict:
    from app.domains.auth.api import get_user_roles
    from app.i18n import _

    roles = sorted(get_user_roles(db, email))
    raw = request.cookies.get(SESSION_COOKIE) or ""
    all_tasks = api.open_tasks(db, roles)

    # Eén gegroepeerde filter (#549), data-gedreven uit de dotted `kind`
    # (bv. "membership.reminder" → categorie "membership", subtype "reminder").
    def _cat(k: str) -> str:
        return (k or "").split(".", 1)[0]

    def _sub(k: str) -> str:
        return (k or "").split(".", 1)[1] if "." in (k or "") else ""

    cats: dict[str, set] = {}
    for t in all_tasks:
        if t.kind:
            cats.setdefault(_cat(t.kind), set())
            if _sub(t.kind):
                cats[_cat(t.kind)].add(_sub(t.kind))
    # Macro-klaar (grouped_filter): top-optie "Alle taken" + per categorie een
    # optgroup met "Alle <cat>" (prefix-match) + de exacte subtypes.
    filter_top = [("", _("Alle taken"))]
    filter_groups = {
        cat: [(cat, f'{_("Alle")} {cat}')] + [(f"{cat}.{s}", s) for s in sorted(subs)]
        for cat, subs in sorted(cats.items())
    }
    # Filter: kind met punt → exact; zonder punt → hele categorie (prefix); leeg → alles.
    if "." in kind:
        tasks = [t for t in all_tasks if t.kind == kind]
    elif kind:
        tasks = [t for t in all_tasks if _cat(t.kind) == kind]
    else:
        tasks = all_tasks
    return {
        "csrf_token": csrf_token_for(raw),
        "roles": roles,
        "tasks": tasks,
        "nav_items": admin_nav("/admin/werkbank"),
        "filter_top": filter_top,
        "filter_groups": filter_groups,
        "kind": kind,
    }


@router.get("/admin/werkbank", response_class=HTMLResponse)
def werkbank(request: Request, db: Session = Depends(get_db),
             email: str = Depends(require_admin_ui),
             kind: str = ""):
    from app.config import settings

    ctx = _ctx(request, db, email, kind)
    ctx["workbench_enabled"] = settings.workbench_enabled
    return templates.TemplateResponse(request, "werkbank.html", ctx)


@router.get("/admin/werkbank/lijst", response_class=HTMLResponse)
def werkbank_lijst(request: Request, db: Session = Depends(get_db),
                   email: str = Depends(require_admin_ui),
                   kind: str = ""):
    """Polling-fragment: de filter-control + gefilterde takenlijst (elke 30s
    ververst, §20.5; het filter overleeft de polling via hx-include)."""
    return templates.TemplateResponse(request, "_werkbank_lijst.html",
                                      _ctx(request, db, email, kind))


@router.get("/admin/werkbank/taken/{task_id}", response_class=HTMLResponse)
def taak_detail(task_id: int, request: Request, db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)):
    """Fragment (htmx) én deep-link (volle pagina zonder HX-Request, §20.5)."""
    task = api.get_task(db, task_id)
    detail_rows: list[tuple[str, str]] = []
    if task and task.subject_type == "form_submission":
        from app.domains.forms.api import submission_view

        detail_rows = submission_view(db, task.subject_id)
    raw = request.cookies.get(SESSION_COOKIE) or ""
    template = ("_werkbank_detail.html" if request.headers.get("hx-request")
                else "werkbank_taak.html")
    ctx = {"task": task, "detail_rows": detail_rows,
           "csrf_token": csrf_token_for(raw)}
    if template == "werkbank_taak.html":
        ctx["nav_items"] = _ctx(request, db, email)["nav_items"]
    return templates.TemplateResponse(request, template, ctx)


@router.post("/admin/werkbank/taken/{task_id}/afgehandeld", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def taak_afhandelen(task_id: int, request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui), besluit: str = Form("")):
    api.complete_task(db, task_id, done_by=email, decision=besluit.strip() or None)
    db.commit()
    return templates.TemplateResponse(request, "_werkbank_lijst.html", _ctx(request, db, email))
