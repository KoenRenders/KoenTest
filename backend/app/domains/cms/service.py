"""Leesbewerkingen op CMS-pagina's (#635 I).

De publieke routes deden hun eigen queries: de home-intro ophalen, een
gepubliceerde pagina op slug zoeken, de slugs voor de sitemap verzamelen. Kleine
queries, maar wel met een regel erin die nergens anders staat — "publiek betekent
`is_published`" — en die regel hoort niet in drie routes te wonen.
"""

import html
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from app.domains.cms import schema as _schema
from app.domains.cms.models import CmsPage, CmsPageTranslation
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
SITE_BLOCK_SLUGS: tuple[str, ...] = ("site-footer",)


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
        # The home page stands at `/` (listed with the shell's own paths); its slug
        # is a second address for the same page (CR-32 R17).
        if is_page(p.slug) and not p.is_home
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
    # The page first: its own rule (a title and a slug) speaks before the lookup,
    # as it did when the screen asked it.
    page = CmsPage(
        title=data.title,
        slug=data.slug,
        content=data.content,
        is_published=data.is_published,
        show_in_nav=data.show_in_nav,
        sort_order=data.sort_order,
    )
    if db.query(CmsPage).filter(CmsPage.slug == data.slug).first():
        raise SlugBestaatAl("Dit webadres bestaat al.")
    db.add(page)
    db.flush()
    # CR-17 fase 1 (#1671): a new page starts with a translation row in the
    # tenant's language, its documents derived from the content it was
    # created with (review C3, #1673) — an empty draft for an empty page.
    # The derive step is the row's ONE creation site. An explicit add here
    # besides her meant TWO rows for the same (page, language) on the app's
    # autoflush=False session: the pending first row is invisible to the
    # derive step's lookup, so it created a second and the commit died on
    # the primary key — the create screen's "Er ging iets mis" (Koen, 8
    # October 2026, on the local version; the suite was blind because the
    # test session autoflushes, the app session does not).
    _derive_documents_from_content(db, page)
    db.commit()
    db.refresh(page)
    return page


def seed_site_blocks(db, tenant_id: int, name: str) -> None:
    """What a new tenant's site starts with (CR-19 §C2 cms, #1478; CR-32 R17): the
    footer block and the home page.

    Without them a fresh site is an empty page: the shell renders `site-footer`
    and `/` renders the tenant's flagged home page (`seed_home_page`), and
    neither exists for a tenant created through the editor. Placeholder text in
    Dutch, the language a new tenant starts in; the address and contact come
    from the organisation record through `site_context` already. Idempotent: a
    block or a home page that exists is left as it is. Flushes; the caller's
    transaction commits.
    """
    from html import escape

    seeded = {
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
            page = CmsPage(
                tenant_id=tenant_id,
                slug=slug,
                title=title,
                content=content,
                is_published=True,
                show_in_nav=False,
            )
            db.add(page)
            db.flush()
            # CR-17 fase 1 (#1671): the seed writes the row — the documents
            # come from the first save or from the migration, exactly like
            # every other page; the site renders `content` until the readers
            # move (snede 3).
            db.add(
                CmsPageTranslation(
                    page_id=page.id,
                    language=_language(db, page),
                    title=title,
                )
            )
    db.flush()
    seed_home_page(db, tenant_id, name)


def seed_home_page(db, tenant_id: int, name: str, *, intro_blocks=None) -> "CmsPage | None":
    """The tenant's home page, when it has none (CR-32 R17; Koen, 15 October
    2026: "a op 4 en 5"): a page of the CMS, flagged as home and published, built
    by `home_document` from the intro the tenant already had (`intro_blocks`; a
    welcome line for a tenant that never had one) and from the modules it has on.
    A tenant that already flagged a page — published or not — is left alone: this
    never touches an existing page. Titled with the site's name, which the board
    changes under Pagina's; slug `start`, not in the menu (the shell's *Home*
    is the way to it). Returns the page, or None when it left things as they were.
    Flushes; the caller's transaction commits."""
    from datetime import datetime, timezone

    from app.domains.cms.home_page import home_document
    from app.domains.cms.models import CmsPageHistory
    from app.domains.forms.api import CONTACT_FORM_SLUG
    from app.domains.mdm.api import enabled_modules

    if (
        db.query(CmsPage.id)
        .filter(CmsPage.tenant_id == tenant_id, CmsPage.is_home.is_(True))
        .execution_options(include_all_tenants=True)
        .first()
        is not None
    ):
        return None
    taken = {
        slug
        for (slug,) in db.query(CmsPage.slug)
        .filter(CmsPage.tenant_id == tenant_id)
        .execution_options(include_all_tenants=True)
        .all()
    }
    slug = "start" if "start" not in taken else "startpagina"
    if slug in taken:
        return None
    modules = enabled_modules(tenant_id, db=db)
    if intro_blocks is None:
        intro_blocks = [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": f"Welkom bij {name}. Deze tekst past u aan onder Pagina's.",
                    }
                ],
            }
        ]
    document = home_document(
        intro_blocks,
        membership="membership" in modules,
        activities="activities" in modules,
        contact_slug=CONTACT_FORM_SLUG if "forms" in modules else None,
    )
    now = datetime.now(timezone.utc)
    page = CmsPage(
        tenant_id=tenant_id,
        slug=slug,
        title=name[:200],
        content=None,
        is_published=True,
        show_in_nav=False,
        is_home=True,
    )
    db.add(page)
    db.flush()
    db.add(
        CmsPageTranslation(
            page_id=page.id,
            language=_language(db, page),
            title=name[:200],
            draft_json=document,
            published_json=document,
            published_at=now,
            published_by="seed",
        )
    )
    db.add(
        CmsPageHistory(
            page_id=page.id,
            language=_language(db, page),
            action="published",
            document=document,
            at=now,
            by="seed",
        )
    )
    db.flush()
    return page


