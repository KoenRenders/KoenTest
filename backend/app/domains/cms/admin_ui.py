"""Server-rendered CMS-paginabeheer (React-exit 405-d, #405 — §21).

Lijst + aanmaken + bewerken (titel, slug, inhoud, publicatie, navigatie,
volgorde) + verwijderen. Hergebruikt de bestaande cms-routerfuncties als
servicelaag; toont de beschikbare placeholder-codes bij het bewerken.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    admin_user_by_email, csrf_from_request,
    SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf,
)
from app.ui import admin_nav, templates
from app.i18n import _

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/paginas")


def _lijst_ctx(db: Session, q: str = "", status: str = "") -> dict:
    """Records-lijst (C1, #587): zoeken op titel of slug + statusfilter.

    Er zijn tientallen CMS-pagina's, geen duizenden: filteren gebeurt op de al
    opgehaalde lijst i.p.v. in een tweede query.
    """
    from app.domains.cms.router import list_all_pages

    pages = list_all_pages(db=db, _admin=None)  # type: ignore[arg-type]
    term = q.strip().lower()
    if term:
        pages = [p for p in pages
                 if term in (p.title or "").lower() or term in (p.slug or "").lower()]
    if status == "published":
        pages = [p for p in pages if p.is_published]
    elif status == "draft":
        pages = [p for p in pages if not p.is_published]
    elif status == "in_nav":
        pages = [p for p in pages if p.show_in_nav]
    return {"pages": pages, "q": q, "status": status,
            "gefilterd": bool(term or status)}


def _detail_response(request: Request, db: Session, page_id: int):
    from app.domains.cms.api import CmsPage
    from app.domains.cms.router import list_cms_placeholders

    page = db.query(CmsPage).filter(CmsPage.id == page_id).first()
    if page is None:
        return HTMLResponse('<div id="cp-detail" hx-swap-oob="true"></div>')
    return templates.TemplateResponse(request, "_cp_detail.html", {
        "p": page, "placeholders": list_cms_placeholders(),
        "csrf_token": csrf_from_request(request), "error": None})


@router.get("/admin/paginas", response_class=HTMLResponse)
def admin_paginas(request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui),
                  q: str = "", status: str = ""):
    sjabloon = ("_cp_kaarten.html" if request.headers.get("hx-request")
                else "admin_paginas.html")
    return templates.TemplateResponse(request, sjabloon, {
        "nav_items": NAV, "csrf_token": csrf_from_request(request),
        **_lijst_ctx(db, q, status)})


@router.get("/admin/paginas/{page_id}", response_class=HTMLResponse)
def pagina_detail(page_id: int, request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui)):
    """Een kaart opent de paginabrede editor (C1, #587); het opslaan daarbinnen
    blijft een htmx-fragment dat in #cp-detail landt."""
    if request.headers.get("hx-request"):
        return _detail_response(request, db, page_id)
    from app.domains.cms.api import CmsPage
    from app.domains.cms.router import list_cms_placeholders

    page = db.query(CmsPage).filter(CmsPage.id == page_id).first()
    if page is None:
        raise HTTPException(status_code=404, detail=_("Pagina niet gevonden"))
    return templates.TemplateResponse(request, "admin_pagina.html", {
        "nav_items": NAV, "p": page, "placeholders": list_cms_placeholders(),
        "csrf_token": csrf_from_request(request), "error": None})


@router.post("/admin/paginas", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def pagina_aanmaken(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui),
                    title: str = Form(""), slug: str = Form("")):
    from app.domains.cms.router import create_page
    from app.schemas.cms import CmsPageCreate

    if not title.strip() or not slug.strip():
        raise HTTPException(status_code=400, detail=_("Titel en slug zijn verplicht."))
    nieuw = create_page(CmsPageCreate(title=title.strip(), slug=slug.strip().lower()),
                        db=db, _admin=None)  # type: ignore[arg-type]
    # Aanmaken opent meteen de editor: een verse pagina heeft nog inhoud nodig.
    return Response(status_code=204,
                    headers={"HX-Redirect": f"/admin/paginas/{nieuw.id}"})


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
        raise HTTPException(status_code=400, detail=_("Ongeldige volgorde."))
    # CmsPageUpdate slaat None-velden over (exclude_none) — booleans en content
    # moeten dus altijd een waarde meekrijgen, anders kun je nooit uitvinken.
    data = CmsPageUpdate(
        title=title.strip() or None, slug=slug.strip().lower() or None,
        content=content, is_published=bool(is_published),
        show_in_nav=bool(show_in_nav), sort_order=volgorde,
    )
    update_page(page_id, data, db=db, _admin=None)  # type: ignore[arg-type]
    # Geen HX-Trigger meer voor de zijlijst: die master-detail-lijst bestond
    # naast de editor en is met #587 verdwenen.
    return _detail_response(request, db, page_id)


@router.post("/admin/paginas/{page_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def pagina_verwijderen(page_id: int, request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_admin_ui)):
    from app.domains.cms.router import delete_page

    delete_page(page_id, db=db, _admin=None)  # type: ignore[arg-type]
    # Verwijderen gebeurt vanuit de editor; die pagina bestaat daarna niet meer.
    return Response(status_code=204, headers={"HX-Redirect": "/admin/paginas"})


@router.get("/admin/paginas/{page_id}/voorbeeld", response_class=HTMLResponse)
def pagina_voorbeeld(page_id: int, request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui)):
    """Admin-voorbeeld van een pagina — óók een concept (ongepubliceerd), #554. De
    publieke /{slug}-route blijft enkel gepubliceerde pagina's tonen (404 op concept),
    dus 'Bekijk' linkt hierheen zodat je een concept kan bekijken vóór publicatie."""
    from app.domains.cms.models import CmsPage
    from app.domains.cms.render import render_cms_content
    from app.ui import site_context

    page = db.query(CmsPage).filter(CmsPage.id == page_id).first()
    if page is None:
        raise HTTPException(status_code=404, detail=_("Pagina niet gevonden"))
    return templates.TemplateResponse(request, "cms_pagina.html", {
        **site_context(db, request), "page": page,
        "content_html": render_cms_content(page.content or ""),
        "concept": not page.is_published})
