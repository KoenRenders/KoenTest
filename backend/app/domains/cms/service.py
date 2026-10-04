"""Leesbewerkingen op CMS-pagina's (#635 I).

De publieke routes deden hun eigen queries: de home-intro ophalen, een
gepubliceerde pagina op slug zoeken, de slugs voor de sitemap verzamelen. Kleine
queries, maar wel met een regel erin die nergens anders staat — "publiek betekent
`is_published`" — en die regel hoort niet in drie routes te wonen.
"""

import re
from typing import Iterable, Optional

from app.domains.cms.models import CmsPage
from app.i18n import _

# A picture in a page's text is an `<img src="/api/v1/media/<id>">` (or its
# `/thumb`); the id is the whole run of digits, so 12 does not match 123.
_MEDIA_URL = re.compile(r"/api/v1/media/(\d+)(?!\d)")


class SlugBestaatAl(ValueError):
    """Twee pagina's met dezelfde slug zouden elkaar op de publieke URL
    verdringen. Geen HTTPException: de service kent geen HTTP."""


#: The site blocks: published rows the site renders inside other pages (the
#: home page shows `home-intro`, the shell `site-footer`), not pages of their
#: own (#1510). A block is known by its slug and nothing else — measured: no
#: kind exists, and `show_in_nav=False` also marks real pages such as
#: `privacy`. `seed_site_blocks` seeds exactly these.
SITE_BLOCK_SLUGS: tuple[str, ...] = ("home-intro", "site-footer")


def is_page(slug: str) -> bool:
    """Is a published row at this slug a page a visitor lands on? (#1510)

    The one test the sitemap and the public page route share: a site block is
    not, so it is neither listed in the sitemap nor served at its own address.
    """
    return slug not in SITE_BLOCK_SLUGS


def published_page(db, slug: str) -> Optional[CmsPage]:
    """The page at this slug for a visitor, or None: published, and a page —
    a site block's slug answers 404 like an unknown one (#1510)."""
    return get_published_page(db, slug) if is_page(slug) else None


def get_published_page(db, slug: str) -> Optional[CmsPage]:
    """Een gepubliceerde pagina op slug, of None.

    `is_published` is hier de hele autorisatieregel van de publieke kant: een
    concept is publiek onzichtbaar (de admin-voorbeeldroute heeft haar eigen pad).
    """
    return db.query(CmsPage).filter(CmsPage.slug == slug, CmsPage.is_published.is_(True)).first()


def published_home_page(db) -> Optional[CmsPage]:
    """The page this tenant flagged as its home page, if published (#1477)."""
    return (
        db.query(CmsPage).filter(CmsPage.is_home.is_(True), CmsPage.is_published.is_(True)).first()
    )


def published_slugs(db) -> list[str]:
    """De slugs die in de sitemap horen: published pages, not site blocks (#1510)."""
    return [
        p.slug
        for p in (
            db.query(CmsPage).filter(CmsPage.is_published.is_(True)).order_by(CmsPage.slug).all()
        )
        if is_page(p.slug)
    ]


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
    return db.query(CmsPage).order_by(CmsPage.sort_order.asc(), CmsPage.id.asc()).all()


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


def seed_site_blocks(db, tenant_id: int, name: str) -> None:
    """The two blocks a new tenant's site starts with (CR-19 §C2 cms, #1478).

    Without them a fresh site is an empty page: the home page renders
    `home-intro` and the shell renders `site-footer`, and neither exists for a
    tenant created through the editor. Placeholder text in Dutch, the language a
    new tenant starts in; the address and contact come from the organisation
    record through `site_context` already. Idempotent: a block that exists is
    left as it is. Flushes; the caller's transaction commits.
    """
    from html import escape

    seeded = {
        "home-intro": (
            "Welkom",
            f"<p>Welkom bij {escape(name)}. Deze tekst past u aan onder Pagina's.</p>",
        ),
        "site-footer": ("Voettekst", f"<p>{escape(name)}</p>"),
    }
    # #1510: the seed is the block list's — a block seeded and not listed would
    # show up in the sitemap as a page.
    blocks = [(slug, *seeded[slug]) for slug in SITE_BLOCK_SLUGS]
    existing = {
        slug
        for (slug,) in db.query(CmsPage.slug)
        .filter(CmsPage.tenant_id == tenant_id)
        .execution_options(include_all_tenants=True)
        .all()
    }
    for slug, title, content in blocks:
        if slug not in existing:
            db.add(
                CmsPage(
                    tenant_id=tenant_id,
                    slug=slug,
                    title=title,
                    content=content,
                    is_published=True,
                    show_in_nav=False,
                )
            )
    db.flush()


def update_page(db, page_id: int, data) -> CmsPage:
    page = get_page_by_id(db, page_id)
    if page is None:
        raise LookupError("Page not found")
    if data.slug and data.slug != page.slug:
        if db.query(CmsPage).filter(CmsPage.slug == data.slug).first():
            raise SlugBestaatAl("Slug already exists")
    if data.is_home and not page.is_home:
        # #1477: one home page per tenant — the flag moves, it is not refused.
        # Flushed first, so the unique index never sees two at once.
        for other in db.query(CmsPage).filter(CmsPage.is_home.is_(True)).all():
            other.is_home = False
        db.flush()
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


def references_to_media(db, asset_ids: Iterable[int]) -> dict:
    """The pages whose text shows these pictures, per asset id (CR-15 §C4.4,
    #1471). A scan of the stored HTML: a page holds a picture by its URL, not by
    a key. Unpublished pages count — publishing one must not find a hole."""
    from app.domains.media.api import MediaUse

    wanted = {int(i) for i in asset_ids}
    if not wanted:
        return {}
    found: dict[int, list] = {}
    pages = (
        db.query(CmsPage.id, CmsPage.title, CmsPage.content)
        .filter(CmsPage.content.contains("/api/v1/media/"))
        .order_by(CmsPage.id)
        .all()
    )
    for page_id, title, content in pages:
        for asset_id in sorted({int(m) for m in _MEDIA_URL.findall(content or "")} & wanted):
            found.setdefault(asset_id, []).append(
                MediaUse(label=f"Pagina {title}", href=f"/admin/paginas/{page_id}")
            )
    return found


def placeholders() -> list[dict]:
    """Beschikbare codes voor de CMS-editor (code → omschrijving + voorbeeld)."""
    from app.domains.cms.render import PLACEHOLDER_LABELS, render_cms_content

    def _preview(code: str) -> str:
        shown = render_cms_content(f"{{{{{code}}}}}") or ""
        if code.startswith("form:"):
            # #1567: the legend shows the button's words, not its markup — or
            # says that this tenant has no such form to send.
            words = re.sub(r"<[^>]+>", " ", shown).strip()
            return f"[{words}]" if words else _("geen knop: dit formulier kan niets ontvangen")
        return shown

    return [
        {"code": f"{{{{{code}}}}}", "label": label, "preview": _preview(code)}
        for code, label in PLACEHOLDER_LABELS.items()
    ]
