"""Leesbewerkingen op CMS-pagina's (#635 I).

De publieke routes deden hun eigen queries: de home-intro ophalen, een
gepubliceerde pagina op slug zoeken, de slugs voor de sitemap verzamelen. Kleine
queries, maar wel met een regel erin die nergens anders staat — "publiek betekent
`is_published`" — en die regel hoort niet in drie routes te wonen.
"""
from typing import Optional

from app.domains.cms.models import CmsPage


class SlugBestaatAl(ValueError):
    """Twee pagina's met dezelfde slug zouden elkaar op de publieke URL
    verdringen. Geen HTTPException: de service kent geen HTTP."""


def get_published_page(db, slug: str) -> Optional[CmsPage]:
    """Een gepubliceerde pagina op slug, of None.

    `is_published` is hier de hele autorisatieregel van de publieke kant: een
    concept is publiek onzichtbaar (de admin-voorbeeldroute heeft haar eigen pad).
    """
    return (db.query(CmsPage)
            .filter(CmsPage.slug == slug, CmsPage.is_published.is_(True))
            .first())


def published_slugs(db) -> list[str]:
    """De slugs die in de sitemap horen."""
    return [p.slug for p in (db.query(CmsPage)
                             .filter(CmsPage.is_published.is_(True))
                             .order_by(CmsPage.slug).all())]


# ── Beheer (#635 I) ──────────────────────────────────────────────────────────
# Deze vier stonden als routerfuncties in `router.py` en werden door
# `admin_ui.py` geïmporteerd — de JSON-router als servicelaag, precies wat #635
# punt 3 beschrijft. De routes zijn nu dunne schillen.

def list_pages(db) -> list[CmsPage]:
    """Alle pagina's, in de volgorde waarin ze in de navigatie horen.

    Tiebreaker op `id` en niet op titel (#745): `move_sibling()` hernummert en
    wisselt op `(sort_order, id)`, en als de weergave op iets anders sorteert lijkt
    een pijltje twee plaatsen te springen zodra twee pagina's dezelfde volgorde
    dragen — precies de toestand die vandaag bestaat. Zelfde redenering als #725.
    """
    return (db.query(CmsPage)
            .order_by(CmsPage.sort_order.asc(), CmsPage.id.asc()).all())


def verplaats_pagina(db, page_id: int, richting: str) -> bool:
    """Eén plaats omhoog of omlaag in de navigatievolgorde (#745).

    Verplaatst binnen de VOLLEDIGE verzameling. `move_sibling()` hernummert
    `sort_order` naar 0..n over wat het krijgt; voed je het een gefilterde lijst,
    dan krijgen die rijen 0..n en verliezen alle pagina's daarbuiten hun plaats —
    dan herschrijft een filter de volgorde van de hele site.

    Dat hernummeren ruimt meteen de dubbels en de -1 op die er vandaag staan.
    """
    from app.kernel.ordering import move_sibling

    verplaatst = move_sibling(list_pages(db), page_id, richting)
    if verplaatst:
        db.commit()
    return verplaatst


def get_page_by_id(db, page_id: int) -> Optional[CmsPage]:
    return db.query(CmsPage).filter(CmsPage.id == page_id).first()


def create_page(db, data) -> CmsPage:
    if db.query(CmsPage).filter(CmsPage.slug == data.slug).first():
        raise SlugBestaatAl("Slug already exists")
    page = CmsPage(
        title=data.title,
        slug=data.slug,
        content=data.content,
        is_published=data.is_published,
        show_in_nav=data.show_in_nav,
        sort_order=data.sort_order,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def update_page(db, page_id: int, data) -> CmsPage:
    page = get_page_by_id(db, page_id)
    if page is None:
        raise LookupError("Page not found")
    if data.slug and data.slug != page.slug:
        if db.query(CmsPage).filter(CmsPage.slug == data.slug).first():
            raise SlugBestaatAl("Slug already exists")
    for veld, waarde in data.model_dump(exclude_none=True).items():
        setattr(page, veld, waarde)
    db.commit()
    db.refresh(page)
    return page


def delete_page(db, page_id: int) -> None:
    page = get_page_by_id(db, page_id)
    if page is None:
        raise LookupError("Page not found")
    db.delete(page)
    db.commit()


def placeholders() -> list[dict]:
    """Beschikbare codes voor de CMS-editor (code → omschrijving + voorbeeld)."""
    from app.domains.cms.render import PLACEHOLDER_LABELS, render_cms_content

    return [{"code": f"{{{{{code}}}}}", "label": label,
             "preview": render_cms_content(f"{{{{{code}}}}}")}
            for code, label in PLACEHOLDER_LABELS.items()]