def _check_opening(data) -> None:
    """The page's opening and its hero, refused by name BEFORE any write (CR-32
    F4): an opening outside the two, a hero the schema refuses."""
    from app.domains.cms.schema import OPENINGS, InvalidShape, validate_hero

    opening = getattr(data, "opening", None)
    if opening is not None and opening not in OPENINGS:
        raise InvalidShape(f"Onjuiste vorm: opening={opening!r}")
    hero = getattr(data, "hero", None)
    if hero is not None:
        validate_hero(hero)


class SectionRefused(ValueError):
    """A section the menu cannot hold (CR-17 phase 6, #2024): its message is
    the author's sentence."""


def _check_section(db, page: CmsPage, parent_id: Optional[int], *, is_home: bool) -> None:
    """The menu is one level deep and a section is a page (Koen, 15 October
    2026, Q&A nr. 11: "ja"): a page stands under a page that stands under no
    section, a page with pages under it stands under none, and the home page
    is neither a section nor under one — it is the site's `/`, not a menu item."""
    holds_pages = (
        page.id is not None
        and db.query(CmsPage).filter(CmsPage.parent_id == page.id).first() is not None
    )
    if is_home and holds_pages:
        raise SectionRefused(
            _("Er staan pagina's onder deze pagina: de startpagina is geen sectie.")
        )
    if parent_id is None:
        return
    if is_home:
        raise SectionRefused(_("De startpagina staat niet onder een sectie."))
    if parent_id == page.id:
        raise SectionRefused(_("Een pagina kan niet onder zichzelf staan."))
    section = db.query(CmsPage).filter(CmsPage.id == parent_id).first()
    if section is None:
        raise SectionRefused(_("Die sectie bestaat niet."))
    if section.parent_id is not None:
        raise SectionRefused(
            _("“%(naam)s” staat zelf onder een sectie: het menu heeft één niveau.")
            % {"naam": section.title}
        )
    if section.is_home:
        raise SectionRefused(_("De startpagina is geen sectie."))
    if holds_pages:
        raise SectionRefused(
            _(
                "Er staan pagina's onder deze pagina: ze is een sectie en staat zelf onder geen sectie."
            )
        )


def menu_name(db, page: CmsPage) -> str:
    """The page's word in the menu: its menu name, else its title (Koen, 15
    October 2026, Q&A nr. 11: "ja")."""
    translation = get_translation(db, page)
    return (translation.menu_label if translation else None) or page.title


def section_back(db, page: CmsPage) -> Optional[tuple[str, str]]:
    """The way back from a page under a section: the section's menu name and
    its path, or None — also when the section is offline, since then it is no
    page a visitor can go back to."""
    if page.parent_id is None:
        return None
    section = published_page_by_id(db, page.parent_id)
    if section is None:
        return None
    return menu_name(db, section), "/" + section.slug


@dataclass(frozen=True)
class MenuItem:
    """A page in the site's menu, by its menu name; a section carries the
    pages under it (CR-17 phase 6, #2024)."""

    id: int
    slug: str
    label: str
    children: tuple["MenuItem", ...] = ()

    @property
    def path(self) -> str:
        return "/" + self.slug


def menu_tree(db) -> list[MenuItem]:
    """The site's menu: the published pages that stand in it, in the order set
    in the back office, a section with its pages under it. A page whose section
    is not in the menu — offline, or out of the menu — is not in it either
    (Koen, 16 October 2026, "3a": only the menu hides it; its address keeps
    working while it is published)."""
    pages = (
        db.query(CmsPage)
        .filter(CmsPage.is_published.is_(True), CmsPage.show_in_nav.is_(True))
        .order_by(CmsPage.sort_order.asc(), CmsPage.title.asc())
        .all()
    )
    # One question for every menu name, in each page's own language (the
    # tenant's: phase 1 has one row per page), as `menu_name` reads it.
    language = {p.id: _language(db, p) for p in pages}
    labels = {
        t.page_id: t.menu_label
        for t in db.query(CmsPageTranslation).filter(
            CmsPageTranslation.page_id.in_(list(language)),
            CmsPageTranslation.menu_label.isnot(None),
        )
        if t.language == language[t.page_id]
    }

    def item(page: CmsPage, children: tuple[MenuItem, ...] = ()) -> MenuItem:
        return MenuItem(page.id, page.slug, labels.get(page.id) or page.title, children)

    return [
        item(top, tuple(item(p) for p in pages if p.parent_id == top.id))
        for top in pages
        if top.parent_id is None
    ]


def published_page_by_id(db, page_id: int) -> Optional[CmsPage]:
    return db.query(CmsPage).filter(CmsPage.id == page_id, CmsPage.is_published.is_(True)).first()


def section_choices(db, page: CmsPage) -> list[tuple[int, str]]:
    """The pages this page may stand under, by the rules of `_check_section`:
    none for the home page or for a section that holds pages."""
    if page.is_home or db.query(CmsPage).filter(CmsPage.parent_id == page.id).first():
        return []
    return [
        (p.id, p.title)
        for p in list_pages(db)
        if p.id != page.id and p.parent_id is None and not p.is_home and serves_at_address(p)
    ]


