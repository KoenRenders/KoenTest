"""Server-rendered publieke site-kern (React-exit #405, §21): homepage,
CMS-slugpagina's en de betaal-resultaatpagina's. De SiteShell (navigatie +
footer) komt uit app.ui.site_context().
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.cms.models import CmsPage
from app.domains.cms.render import render_cms_content
from app.ui import site_context, templates

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def homepage(request: Request, db: Session = Depends(get_db)):
    from app.domains.activities.api import list_activities

    intro = db.query(CmsPage).filter(CmsPage.slug == "home-intro").first()
    return templates.TemplateResponse(request, "home.html", {
        **site_context(db),
        "intro_html": render_cms_content(intro.content or "") if intro else None,
        "activities": list_activities(db, scope="upcoming"),
        "scope": "upcoming",
    })


@router.get("/betaling/succes", response_class=HTMLResponse)
def betaling_succes(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "betaling_resultaat.html", {
        **site_context(db), "gelukt": True})


@router.get("/betaling/geannuleerd", response_class=HTMLResponse)
def betaling_geannuleerd(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "betaling_resultaat.html", {
        **site_context(db), "gelukt": False})


@router.get("/p/{slug}", response_class=HTMLResponse)
@router.get("/{slug}", response_class=HTMLResponse)
def cms_pagina(slug: str, request: Request, db: Session = Depends(get_db)):
    """CMS-slugpagina. Geregistreerd als LAATSTE route (main mount-volgorde):
    alle vaste paden winnen; onbekende slug = nette 404."""
    page = (db.query(CmsPage)
            .filter(CmsPage.slug == slug, CmsPage.is_published == True)  # noqa: E712
            .first())
    if page is None:
        raise HTTPException(status_code=404, detail="Pagina niet gevonden")
    return templates.TemplateResponse(request, "cms_pagina.html", {
        **site_context(db), "page": page,
        "content_html": render_cms_content(page.content or "")})
