"""Leesbewerkingen op CMS-pagina's (#635 I).

De publieke routes deden hun eigen queries: de home-intro ophalen, een
gepubliceerde pagina op slug zoeken, de slugs voor de sitemap verzamelen. Kleine
queries, maar wel met een regel erin die nergens anders staat — "publiek betekent
`is_published`" — en die regel hoort niet in drie routes te wonen.
"""

import html
import json
import re
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
    db.flush()
    # CR-17 fase 1 (#1671): a new page starts with a translation row in the
    # tenant's language, its documents derived from the content it was
    # created with (review C3, #1673) — an empty draft for an empty page.
    translation = CmsPageTranslation(
        page_id=page.id, language=_language(db, page), title=data.title
    )
    db.add(translation)
    _derive_documents_from_content(db, page)
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


def _apply_page_fields(db, page: CmsPage, data) -> None:
    """The record's fields onto the page, in the CALLER's transaction — the
    applying half of `update_page` and of the screen's one save (the review's
    A3, #1734): the document is validated before she runs, so a refusal has
    written nothing that this half would leave behind."""
    if data.slug and data.slug != page.slug:
        if db.query(CmsPage).filter(CmsPage.slug == data.slug).first():
            raise SlugBestaatAl("Slug already exists")
    if data.is_home and not page.is_home:
        # #1477: one home page per tenant — the flag moves, it is not refused.
        # Flushed first, so the unique index never sees two at once.
        for other in db.query(CmsPage).filter(CmsPage.is_home.is_(True)).all():
            other.is_home = False
        db.flush()
    velden = data.model_dump(exclude_none=True)
    for veld, waarde in velden.items():
        setattr(page, veld, waarde)
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

    document = parse_html(page.content, on_page=not is_site_block(page.slug))
    draft = document or parse_html(page.content, on_page=not is_site_block(page.slug), lenient=True)
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
    db.delete(page)
    db.commit()


# ── Documents (CR-17 fase 1, #1671) ───────────────────────────────────────────


def _language(db, page: CmsPage, language: Optional[str] = None) -> str:
    """The language of a page's translation row: the one asked for, else the
    tenant's — as a language CODE (`nl`), the key `mdm.language_codes`
    carries. Phase 1 has exactly one row per page."""
    from app.kernel.tenant_config import tenant_language

    return _schema.locale_language(language or tenant_language(db, tenant_id=page.tenant_id))


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
    parsed = parse_html(page.content, on_page=not is_site_block(page.slug), lenient=True)
    if parsed and parsed.get("content"):
        return parsed
    return {"type": "doc", "content": []}


def is_site_block(slug: str) -> bool:
    """Whether this slug is one of the site's own blocks (#1510) — the blocks
    render without the page's heading shift, so their documents parse with
    `on_page=False`."""
    return slug in SITE_BLOCK_SLUGS


def published_html(db, page: CmsPage, language: Optional[str] = None) -> str:
    """What a visitor sees: the page's published document, rendered; her
    pre-CR-17 HTML as long as nothing is published (snede 3, #1671 — the
    readers' ONE source: every screen that shows a page asks here, so the
    fallback lives in one place and cannot drift between readers)."""
    from app.domains.cms.render import render_cms_content, render_document

    document = published_document(db, page, language)
    if document is not None:
        on_page = not is_site_block(page.slug)
        return render_document(document, db, on_page=on_page)
    return render_cms_content(page.content or "", db, on_page=not is_site_block(page.slug)) or ""


def draft_html(db, page: CmsPage, language: Optional[str] = None) -> str:
    """What the preview shows: the DRAFT (C6 5), the published document when
    no draft exists, the stored HTML as the last fallback."""
    from app.domains.cms.render import render_cms_content, render_document

    document = draft_document(db, page, language)
    if document is None:
        document = published_document(db, page, language)
    if document is not None:
        return render_document(document, db, on_page=not is_site_block(page.slug))
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
        result = dict(node)
        if isinstance(result.get("content"), list):
            result["content"] = [transform(child, depth + 1) for child in result["content"]]
        return result

    return transform(document)


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
    from app.domains.media.api import offered_by_picker

    for media_id in sorted(_figure_media_ids(doc)):
        if not offered_by_picker(db, media_id):
            raise _schema.InvalidShape(f"Onbekende afbeelding: {media_id}")
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


def publish(
    db, page_id: int, *, language: Optional[str] = None, by: Optional[str] = None
) -> "CmsPageTranslation":
    """Publiceren: draft → published, in one transaction, with exactly one
    history row (C4.3). `is_published` on the page means "has a published
    document in the tenant's language" from now on; for a page without a
    document (the HTML fallback) the flag keeps its old meaning."""
    from datetime import datetime, timezone

    from app.domains.cms.models import CmsPageHistory

    page = get_page_by_id(db, page_id)
    if page is None:
        raise LookupError("Page not found")
    translation = get_translation(db, page, language)
    if translation is None or translation.draft_json is None:
        raise LookupError("Nothing to publish")
    now = datetime.now(timezone.utc)
    translation.published_json = translation.draft_json
    translation.published_at = now
    translation.published_by = by
    page.is_published = True
    db.add(
        CmsPageHistory(
            page_id=page.id,
            language=translation.language,
            action="published",
            document=translation.draft_json,
            at=now,
            by=by,
        )
    )
    db.commit()
    db.refresh(translation)
    return translation


def take_page_offline(db, page_id: int) -> CmsPage:
    """Offline halen (Koen, 8 October 2026, decision 1a on #1734): the page
    leaves the site — the public route reads `is_published`, and she is the
    flag — while the page, her draft and her published document all stay.
    Publiceren puts her back with the same words; nothing is re-published
    or re-derived by this door.
    """
    page = get_page_by_id(db, page_id)
    if page is None:
        raise LookupError("Page not found")
    page.is_published = False
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
    translation.draft_json = version.document
    db.add(
        CmsPageHistory(
            page_id=page.id,
            language=version.language,
            action="restored",
            document=version.document,
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