def _apply_page_fields(db, page: CmsPage, data) -> None:
    """The record's fields onto the page, in the CALLER's transaction — the
    applying half of `update_page` and of the screen's one save (the review's
    A3, #1734): the document is validated before she runs, so a refusal has
    written nothing that this half would leave behind."""
    _check_opening(data)
    if data.title and len(data.title) > 200:
        # `page_translations.title` is String(200); `cms_pages.title` carries
        # 255. A 201–255 character title aborted the save on the INSERT
        # (review B3, #1770) — every door speaks her, this is the one that
        # applies the title.
        raise ValueError("De titel is te lang: hooguit 200 tekens.")
    if data.slug and data.slug != page.slug:
        if db.query(CmsPage).filter(CmsPage.slug == data.slug).first():
            raise SlugBestaatAl("Dit webadres bestaat al.")
    # CR-17 phase 6 (#2024): before anything is written, the home flag's move
    # included — a refusal leaves the transaction as it found it.
    is_home = data.is_home if data.is_home is not None else page.is_home
    parent_id = data.parent_id if "parent_id" in data.model_fields_set else page.parent_id
    _check_section(db, page, parent_id, is_home=bool(is_home))
    if data.is_home and not page.is_home:
        # #1477: one home page per tenant — the flag moves, it is not refused.
        # Flushed first, so the unique index never sees two at once.
        for other in db.query(CmsPage).filter(CmsPage.is_home.is_(True)).all():
            other.is_home = False
        db.flush()
    velden = data.model_dump(exclude_none=True, exclude={"parent_id", "menu_label"})
    for veld, waarde in velden.items():
        setattr(page, veld, waarde)
    page.parent_id = parent_id
    if "menu_label" in data.model_fields_set:
        # The menu's word, when it differs from the title; empty is the title.
        label = (data.menu_label or "").strip() or None
        if label and len(label) > 80:
            raise SectionRefused(_("De naam in het menu is te lang: hooguit 80 tekens."))
        for translation in db.query(CmsPageTranslation).filter(
            CmsPageTranslation.page_id == page.id
        ):
            translation.menu_label = label
    # CR-17 fase 1 (#1671): the translation row is the title's source; the
    # page column is its one-release shadow (kept in sync here so every
    # existing reader — the menus, the shell — keeps working unchanged).
    if data.title:
        for translation in db.query(CmsPageTranslation).filter(
            CmsPageTranslation.page_id == page.id
        ):
            translation.title = data.title


def update_page(db, page_id: int, data) -> CmsPage:
    """The page's fields, committed — the JSON API's door.

    CR-17 snede 3 (#1671, the review's A1 on #1734): the documents are no
    longer derived from `content` here. That derivation was slice 1's
    interim — "zolang Trix de pagina-editor is" — and its premise left with
    Trix: the editor writes documents, `content` is the honest fallback of a
    page that never published one, and re-deriving from her would overwrite
    what the author saved. Only `create_page` still derives (the honest
    initial state of a new page).
    """
    page = get_page_by_id(db, page_id)
    if page is None:
        raise LookupError("Page not found")
    _apply_page_fields(db, page, data)
    db.commit()
    db.refresh(page)
    return page


def save_page_form(db, page_id: int, data, document, *, by: str | None = None) -> CmsPage:
    """The screen's ONE save: the record's fields and the document in a
    single transaction (the review's A3, #1734) — a refusal saves nothing
    at all, not half. Every refusal comes BEFORE the first write: the
    document is translated, validated and her figures' media ids checked
    (C6 7) first, the fields' own refusals (a slug that exists) before the
    one flush they can cause — so a refused save leaves the session CLEAN,
    and the screen re-renders her over the same, untouched session. That
    ordering is why there is no rollback here: a bare `rollback()` would
    discard more than this form ever wrote.
    """
    page = get_page_by_id(db, page_id)
    if page is None:
        raise LookupError("Page not found")
    # Every refusal BEFORE the first write (N1, the third reading on
    # #1734): the fields' own refusals — a slug that exists, a title longer
    # than her column — come before the document is written, so a refused
    # address leaves the draft as it was, pending nothing (the app's session
    # does not flush on its own; the promise is not left to that).
    if data.slug and data.slug != page.slug:
        if db.query(CmsPage).filter(CmsPage.slug == data.slug).first():
            raise SlugBestaatAl("Dit webadres bestaat al.")
    _check_opening(data)
    if data.title and len(data.title) > 200:
        # `page_translations.title` is String(200); a longer title would
        # abort on the INSERT (review B3) — and this door promises every
        # refusal BEFORE the first write (the second read's finding 2,
        # #1770): the check stands beside the slug's, ahead of the
        # document.
        raise ValueError("De titel is te lang: hooguit 200 tekens.")
    # Whether there IS a document to save is this door's rule, not the
    # screen's (CR-13 §B9.3): an empty field saves the fields alone.
    if document is not None and document.strip():
        try:
            parsed = json.loads(document)
        except ValueError:
            # A document that does not parse carries no name of her own —
            # the author reads what to do, not Python's English.
            raise ValueError("Ongeldige documentopmaak.")
        save_document(db, page_id, parsed, by=by, commit=False)
    _apply_page_fields(db, page, data)
    db.commit()
    db.refresh(page)
    return page


