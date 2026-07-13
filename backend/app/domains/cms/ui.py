"""Server-rendered publieke site-kern (React-exit #405, §21): homepage,
CMS-slugpagina's en de betaal-resultaatpagina's. De SiteShell (navigatie +
footer) komt uit app.ui.site_context().
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.cms.models import CmsPage
from app.domains.cms.render import render_cms_content
from app.ui import site_context, templates

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def homepage(request: Request, db: Session = Depends(get_db)):
    from app.domains.activities.api import list_activities

    if request.state.platform_landing:
        # renko.be-wortel (§7, 5c): de "Raak Digital Platform"-landing met de
        # actieve afdelingen; units draaien op hun eigen adres of pad-prefix.
        from app.domains.mdm.api import Organization
        from app.kernel.tenant_config import tenant_base_url, tenant_display_name

        units = (db.query(Organization)
                 .filter(Organization.org_type == "UNIT",
                         Organization.is_active == True)  # noqa: E712
                 .order_by(Organization.id).all())
        afdelingen = [{"naam": tenant_display_name(db, tenant_id=u.id),
                       "url": tenant_base_url(db, tenant_id=u.id)}
                      for u in units]
        return templates.TemplateResponse(request, "platform_landing.html", {
            "afdelingen": afdelingen, "current_year": site_context(db)["current_year"]})

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


# ── Per-tenant SEO (5c, #406): robots + sitemap — verdwenen met de React-exit,
# nu server-side en tenant-bewust. Demo/noindex-tenants worden niet geïndexeerd.

@router.get("/robots.txt", response_class=PlainTextResponse)
def robots(request: Request, db: Session = Depends(get_db)):
    from app.kernel.tenant_config import get_setting, tenant_base_url

    if get_setting(db, "noindex") == "1":
        return "User-agent: *\nDisallow: /\n"
    return (f"User-agent: *\nAllow: /\nDisallow: /admin\n"
            f"Sitemap: {tenant_base_url(db)}/sitemap.xml\n")


@router.get("/sitemap.xml")
def sitemap(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import Response

    from app.kernel.tenant_config import get_setting, tenant_base_url

    if get_setting(db, "noindex") == "1":
        raise HTTPException(status_code=404, detail="Geen sitemap voor deze tenant")
    base = tenant_base_url(db)
    paden = ["/", "/activiteiten", "/activiteiten/archief", "/fotos",
             "/lid-worden", "/berichten"]
    paden += [f"/{p.slug}" for p in (db.query(CmsPage)
                                     .filter(CmsPage.is_published == True)  # noqa: E712
                                     .order_by(CmsPage.slug).all())]
    urls = "".join(f"<url><loc>{base}{pad}</loc></url>" for pad in paden)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           f"{urls}</urlset>")
    return Response(content=xml, media_type="application/xml")


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
