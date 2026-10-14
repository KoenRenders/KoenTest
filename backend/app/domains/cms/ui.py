"""Server-rendered publieke site-kern (React-exit #405, §21): homepage,
CMS-slugpagina's en de betaal-resultaatpagina's. De SiteShell (navigatie +
footer) komt uit app.ui.site_context().
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.cms.api import get_published_page, published_html, published_page, published_slugs
from app.i18n import _
from app.ui import site_context, templates

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def homepage(request: Request, db: Session = Depends(get_db)):
    from app.domains.activities.api import list_activities

    # #727: `is_published` geldt ook voor de blokken die de site zelf invult. Er
    # stond een vinkje "Gepubliceerd" op het beheerscherm dat niets deed — uitzetten
    # veranderde niets aan de homepagina. Gepubliceerd → getoond, niet gepubliceerd
    # → niet getoond, zonder uitzondering voor blok-pagina's; die uitzondering was
    # juist de verwarring.
    # CR-19 (#1477): a tenant may flag one of its pages as the home page; `/`
    # then renders that page, exactly as its own address would.
    from app.domains.cms.api import published_home_page

    home_page = published_home_page(db)
    if home_page is not None:
        return _render_page(request, db, home_page)

    intro = get_published_page(db, "home-intro")
    # Golf 11 (F31, #913): de lidmaatschapsband toont bedrag en geldigheid uit
    # dezelfde betaal-helpers als het Word-lid-scherm en de aanrekening zelf —
    # het tarief staat dus niet meer als tekst in de intro.
    from app.domains.forms.api import contact_form
    from app.domains.mdm.api import module_enabled
    from app.domains.payment.api import membership_price_for_date, membership_valid_period
    from app.kernel.modules import ModuleCode

    # CR-19 (#1477): the composition follows the module set — a block of a
    # module that is off is absent, not empty.
    toon_lidgeld = module_enabled(ModuleCode.MEMBERSHIP)
    toon_activiteiten = module_enabled(ModuleCode.ACTIVITIES)
    _van, tot = membership_valid_period()
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            **site_context(db, request),
            "intro_html": published_html(db, intro) if intro else None,
            "toon_lidgeld": toon_lidgeld,
            # #1509: and only when the contact form can take a message — a
            # tenant without it had a button that led nowhere.
            "toon_contact": module_enabled(ModuleCode.FORMS) and contact_form(db) is not None,
            "toon_activiteiten": toon_activiteiten,
            "activities": list_activities(db, scope="upcoming") if toon_activiteiten else [],
            "scope": "upcoming",
            "lidgeld": {"prijs": membership_price_for_date(), "tot": tot},
            "bericht_verzonden": request.query_params.get("bericht") == "verzonden",
        },
    )


def _payment_confirmed(db: Session, request: Request) -> bool | None:
    """Did the provider confirm the payment this page is the return of?

    #1589 (end state §2.6): the screen never reports a successful online payment
    before the provider confirms it. The return address is where the PAYER's
    browser lands — it says the payer came back, not that the money did; the
    provider's own word arrives through the webhook, usually a moment earlier
    and sometimes later. So the page reads what the ledger says.

    True: every booking is settled. False: one is still open. None: the page
    cannot tell — no reference at all, or a number without a booking — and then
    it claims nothing.

    Two kinds of return: a registration's (`?registration=<id>`, the booking
    hangs on it) and a membership's — a sign-up or a renewal (`?member=<id>`:
    the address names the household, the booking hangs on its newest
    membership; since #1590 that is read too, where the page used to say
    "wordt verwerkt" for ever).
    """
    registration = request.query_params.get("registration", "")
    if registration.isdigit():
        from app.domains.payment.api import registration_payment_states

        found = registration_payment_states(db, [int(registration)]).get(int(registration))
        return None if found is None else found["state"] == "settled"
    member = request.query_params.get("member", "")
    if member.isdigit():
        from app.domains.membership.api import household_payment_state

        state = household_payment_state(db, int(member))
        return None if state is None else state == "settled"
    return None


@router.get("/betaling/succes", response_class=HTMLResponse)
def betaling_succes(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "betaling_resultaat.html",
        {
            **site_context(db, request),
            "gelukt": True,
            "bevestigd": _payment_confirmed(db, request),
            "membership": request.query_params.get("member", "").isdigit(),
            "status_url": f"{request.url.path}?{request.url.query}",
        },
    )


@router.get("/betaling/geannuleerd", response_class=HTMLResponse)
def betaling_geannuleerd(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "betaling_resultaat.html",
        {
            **site_context(db, request),
            "gelukt": False,
            "bevestigd": None,
            "membership": False,
            "status_url": "",
        },
    )


# ── Per-tenant SEO (5c, #406): robots + sitemap — verdwenen met de React-exit,
# nu server-side en tenant-bewust. Demo/noindex-tenants worden niet geïndexeerd.


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots(request: Request, db: Session = Depends(get_db)):
    from app.kernel.tenant_config import get_setting, tenant_home_url

    if get_setting(db, "noindex") == "1":
        return "User-agent: *\nDisallow: /\n"
    return (
        f"User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: {tenant_home_url(db)}/sitemap.xml\n"
    )


@router.get("/sitemap.xml")
def sitemap(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import Response

    from app.kernel.tenant_config import get_setting, tenant_home_url

    if get_setting(db, "noindex") == "1":
        raise HTTPException(status_code=404, detail=_("Geen sitemap voor deze tenant"))
    base = tenant_home_url(db)
    # CR-19 (#1477): the fixed paths come from the registry, per module that is
    # on — a path of a module that is off would answer 404 for this tenant. The
    # menu's rule decides, so /fotos needs Activiteiten as well as Media.
    from app.domains.mdm.api import current_enabled_modules
    from app.kernel.modules import MODULES, nav_item_shown

    aan = current_enabled_modules()
    paden = ["/"] + [
        path
        for m in MODULES
        if m.code.value in aan
        for path in m.sitemap_paths
        if nav_item_shown("public_items", path, aan)
    ]
    paden += [f"/{slug}" for slug in published_slugs(db)]
    urls = "".join(f"<url><loc>{base}{pad}</loc></url>" for pad in paden)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{urls}</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


@router.get("/p/{slug}", response_class=HTMLResponse)
@router.get("/{slug}", response_class=HTMLResponse)
def cms_pagina(slug: str, request: Request, db: Session = Depends(get_db)):
    """CMS-slugpagina. Geregistreerd als LAATSTE route (main mount-volgorde):
    alle vaste paden winnen; onbekende slug = nette 404. A site block's slug
    too (#1510): `published_page` reads the same test as the sitemap."""
    page = published_page(db, slug)
    if page is None:
        raise HTTPException(status_code=404, detail=_("Pagina niet gevonden"))
    return _render_page(request, db, page)


def _render_page(request: Request, db: Session, page):
    """One published page in the site shell — at its own address, or at `/`
    when it is the tenant's home page (#1477)."""
    slug = page.slug
    return templates.TemplateResponse(
        request,
        "cms_pagina.html",
        {
            **site_context(db, request),
            "page": page,
            "content_html": published_html(db, page),
            # #924: één vaste slug krijgt het contactblok uit de organisatie, zoals de
            # footer er een krijgt. Geen shortcode en geen nieuwe pagina: er ís geen
            # contactpagina, en een blok dat van een paginanaam afhangt werkt niet voor
            # een tweede afdeling die haar pagina anders noemt.
            "toon_contactblok": slug == "privacy",
            # De template toont een concept-banner; de publieke route serveert alleen
            # gepubliceerde pagina's, dus hier altijd False. Expliciet meegeven i.p.v.
            # de template laten raden — dat is de afspraak sinds #643.
            "concept": False,
        },
    )