def _derive_documents_from_content(db, page: CmsPage) -> None:
    """The documents of a page, re-derived from its content (snede 1).

    Strict where the content converts losslessly, lenient for the draft
    otherwise (F11): a page that does not convert keeps its words as a draft
    and an empty `published_json` — the site keeps rendering her `content`
    until an author publishes the draft (from snede 3 on).
    """
    from app.domains.cms.parse import parse_html

    document = parse_html(page.content)
    draft = document or parse_html(page.content, lenient=True)
    translation = get_translation(db, page)
    if translation is None:
        translation = CmsPageTranslation(
            page_id=page.id, language=_language(db, page), title=page.title
        )
        db.add(translation)
    translation.draft_json = draft
    if document is not None and page.is_published:
        translation.published_json = document
    else:
        # Not lossless, or unpublished: publishing is an author's act, not a
        # side effect of a save — `published_json` is cleared and the site
        # renders content (review C3, #1673: a publish switch without a
        # content change follows too).
        translation.published_json = None


def delete_page(db, page_id: int) -> None:
    page = get_page_by_id(db, page_id)
    if page is None:
        raise LookupError("Page not found")
    # CR-17 phase 6 (#2024): a section with pages under it stays (Koen, 15
    # October 2026: "ja"); the database's RESTRICT is the net under this.
    if db.query(CmsPage).filter(CmsPage.parent_id == page.id).first():
        raise SectionRefused(
            _(
                "Er staan nog pagina's onder “%(naam)s”: zet ze eerst onder een andere "
                "sectie of onder geen."
            )
            % {"naam": page.title}
        )
    db.delete(page)
    db.commit()


# ── Documents (CR-17 fase 1, #1671) ───────────────────────────────────────────


def known_language(db, locale: Optional[str]) -> str:
    """Map a locale to a language code the database knows (review A5,
    #1770). `page_translations.language` carries a foreign key to
    `mdm.language_codes`; the tenant's `language` setting is free text,
    so `frans`, `FR` or `vlaams` would abort a migration on the INSERT and
    break every later save. One place maps the setting: the part before
    the underscore, as she stands (`FR` falls back — the code is a row's
    key, not a case-insensitive name), when `mdm.language_codes` carries
    her, else `nl` — the association's own language, the row every tenant
    has
    today. A tenant that changes its setting later keeps its documents:
    the reader asks for the new language, finds nothing and falls back,
    exactly as a visitor of a language without content does (C4.3)."""
    from app.domains.mdm.api import language_code_exists

    code = _schema.locale_language(locale or "nl_BE")
    if language_code_exists(db, code):
        return code
    return "nl"


def _language(db, page: CmsPage, language: Optional[str] = None) -> str:
    """The language of a page's translation row: the one asked for, else the
    tenant's — as a language CODE (`nl`), the key `mdm.language_codes`
    carries. Phase 1 has exactly one row per page."""
    from app.kernel.tenant_config import tenant_language

    return known_language(db, language or tenant_language(db, tenant_id=page.tenant_id))


def get_translation(db, page: CmsPage, language: Optional[str] = None):
    """The page's translation row in this language, or None (C4.3)."""
    from app.domains.cms.models import CmsPageTranslation

    return (
        db.query(CmsPageTranslation)
        .filter(
            CmsPageTranslation.page_id == page.id,
            CmsPageTranslation.language == _language(db, page, language),
        )
        .first()
    )


def published_document(db, page: CmsPage, language: Optional[str] = None) -> Optional[dict]:
    """The page's published document, or None. From snede 3 (#1671) this is
    what the site shows; today the site still renders `content` and this is
    the accessor the readers will move to. None means the page renders its
    pre-CR-17 HTML — the migration's honest fallback for a page that did not
    convert losslessly (R17)."""
    translation = get_translation(db, page, language)
    return translation.published_json if translation is not None else None


def draft_document(db, page: CmsPage, language: Optional[str] = None) -> Optional[dict]:
    """The draft, or None when the page has no draft document yet."""
    translation = get_translation(db, page, language)
    return translation.draft_json if translation is not None else None


def editable_document(db, page: CmsPage, language: Optional[str] = None) -> dict:
    """What the editor opens: the draft (every page has one since the
    migration — a page that did not convert losslessly holds its words as a
    draft, F11), or a lenient parse of its HTML when no row exists yet, or an
    empty page. The editor shows one document; there is no second page
    editor (C2 cms)."""
    from app.domains.cms.parse import parse_html

    draft = draft_document(db, page, language)
    if draft is not None:
        return draft
    parsed = parse_html(page.content, lenient=True)
    if parsed and parsed.get("content"):
        return parsed
    return {"type": "doc", "content": []}


def is_site_block(slug: str) -> bool:
    """Whether this slug is one of the site's own blocks (#1510) — the blocks
    render without the page's heading shift, so their documents parse with
    `on_page=False`."""
    return slug in SITE_BLOCK_SLUGS


def serves_at_address(page: CmsPage) -> bool:
    """Whether this page is served at an address of her own (review A2 of
    12 October 2026): the site's own blocks (the home intro, the footer)
    render inside other pages and stand at no address of their own — a
    button that points at her leads to a 404. The button's page list asks
    the same question, so the picker offers exactly what the resolver
    resolves — one rule, one place, both callers."""
    return not is_site_block(page.slug)


def published_html(db, page: CmsPage, language: Optional[str] = None, *, viewer=None) -> str:
    """What a visitor sees: the page's published document, rendered; her
    pre-CR-17 HTML as long as nothing is published (snede 3, #1671 — the
    readers' ONE source: every screen that shows a page asks here, so the
    fallback lives in one place and cannot drift between readers)."""
    from app.domains.cms.render import render_cms_content, render_document

    document = published_document(db, page, language)
    if document is not None:
        return render_document(document, db, viewer=viewer)
    return render_cms_content(page.content or "", db, on_page=not is_site_block(page.slug)) or ""


