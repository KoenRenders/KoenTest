"""Server-rendered CMS-paginabeheer (React-exit 405-d, #405 — §21).

Lijst + aanmaken + bewerken (titel, slug, inhoud, publicatie, navigatie,
volgorde) + verwijderen. Hergebruikt de bestaande cms-routerfuncties als
servicelaag; toont de beschikbare placeholder-codes bij het bewerken.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf,
)
from app.ui import admin_nav, templates

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/paginas")


def _csrf(request: Request) -> str:
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


def _lijst_ctx(db: Session) -> dict:
    from app.domains.cms.router import list_all_pages

    return {"pages": list_all_pages(db=db, _admin=None)}  # type: ignore[arg-type]


def _detail_response(request: Request, db: Session, page_id: int):
    from app.domains.cms.api import CmsPage
    from app.domains.cms.router import list_cms_placeholders

    page = db.query(CmsPage).filter(CmsPage.id == page_id).first()
    if page is None:
        return HTMLResponse('<div id="cp-detail" hx-swap-oob="true"></div>')
    return templates.TemplateResponse(request, "_cp_detail.html", {
        "p": page, "placeholders": list_cms_placeholders(),
        "csrf_token": _csrf(request), "error": None})


@router.get("/admin/paginas", response_class=HTMLResponse)
def admin_paginas(request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "admin_paginas.html", {
        "nav_items": NAV, "csrf_token": _csrf(request), **_lijst_ctx(db)})


@router.get("/admin/paginas/lijst", response_class=HTMLResponse)
def paginas_lijst(request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "_cp_lijst.html", _lijst_ctx(db))


@router.get("/admin/paginas/{page_id}", response_class=HTMLResponse)
def pagina_detail(page_id: int, request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui)):
    return _detail_response(request, db, page_id)


@router.post("/admin/paginas", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def pagina_aanmaken(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui),
                    title: str = Form(""), slug: str = Form("")):
    from app.domains.cms.router import create_page
    from app.schemas.cms import CmsPageCreate

    if not title.strip() or not slug.strip():
        raise HTTPException(status_code=400, detail="Titel en slug zijn verplicht.")
    create_page(CmsPageCreate(title=title.strip(), slug=slug.strip().lower()),
                db=db, _admin=None)  # type: ignore[arg-type]
    return templates.TemplateResponse(request, "_cp_lijst.html", _lijst_ctx(db))


@router.post("/admin/paginas/{page_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def pagina_bijwerken(page_id: int, request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui),
                     title: str = Form(""), slug: str = Form(""),
                     content: str = Form(""), is_published: str = Form(""),
                     show_in_nav: str = Form(""), sort_order: str = Form("0")):
    from app.domains.cms.router import update_page
    from app.schemas.cms import CmsPageUpdate

    try:
        volgorde = int(sort_order or "0")
    except ValueError:
        raise HTTPException(status_code=400, detail="Ongeldige volgorde.")
    # CmsPageUpdate slaat None-velden over (exclude_none) — booleans en content
    # moeten dus altijd een waarde meekrijgen, anders kun je nooit uitvinken.
    data = CmsPageUpdate(
        title=title.strip() or None, slug=slug.strip().lower() or None,
        content=content, is_published=bool(is_published),
        show_in_nav=bool(show_in_nav), sort_order=volgorde,
    )
    update_page(page_id, data, db=db, _admin=None)  # type: ignore[arg-type]
    response = _detail_response(request, db, page_id)
    response.headers["HX-Trigger"] = "cp-lijst-ververst"
    return response


@router.post("/admin/paginas/{page_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def pagina_verwijderen(page_id: int, request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_admin_ui)):
    from app.domains.cms.router import delete_page

    delete_page(page_id, db=db, _admin=None)  # type: ignore[arg-type]
    return templates.TemplateResponse(request, "_cp_lijst.html", _lijst_ctx(db))