def published_parts(db, page: CmsPage, language: Optional[str] = None, *, viewer=None):
    """`published_html` as `(kind, html)` parts — prose and data blocks apart (see
    `render_document_parts`); a page on her stored HTML is one prose part."""
    from app.domains.cms.render import render_cms_content, render_document_parts

    document = published_document(db, page, language)
    if document is not None:
        return render_document_parts(document, db, viewer=viewer)
    html = render_cms_content(page.content or "", db, on_page=not is_site_block(page.slug)) or ""
    return [("prose", html)]


def draft_parts(db, page: CmsPage, language: Optional[str] = None, *, viewer=None):
    """`draft_html` as parts: the preview's counterpart of `published_parts`."""
    from app.domains.cms.render import render_cms_content, render_document_parts

    document = draft_document(db, page, language)
    if document is None:
        document = published_document(db, page, language)
    if document is not None:
        return render_document_parts(document, db, preview=True, viewer=viewer)
    html = render_cms_content(page.content or "", db, on_page=not is_site_block(page.slug)) or ""
    return [("prose", html)]


def draft_html(db, page: CmsPage, language: Optional[str] = None) -> str:
    """What the preview shows: the DRAFT (C6 5), the published document when
    no draft exists, the stored HTML as the last fallback."""
    from app.domains.cms.render import render_cms_content, render_document

    document = draft_document(db, page, language)
    if document is None:
        document = published_document(db, page, language)
    if document is not None:
        # The preview passes her own flag: a reference that leads nowhere
        # shows her words here (A4's one rule) and nothing on the site.
        return render_document(document, db, preview=True)
    return render_cms_content(page.content or "", db, on_page=not is_site_block(page.slug)) or ""


def published_text(db, page: CmsPage, language: Optional[str] = None) -> str:
    """What the chatbot reads: the published document as words — no tags, a
    code its value, a figure her alt text (C2 cms, Readers). A page that still
    shows her stored HTML keeps today's shape (the rendered HTML), exactly
    as the chatbot received her before."""
    from app.domains.cms.render import render_cms_content, render_document

    document = published_document(db, page, language)
    if document is not None:
        return render_document(document, db, target="text")
    return render_cms_content(page.content or "", db) or ""


def document_from_editor(document: Any) -> Any:
    """What the editor sends becomes a stored document (Koen, 8 October 2026).

    Two translations, both measured (#1699's third look): the editor notes
    her own chrome on every table cell — column widths and alignment,
    which our toolbar never offers and the site never shows — dropped
    here; and she marks a header row by the CELL type alone, while the
    stored document says it on the row — derived here, so the header
    survives the round trip. What the author sees and means — a merged
    cell's spans — travels untouched.

    She runs BEFORE the validator (the review's A4, #1734), so malformed
    shapes pass her by untouched — the validator refuses them by name —
    and her own walk is bounded: a document nested deeper than the
    validator's cap is refused with the validator's own words instead of
    a RecursionError. Those shapes were measured: a cell whose attrs is a
    list crashed `attrs.items()`, a 3 000-deep document the interpreter.
    """

    from app.domains.cms.schema import MAX_DEPTH, InvalidShape

    def transform(node: Any, depth: int = 0) -> Any:
        if depth > MAX_DEPTH:
            raise InvalidShape("Te diep genest: het document heeft te veel niveaus")
        if isinstance(node, list):
            return [transform(child, depth + 1) for child in node]
        if not isinstance(node, dict):
            return node
        kind = node.get("type")
        if kind in ("tableHeader", "tableCell"):
            attrs = node.get("attrs")
            # Not a mapping: leave her for the validator to refuse by name.
            if isinstance(attrs, dict):
                kept = {
                    name: value
                    for name, value in attrs.items()
                    if name not in ("colwidth", "align")
                }
                if kept or attrs:
                    node = {**node, "attrs": kept}
        elif kind == "tableRow":
            content = node.get("content")
            cells = content if isinstance(content, list) else []
            section = (
                "head"
                if any(isinstance(c, dict) and c.get("type") == "tableHeader" for c in cells)
                else "body"
            )
            node = {**node, "attrs": {"section": section}}
        elif kind == "columns":
            # The alignment is not the author's own choice to make: C4.13
            # says "bovenaan uitgelijnd; in het midden wanneer één kolom
            # alleen een afbeelding is" — derived here, one place (the
            # design review's B4), and the renderer renders the stored
            # value. A figure beside her text is the one case; everything
            # else is "top".
            content = node.get("content")
            children = content if isinstance(content, list) else []
            only_figure = [
                all(
                    isinstance(b, dict) and b.get("type") == "figure"
                    for b in (c.get("content") or [])
                )
                for c in children
                if isinstance(c, dict) and c.get("type") == "column"
            ]
            align = "middle" if len(only_figure) == 2 and sum(only_figure) == 1 else "top"
            attrs = node.get("attrs")
            node = {**node, "attrs": {**(attrs if isinstance(attrs, dict) else {}), "align": align}}
        result = dict(node)
        if isinstance(result.get("content"), list):
            result["content"] = [transform(child, depth + 1) for child in result["content"]]
        return result

    def unwrap_one_column(nodes: Any, depth: int = 0) -> Any:
        """A columns block with one column comes back as her plain blocks
        (review S4 of 12 October 2026): the author reaches her with a
        Backspace in the empty second column, and on the site she leaves
        half the width empty. The save unwraps her rather than refusing —
        the editor has no command that adds a column back, so a refused
        document could only be fixed by deleting the block and retyping
        her words."""
        if depth > MAX_DEPTH:
            raise InvalidShape("Te diep genest: het document heeft te veel niveaus")
        if not isinstance(nodes, list):
            return nodes
        unwrapped: list[Any] = []
        for child in nodes:
            if (
                isinstance(child, dict)
                and child.get("type") == "columns"
                and isinstance(child.get("content"), list)
                and len(child["content"]) == 1
                and isinstance(child["content"][0], dict)
                and child["content"][0].get("type") == "column"
            ):
                unwrapped.extend(
                    unwrap_one_column(child["content"][0].get("content") or [], depth + 1)
                )
            else:
                if isinstance(child, dict) and isinstance(child.get("content"), list):
                    child = {**child, "content": unwrap_one_column(child["content"], depth + 1)}
                unwrapped.append(child)
        return unwrapped

    document = transform(document)
    if isinstance(document, dict) and isinstance(document.get("content"), list):
        document = {**document, "content": unwrap_one_column(document["content"])}
    return document


def save_draft(
    db,
    page_id: int,
    document,
    *,
    language: Optional[str] = None,
    by: str | None = None,
    commit: bool = True,
) -> "CmsPageTranslation":
    """Opslaan: the document into `draft_json` — the editor's dialect
    translated HERE (the table rule, so every door speaks the stored
    dialect; the review's C on #1734), then validated against the schema,
    an unknown block or attribute refused with its name, never stripped
    (C6 test 2), and her figures' media ids checked against the picker's
    offer (C6 7, the review's B1 on #1734): an id the picker would not show
    this tenant — another tenant's picture, a file, a deleted one — is
    refused by her number, because publishing her would show the visitor a
    broken picture. Nothing published changes (test 4)."""
    import json as _json

    from app.domains.cms import schema as _schema
    from app.domains.cms.models import CmsPageTranslation

    page = get_page_by_id(db, page_id)
    if page is None:
        raise LookupError("Page not found")
    doc = _json.loads(document) if isinstance(document, str) else document
    doc = document_from_editor(doc)
    _schema.validate_document(doc)
    _check_references(db, doc)
    lang = _language(db, page, language)
    translation = (
        db.query(CmsPageTranslation)
        .filter(CmsPageTranslation.page_id == page.id, CmsPageTranslation.language == lang)
        .first()
    )
    if translation is None:
        translation = CmsPageTranslation(page_id=page.id, language=lang, title=page.title)
        db.add(translation)
    translation.draft_json = doc
    # `commit=False`: the caller owns the transaction (the screen's one save,
    # #1734 A3) — the draft writes, the caller commits the whole form.
    if commit:
        db.commit()
        db.refresh(translation)
    return translation


def save_document(
    db, page_id: int, document: Any, *, by: Optional[str] = None, commit: bool = True
) -> "CmsPageTranslation":
    """The screen's save door (snede 3, #1671): `save_draft` — every refusal
    (the schema's, the picker's) comes before the first write, so the
    session stays clean and the screen re-renders over her untouched
    (#635 rule 2: a ui touches no transaction; #1734 A3: a refused save
    wrote nothing to roll back). `commit=False` when the CALLER owns the
    transaction (the screen's one save): the draft then writes, and the
    caller commits the whole form."""
    return save_draft(db, page_id, document, by=by, commit=commit)


def _check_references(db, doc: dict) -> None:
    """What a document points at must exist and be offered (the ONE door, for a
    save and for a publish): a picture the picker would not show this tenant
    (C6 7), and an album the photo page does not list (CR-32 R20 — the validator
    decides by shape alone and knows no data). Refused by name, before the first
    write."""
    from app.domains.cms import schema as _schema
    from app.domains.media.api import list_albums, offered_by_picker

    for media_id in sorted(_figure_media_ids(doc)):
        if not offered_by_picker(db, media_id):
            raise _schema.InvalidShape(f"Onbekende afbeelding: {media_id}")
    _check_data_blocks(doc)
    wanted = _gallery_activity_ids(doc)
    if wanted:
        known = {album.id for album in list_albums(db)}
        for activity_id in sorted(wanted - known):
            raise _schema.InvalidShape(f"Onbekend album: {activity_id}")


def _data_blocks_of(document: Optional[dict]) -> set[str]:
    """The data blocks (`schema.DATA_BLOCKS`) a document holds."""
    from app.domains.cms.schema import DATA_BLOCKS

    found: set[str] = set()

    def walk(node):
        if not isinstance(node, dict):
            return
        if node.get("type") in DATA_BLOCKS:
            found.add(node["type"])
        for child in node.get("content") or []:
            walk(child)

    walk(document)
    return found


def _check_data_blocks(document: dict) -> None:
    """A data block belongs to a module (the registry's `home_blocks`) and is
    accepted only where that module is on for the tenant (CR-32 R18, F16). The
    validator decides by shape alone and does not know the tenant, so the rule
    stands here, before the first write, and refuses by the block's name."""
    from app.domains.cms import schema as _schema
    from app.domains.mdm.api import module_enabled
    from app.kernel.modules import owner_of

    for block in sorted(_data_blocks_of(document)):
        owner = owner_of("home_blocks", block)
        if owner is not None and not module_enabled(owner):
            raise _schema.InvalidShape(f"Het blok {block} hoort bij een module die uit staat")


def _gallery_activity_ids(document: Optional[dict]) -> set[int]:
    """The activities the galleries of a document show."""
    ids: set[int] = set()

    def walk(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "gallery":
            activity_id = (node.get("attrs") or {}).get("activity_id")
            if isinstance(activity_id, int):
                ids.add(activity_id)
        for child in node.get("content") or []:
            walk(child)

    walk(document)
    return ids


def _assert_publishable(db, document) -> dict:
    """The door every live-going document passes (review A3, #1770): what
    Opslaan already refuses — an unknown node, a shape the schema does not
    allow, a picture the picker would not offer — a draft the migration or
    the lenient parse wrote, and a restored version, meet HERE too, before
    the first write. The renderer and the sanitiser still stand behind her;
    this is integrity, not injection."""
    import json as _json

    from app.domains.cms import schema as _schema

    doc = _json.loads(document) if isinstance(document, str) else document
    doc = document_from_editor(doc)
    _schema.validate_document(doc)
    _check_references(db, doc)
    return doc


def publish(
    db, page_id: int, *, language: Optional[str] = None, by: Optional[str] = None
) -> "CmsPageTranslation":
    """Publiceren: draft → published, in one transaction, with exactly one
    history row (C4.3). `is_published` on the page means "has a published
    document in the tenant's language" from now on; for a page without a
    document (the HTML fallback) the flag keeps its old meaning.

    The draft is validated before the first write (review A3, #1770): a
    draft the migration or a lenient parse left behind cannot go live
    unread."""
    from datetime import datetime, timezone

    from app.domains.cms.models import CmsPageHistory

    page = get_page_by_id(db, page_id)
    if page is None:
        raise LookupError("Page not found")
    translation = get_translation(db, page, language)
    if translation is None or translation.draft_json is None:
        raise LookupError("Nothing to publish")
    # A3: the draft meets the same door as a save — before the first write,
    # so a refusal leaves the page exactly as she was.
    document = _assert_publishable(db, translation.draft_json)
    now = datetime.now(timezone.utc)
    translation.published_json = document
    translation.published_at = now
    translation.published_by = by
    page.is_published = True
    db.add(
        CmsPageHistory(
            page_id=page.id,
            language=translation.language,
            action="published",
            document=document,
            at=now,
            by=by,
        )
    )
    db.commit()
    db.refresh(translation)
    return translation


def take_page_offline(db, page_id: int, *, by: Optional[str] = None) -> CmsPage:
    """Offline halen (Koen, 8 October 2026, decision 1a on #1734): the page
    leaves the site — the public route reads `is_published`, and she is the
    flag — while the page, her draft and her published document all stay.
    A history row records who took her off and when (Koen: "ja" — the
    same rule as Publiceren and Terugzetten); her document is the
    published one at that moment, the empty document for a page live
    through the HTML fallback. Publiceren puts the DRAFT live again —
    the draft as it stands then, not necessarily these words.
    """
    from datetime import datetime, timezone

    from app.domains.cms.models import CmsPageHistory

    page = get_page_by_id(db, page_id)
    if page is None:
        raise LookupError("Page not found")
    translation = get_translation(db, page)
    now = datetime.now(timezone.utc)
    page.is_published = False
    db.add(
        CmsPageHistory(
            page_id=page.id,
            language=translation.language if translation else "nl",
            action="offline",
            document=(
                translation.published_json
                if translation and translation.published_json is not None
                else {"type": "doc", "content": []}
            ),
            at=now,
            by=by,
        )
    )
    db.commit()
    db.refresh(page)
    return page


def restore(db, page_id: int, history_id: int, *, by: Optional[str] = None) -> "CmsPageTranslation":
    """Terugzetten: a history version into the DRAFT — never live (test 6).
    Publishing it afterwards is what makes it live again."""
    from datetime import datetime, timezone

    from app.domains.cms.models import CmsPageHistory, CmsPageTranslation

    version = db.query(CmsPageHistory).filter(CmsPageHistory.id == history_id).first()
    page = get_page_by_id(db, page_id)
    if version is None or page is None or version.page_id != page.id:
        raise LookupError("Version not found")
    # An offline row is an event, not a version (the aside shows her without
    # a Terugzetten button); she names the moment, she is not a document to
    # return to.
    if version.action == "offline":
        raise ValueError("Offline is geen versie om terug te zetten.")
    # A3: a restored version meets the same door as a save — a history row
    # the migration or an older build wrote cannot return unread.
    document = _assert_publishable(db, version.document)
    translation = (
        db.query(CmsPageTranslation)
        .filter(
            CmsPageTranslation.page_id == page.id,
            CmsPageTranslation.language == version.language,
        )
        .first()
    )
    if translation is None:
        translation = CmsPageTranslation(
            page_id=page.id, language=version.language, title=page.title
        )
        db.add(translation)
    translation.draft_json = document
    db.add(
        CmsPageHistory(
            page_id=page.id,
            language=version.language,
            action="restored",
            document=document,
            at=datetime.now(timezone.utc),
            by=by,
        )
    )
    db.commit()
    db.refresh(translation)
    return translation


def versions(db, page_id: int, language: Optional[str] = None) -> list:
    """The history of a page's documents, newest first (Geschiedenis)."""
    from app.domains.cms.models import CmsPageHistory

    page = get_page_by_id(db, page_id)
    if page is None:
        raise LookupError("Page not found")
    query = db.query(CmsPageHistory).filter(CmsPageHistory.page_id == page.id)
    if language:
        query = query.filter(CmsPageHistory.language == language)
    return query.order_by(CmsPageHistory.at.desc(), CmsPageHistory.id.desc()).all()


def draft_states(db, page_ids: list[int]) -> dict[int, bool]:
    """Whether each page's draft differs from its published document, in one
    query — the list's badge, for a list of pages (AC3)."""
    if not page_ids:
        return {}
    rows = db.query(CmsPageTranslation).filter(CmsPageTranslation.page_id.in_(page_ids)).all()
    return {r.page_id: r.draft_json is not None and r.draft_json != r.published_json for r in rows}


def draft_differs(db, page: CmsPage) -> bool:
    """Whether the draft differs from what is live — the list's badge and the
    editor's 'concept gewijzigd' (AC3). A page without documents never shows
    it: its HTML is its live state. One source: `draft_states` (review
    B4c, #1673)."""
    return draft_states(db, [page.id]).get(page.id, False)


def references_to_media(db, asset_ids: Iterable[int]) -> dict:
    """The pages whose text shows these pictures, per asset id (CR-15 §C4.4,
    #1471). A scan of the stored HTML: a page holds a picture by its URL, not by
    a key. Unpublished pages count — publishing one must not find a hole.

    CR-17: the documents of fase 1 are derived from `content` (they follow it
    on every save), so scanning the HTML sees every picture a page holds. The
    walk over the figure nodes comes with the readers (fase 1, snede 3,
    #1671)."""
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
    # Snede 3 (#1671): the editor saves documents, and `content` no longer
    # follows them — a picture chosen through the picker stands in the
    # document's figure node by her media id. Walk the translations' figures
    # too: a page whose pictures live only in her documents must be found,
    # and unpublished (draft) ones count as much as stored HTML did.
    translations = (
        db.query(CmsPageTranslation, CmsPage.id, CmsPage.title)
        .join(CmsPage, CmsPage.id == CmsPageTranslation.page_id)
        .order_by(CmsPageTranslation.page_id, CmsPageTranslation.language)
        .all()
    )
    for translation, page_id, title in translations:
        for asset_id in sorted(_figure_media_ids(translation.draft_json) & wanted):
            found.setdefault(asset_id, []).append(
                MediaUse(label=f"Pagina {title}", href=f"/admin/paginas/{page_id}")
            )
        for asset_id in sorted(_figure_media_ids(translation.published_json) & wanted):
            found.setdefault(asset_id, []).append(
                MediaUse(label=f"Pagina {title}", href=f"/admin/paginas/{page_id}")
            )
    for uses in found.values():
        # A page that holds the picture in both her HTML and her document
        # names her once, not twice.
        seen: list = []
        for use in uses:
            if use.href not in [u.href for u in seen]:
                seen.append(use)
        uses[:] = seen
    return found


def _figure_media_ids(document: Optional[dict]) -> set[int]:
    """The media ids a document's figures hold."""
    ids: set[int] = set()
    if not isinstance(document, dict):
        return ids

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for child in node:
                walk(child)
            return
        if not isinstance(node, dict):
            return
        if node.get("type") == "figure":
            media_id = (node.get("attrs") or {}).get("media_id")
            if isinstance(media_id, int) and media_id > 0:
                ids.add(media_id)
        for child in node.get("content") or []:
            walk(child)

    walk(document)
    return ids


def placeholders(db=None) -> list[dict]:
    """Beschikbare codes voor de CMS-editor (code → omschrijving + voorbeeld).

    `db`: the request's session where the caller has one (the page editor), so
    the sites' example sees what the request sees; without it a short session
    of its own, as `render_cms_content` does."""
    from app.domains.cms.render import PLACEHOLDER_LABELS, render_cms_content

    def _preview(code: str) -> str:
        """The example of one code, in WORDS (#1615). A placeholder may render
        markup — a button, a list of cards — and the legend never shows it:
        whatever a code renders is reduced to its text here, so a new
        placeholder cannot fall back to raw output
        (`test_placeholder_previews.py` refuses a `<` in any example)."""
        if code.startswith("tenants"):
            # #1543/#1566: the cards, as the accounts with their site names.
            from app.domains.cms.render import sites_in_words

            words = sites_in_words(code.partition(":")[2] or None, db)
            return words or _("geen sites: dit account heeft er geen")
        shown = render_cms_content(f"{{{{{code}}}}}", db) or ""
        words = " ".join(html.unescape(re.sub(r"<[^>]*>", " ", shown)).split())
        if code.startswith("form:"):
            # #1567: the button's words — or that this tenant has no such form.
            return f"[{words}]" if words else _("geen knop: dit formulier kan niets ontvangen")
        return words

    return [
        {"code": f"{{{{{code}}}}}", "label": label, "preview": _preview(code)}
        for code, label in PLACEHOLDER_LABELS.items()
    ]


def insertable_codes(codes: list[dict]) -> list[dict]:
    """The codes the editor's insert menu offers, out of `placeholders()` — the
    one list, so the menu and the Codes card cannot name different codes.

    The values of the closed list (`schema.VALUE_CODES`, CR-32 R19): the menu
    inserts a value node, which only those can be. The form codes and the codes
    with a part of their own (`{{tenants:raak}}`) stay in the card and keep
    working as typed text.
    """
    from app.domains.cms.schema import VALUE_CODES

    return [code for code in codes if code["code"].strip("{}") in VALUE_CODES]
