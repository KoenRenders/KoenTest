"""Server-rendered CMS-paginabeheer (React-exit 405-d, #405 — §21).

Lijst + aanmaken + bewerken (titel, slug, inhoud, publicatie, navigatie,
volgorde) + verwijderen. De regels staan in `cms/service.py`; toont de
beschikbare placeholder-codes bij het bewerken.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from markupsafe import escape
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    Right,
    csrf_from_request,
    require_csrf,
    require_right,
)
from app.i18n import _
from app.ui import admin_nav, is_fragment_request, templates

router = APIRouter(include_in_schema=False)

NAV = "/admin/paginas"


def _lijst_ctx(
    request: Request, db: Session, *, oob: bool = False, error: str | None = None
) -> dict:
    """Pagina's on the kit's list page (#2123): the segments Gepubliceerd, Concept and In
    navigatie with their counts, the search on title and slug, the table with the order
    arrows in a column of their own.

    Er zijn tientallen CMS-pagina's, geen duizenden: filteren gebeurt op de al opgehaalde
    lijst i.p.v. in een tweede query.
    """
    from app.domains.cms.api import draft_states
    from app.domains.cms.api import list_pages as list_all_pages
    from app.ui import PER_PAGE_OPTIONS, filterparams
    from app.ui.list_state import page_of, read_state, segments_of

    state = read_state(request, ("published", "draft"))
    # "In navigatie" is a filter behind the toolbar's Filters, not a fourth segment: four
    # segments with their counts are wider than a phone (measured at 390 px, 36 px).
    in_nav = (filterparams(request).get("nav") or "") == "in_nav"
    alle = list_all_pages(db)
    # Snede 3 (#1671): the list says "concept gewijzigd" where the draft
    # differs from the published document (C4.3) — one source: draft_states.
    gewijzigd = draft_states(db, [p.id for p in alle])
    # #745: de pijltjes verplaatsen binnen de VOLLEDIGE verzameling; het filter
    # bepaalt alleen wat je ziet. Daarom wordt "eerste" en "laatste" ook daaraan
    # afgemeten: met een filter aan is de bovenste zichtbare rij zelden de eerste
    # pagina, en die dan uitgrijzen zou een verplaatsing blokkeren die gewoon kan.
    geordend = sorted(alle, key=lambda p: (p.sort_order or 0, p.id))
    eerste_id = geordend[0].id if geordend else None
    laatste_id = geordend[-1].id if geordend else None

    term = state.q.lower()
    found = [
        p
        for p in alle
        if not term or term in (p.title or "").lower() or term in (p.slug or "").lower()
    ]
    if in_nav:
        found = [p for p in found if p.show_in_nav]
    counts = {
        "published": sum(1 for p in found if p.is_published),
        "draft": sum(1 for p in found if not p.is_published),
    }
    segment = {"published": lambda p: p.is_published, "draft": lambda p: not p.is_published}
    shown = [p for p in found if not state.status or segment[state.status](p)]
    pages, total, page = page_of(shown, state)
    for row in pages:
        row.concept_gewijzigd = gewijzigd.get(row.id, False)
    return {
        "pages": pages,
        "q": state.q,
        "status": state.status,
        "gefilterd": bool(term or state.status or in_nav),
        "in_nav": in_nav,
        "eerste_id": eerste_id,
        "laatste_id": laatste_id,
        "columns": [
            {"key": "titel", "label": _("Pagina"), "cell": "name"},
            {"key": "status", "label": _("Status"), "cell": "status"},
            {"key": "plaats", "label": _("Waar"), "cell": "context"},
            {"key": "volgorde", "label": _("Volgorde"), "cell": "actions"},
        ],
        "segments": segments_of(
            [("published", _("Gepubliceerd")), ("draft", _("Concept"))],
            counts,
            len(found),
            _("Alle"),
        ),
        "page": page,
        "per_page": state.per_page,
        "total": total,
        "page_sizes": list(PER_PAGE_OPTIONS),
        "pager_url": f"{NAV}?{state.query(nav='in_nav' if in_nav else '')}",
        "empty_reason": (
            _("Geen pagina's gevonden.")
            if (term or state.status or in_nav)
            else _("Nog geen pagina's.")
        ),
        "oob": oob,
        #: The row's ⋯ (#2172): Verwijderen, with the record's question and its OK.
        "menus": {
            p.id: [
                {
                    "kind": "delete",
                    "label": _("Verwijderen"),
                    "attrs": f'hx-post="{NAV}/{p.id}/verwijderen" hx-vals=\'{{"from_list": "1"}}\' '
                    'hx-target="#cp-lijst" hx-swap="innerHTML" data-confirm-tone="delete" '
                    f'data-confirm-ok="{escape(_("Definitief verwijderen"))}"',
                    "confirm": _("“%(naam)s” definitief verwijderen?") % {"naam": p.title},
                }
            ]
            for p in pages
        },
        #: The reason a delete from a row's ⋯ was refused, on the list's banner (#2172).
        "error": error,
    }


def _record_ctx(
    request: Request,
    db: Session,
    page,
    *,
    error=None,
    slug_error=None,
    slug_typed=None,
    toast: bool = False,
    document: str | None = None,
) -> dict:
    """Everything the record page needs, built in one place (snede 3, #1671):
    the editor's configuration and her document, the draft's state against
    the published version, and the history the author can go back to.
    `document`: the POSTED document of a refused save (the review's A3,
    #1734) — the editor re-opens what the author typed, not the stored
    draft her words would otherwise replace."""
    import json as _json

    from app.domains.cms.api import (
        button_page_choices,
        draft_differs,
        editable_document,
        get_translation,
        insertable_codes,
        placeholders,
        schema,
        versions,
    )
    from app.domains.cms.service import section_choices

    # The button's dialog needs the tenant's pages and her button-eligible
    # forms (Koen, 11 October 2026: a button may lead to a page, a form,
    # "Lid worden", or an outside address). The pages are cms's own and
    # ask `serves_at_address` — the same rule the resolver resolves with,
    # so the picker offers exactly what she resolves (review A2 of 12
    # October 2026: the site's own blocks stand at no address of their
    # own). The forms ask forms' own door. "Word lid" is the module's
    # own: the screen is mounted behind the membership module, so a
    # tenant without her is not offered the choice (review A3).
    from app.domains.forms.api import form_button_choices
    from app.domains.mdm.api import module_enabled

    # The data blocks this tenant's modules offer (CR-32 F16): the registry's
    # `home_blocks` of every module that is on.
    from app.domains.mdm.api import module_enabled as _on
    from app.kernel.modules import MODULES

    data_blocks = [block for module in MODULES if _on(module.code) for block in module.home_blocks]
    # The albums a gallery block may show (CR-32 R20): the photo page's own list.
    from app.domains.media.api import list_albums
    from app.kernel.modules import ModuleCode

    gallery_albums = [
        (
            album.id,
            f"{album.name} ({(album.sort_date or album.dates[0].start_date).year})"
            if (album.sort_date or album.dates)
            else album.name,
        )
        for album in list_albums(db)
    ]
    button_pages = button_page_choices(db)
    button_forms = form_button_choices(db)
    button_lid_worden = module_enabled(ModuleCode.MEMBERSHIP)

    from app.domains.cms.schema import OPENINGS, TONES, hero_form_values

    # The hero's two buttons lead where the document's buttons may: the same
    # four kinds, as the choices of one select (CR-32 F4).
    hero_destinations = [("", _("— kies —"))]
    hero_destinations += [(f"page:{pid}", title) for pid, title in button_pages]
    hero_destinations += [(f"form:{slug}", title) for slug, title in button_forms]
    if button_lid_worden:
        hero_destinations.append(("screen:lid-worden", _("Word lid")))
    hero_destinations.append(("href", _("Een adres buiten de site")))

    return {
        "p": page,
        # CR-17 phase 6 (#2024): the pages this one may stand under.
        "section_options": [("", _("— geen —"))]
        + [(str(pid), title) for pid, title in section_choices(db, page)],
        "hero_form": hero_form_values(page.hero),
        "hero_destinations": hero_destinations,
        "opening_options": [
            (OPENINGS[0], _("Titelregel")),
            (OPENINGS[1], _("Hero — de titel groot op een band")),
        ],
        "tone_options": list(zip(TONES, (_("Neutraal"), _("Tint"), _("Accent")), strict=True)),
        "document_json": (
            document if document is not None else _json.dumps(editable_document(db, page))
        ),
        "editor_config": schema.schema_for("page", albums=gallery_albums, data_blocks=data_blocks),
        "button_pages": button_pages,
        "button_forms": button_forms,
        "button_lid_worden": button_lid_worden,
        # The value codes the author can type in the document (#1615): the
        # legend in WORDS, one source with the public renderer's examples —
        # the record page's aside shows her.
        "placeholders": (codes := placeholders(db)),
        # The same list, without the form codes: what the editor's insert
        # menu offers under "Code".
        "insert_codes": insertable_codes(codes),
        "csrf_token": csrf_from_request(request),
        "error": error,
        # #2061: why the address was refused, under its field.
        "slug_error": slug_error,
        # ... and the address as typed, so the field shows what the reason names.
        "slug_typed": slug_typed,
        "toast_opgeslagen": toast,
        "wijzigend": draft_differs(db, page),
        "vertaling": (vertaling := get_translation(db, page)),
        "versies": versions(db, page.id),
        # A page the migration could not convert losslessly is live through
        # her stored HTML; Publiceren would replace that with the (lossy)
        # draft — the CR asks a notice to compare the two first (F11, C2
        # cms; review A4, #1770).
        "live_via_oude_tekst": bool(
            page.is_published and (vertaling is None or vertaling.published_json is None)
        ),
    }


def _record_response(
    request: Request,
    db: Session,
    page_id: int,
    *,
    error=None,
    slug_error=None,
    slug_typed=None,
    toast: bool = False,
    document: str | None = None,
):
    """The record page, or a 404 — the hand-built detail fragment of the
    master-detail is gone (snede 3, #1671: the page screen is a record page
    of the kit)."""
    from app.domains.cms.api import get_page_by_id

    page = get_page_by_id(db, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=_("Pagina niet gevonden."))
    # A refused save swaps the record back into #main: the fragment, not the
    # whole shell (nesting shells is how a boosted screen breaks).
    if is_fragment_request(request):
        return templates.TemplateResponse(
            request,
            "_cp_record.html",
            _record_ctx(
                request,
                db,
                page,
                error=error,
                slug_error=slug_error,
                slug_typed=slug_typed,
                toast=toast,
                document=document,
            ),
        )
    return templates.TemplateResponse(
        request,
        "admin_pagina.html",
        {
            "nav_items": admin_nav(NAV, request),
            **_record_ctx(
                request,
                db,
                page,
                error=error,
                slug_error=slug_error,
                slug_typed=slug_typed,
                toast=toast,
                document=document,
            ),
        },
    )


@router.get("/admin/paginas", response_class=HTMLResponse)
def admin_paginas(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAGE_VIEW)),
):
    fragment = is_fragment_request(request)
    return templates.TemplateResponse(
        request,
        "_cp_kaarten.html" if fragment else "admin_paginas.html",
        {
            "nav_items": [] if fragment else admin_nav(NAV, request),
            "csrf_token": csrf_from_request(request),
            **_lijst_ctx(request, db, oob=fragment),
        },
    )


@router.get("/admin/paginas/nieuw", response_class=HTMLResponse)
def pagina_nieuw(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAGE_VIEW)),
):
    """Aanmaken als volledige pagina (#627, §2.8) i.p.v. een modal."""
    return templates.TemplateResponse(
        request,
        "admin_pagina_nieuw.html",
        {
            "nav_items": admin_nav(NAV, request),
            "csrf_token": csrf_from_request(request),
        },
    )


@router.get("/admin/paginas/{page_id}", response_class=HTMLResponse)
def pagina_detail(
    page_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAGE_VIEW)),
):
    """The page screen is a record page of the kit (snede 3, #1671): the
    header carries title and address, the actions are Voorbeeld, Publiceren
    and Geschiedenis, and the document is the editor's."""
    return _record_response(
        request, db, page_id, toast=request.query_params.get("opgeslagen") == "1"
    )


@router.post("/admin/paginas", response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def pagina_aanmaken(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAGE_MANAGE)),
    title: str = Form(""),
    slug: str = Form(""),
):
    from app.domains.cms.api import PageIncomplete, SlugBestaatAl, create_page
    from app.schemas.cms import CmsPageCreate

    try:
        nieuw = create_page(db, CmsPageCreate(title=title.strip(), slug=slug.strip().lower()))
    except (PageIncomplete, SlugBestaatAl) as refusal:
        # #2061: the reason on the form's message line. A 400 reached the screen
        # as the general "something went wrong", whatever its detail said.
        from app.kernel.refusals import FieldError
        from app.ui import refusal_response

        return refusal_response(request, [FieldError("", str(refusal))], "#pagina-nieuw-melding")
    # Aanmaken opent meteen de editor: een verse pagina heeft nog inhoud nodig.
    return Response(status_code=204, headers={"HX-Redirect": f"/admin/paginas/{nieuw.id}"})


@router.post(
    "/admin/paginas/{page_id}", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
def pagina_bijwerken(
    page_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAGE_MANAGE)),
    title: str = Form(""),
    slug: str = Form(""),
    document: str = Form(""),
    show_in_nav: str = Form(""),
    is_home: str = Form(""),
    show_in_footer: str = Form(""),
    sort_order: str | None = Form(None),
    parent_id: str = Form(""),
    menu_label: str = Form(""),
    opening: str = Form("title_line"),
    hero_tone: str = Form("plain"),
    hero_eyebrow: str = Form(""),
    hero_lead: str = Form(""),
    hero_b1_label: str = Form(""),
    hero_b1_destination: str = Form(""),
    hero_b1_address: str = Form(""),
    hero_b2_label: str = Form(""),
    hero_b2_destination: str = Form(""),
    hero_b2_address: str = Form(""),
):
    """Opslaan (snede 3, #1671): the record's fields and the document in ONE
    save (the review's A3, #1734) — a refusal saves NOTHING, not the fields
    without the document, and the editor reopens with what the author
    POSTED, not with the stored draft her words would otherwise replace.
    C6 4: nothing published changes here.
    """
    from app.domains.cms.api import SlugBestaatAl, save_page_form
    from app.domains.cms.schema import hero_from_form
    from app.schemas.cms import CmsPageUpdate

    volgorde = None
    if sort_order is not None:
        try:
            volgorde = int(sort_order or "0")
        except ValueError:
            raise HTTPException(status_code=400, detail=_("Ongeldige volgorde."))
    try:
        sectie = int(parent_id) if parent_id.strip() else None
    except ValueError:
        raise HTTPException(status_code=400, detail=_("Ongeldige sectie."))
    # No `content` and no `is_published` ride along: the editor is the author
    # of the document (content is her fallback, not her source), and
    # publishing is the Publiceren action — not a checkbox.
    data = CmsPageUpdate(
        title=title.strip() or None,
        slug=slug.strip().lower() or None,
        show_in_nav=bool(show_in_nav),
        is_home=bool(is_home),
        show_in_footer=bool(show_in_footer),
        sort_order=volgorde,
        # CR-17 phase 6 (#2024): empty is "under no section" and "the title".
        parent_id=sectie,
        menu_label=menu_label,
        opening=opening,
        hero=hero_from_form(
            hero_tone,
            hero_eyebrow,
            hero_lead,
            [
                (hero_b1_label, hero_b1_destination, hero_b1_address),
                (hero_b2_label, hero_b2_destination, hero_b2_address),
            ],
        ),
    )
    try:
        save_page_form(db, page_id, data, document, by=email)
    except LookupError:
        # An unknown page id is the author's own door: the words the list
        # screen uses, not Python's 500 (review B4, #1770).
        raise HTTPException(status_code=404, detail=_("Pagina niet gevonden."))
    except SlugBestaatAl as refusal:
        # #2061: the address's own refusal stands under its field, the banner
        # says where to look — on a long record the field is out of view.
        return _record_response(
            request,
            db,
            page_id,
            error=_("Opslaan kan nog niet: controleer 1 veld."),
            slug_error=str(refusal),
            slug_typed=data.slug,
            document=document,
        )
    except (ValueError, TypeError) as error:
        # UnknownBlock, UnknownAttribute, InvalidShape, a slug that exists,
        # an unreadable document and a picture the picker does not offer
        # all carry their own name for the author; the service refused
        # before the first write — a screen touches no transaction
        # (#635 rule 2), and the author's posted document comes back.
        return _record_response(request, db, page_id, error=str(error), document=document)
    return Response(
        status_code=204, headers={"HX-Redirect": f"/admin/paginas/{page_id}?opgeslagen=1"}
    )


@router.post(
    "/admin/paginas/{page_id}/publiceren",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def publish_page(
    page_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAGE_MANAGE)),
):
    """Publiceren (C4.3, snede 3): the draft becomes the published document
    and exactly one history row is written, in one transaction. The site
    shows her from the next request on."""
    from app.domains.cms.api import publish

    try:
        publish(db, page_id, by=email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as refusal:
        # The door of A3 (the second read's finding 1, #1770): a draft the
        # migration or a lenient parse wrote meets the schema HERE, and the
        # author reads her refusal in the screen, not a 500 — the same
        # words the save route gives, the screen the author stands in.
        return _record_response(request, db, page_id, error=str(refusal))
    return Response(
        status_code=204, headers={"HX-Redirect": f"/admin/paginas/{page_id}?opgeslagen=1"}
    )


@router.post(
    "/admin/paginas/{page_id}/offline-halen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def take_offline_page(
    page_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAGE_MANAGE)),
):
    """Offline halen (Koen, 8 October 2026, decision 1a on #1734): the page
    leaves the site and keeps everything — her draft, her published
    document, her history. A history row records who took her off and
    when (Koen: "ja"). Publiceren puts the draft live again — the draft
    as it stands then, not necessarily the same words.
    """
    from app.domains.cms.api import take_page_offline

    try:
        take_page_offline(db, page_id, by=email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
    return Response(status_code=204, headers={"HX-Redirect": f"/admin/paginas/{page_id}"})


@router.post(
    "/admin/paginas/{page_id}/terugzetten/{history_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def restore_page(
    page_id: int,
    history_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAGE_MANAGE)),
):
    """Terugzetten (C6 6): writes the chosen version into the draft only —
    the site keeps showing the published document until the author
    publishes the restored draft."""
    from app.domains.cms.api import restore

    try:
        restore(db, page_id, history_id, by=email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as refusal:
        # As Publiceren (the second read's finding 1, #1770): a history row
        # an older build wrote refuses with her name, in the screen.
        return _record_response(request, db, page_id, error=str(refusal))
    return Response(
        status_code=204, headers={"HX-Redirect": f"/admin/paginas/{page_id}?opgeslagen=1"}
    )


@router.post(
    "/admin/paginas/{page_id}/volgorde/{richting}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def pagina_verplaatsen(
    page_id: int,
    richting: str,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAGE_MANAGE)),
):
    """Eén plaats omhoog of omlaag (#745).

    De volgorde werd tot nu toe gezet door in élke pagina een getal te typen: om er
    één omhoog te zetten moest je weten welk nummer de pagina erboven droeg, beide
    editors openen en er een getal tussen verzinnen. Op HDEV stond er daardoor een
    op -1 — iemand had geen ruimte meer.

    **Verplaatsen gebeurt binnen de VOLLEDIGE verzameling**, ook als er gefilterd
    is. `move_sibling()` hernummert `sort_order` naar 0..n over wat het krijgt; voed
    je het de gefilterde rijen, dan krijgen die 0..n en verliezen alle pagina's
    buiten het filter hun plaats — dan herschrijft een filter de volgorde van de hele
    site, en dat merk je pas als het publieke menu door elkaar staat.

    Dat hernummeren ruimt meteen de dubbels en de -1 op die er vandaag staan.
    """
    from app.domains.cms.api import verplaats_pagina

    verplaats_pagina(db, page_id, richting)
    # De filterstand komt uit de browser-URL (#671), zodat je na een verplaatsing
    # dezelfde selectie terugkrijgt en niet plots de hele lijst.
    return _list_response(request, db)


@router.post(
    "/admin/paginas/{page_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def pagina_verwijderen(
    page_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAGE_MANAGE)),
    from_list: str = Form(""),
):
    """Asked from the record's action bar or from a row's ⋯ in the list (#2172,
    `from_list`): the answer goes back where it was asked."""
    from app.domains.cms.api import SectionRefused, delete_page

    try:
        delete_page(db, page_id)
    except SectionRefused as error:
        # A section with pages under it stays (#2024): the reason where the delete
        # was asked — the list's banner, or the record page again.
        if from_list:
            return _list_response(request, db, error=str(error))
        response = _record_response(request, db, page_id, error=str(error))
        response.headers["HX-Retarget"] = "#main"
        response.headers["HX-Reswap"] = "innerHTML"
        return response
    if from_list:
        return _list_response(request, db)
    # From the editor: that page no longer exists, so back to the list.
    return Response(status_code=204, headers={"HX-Redirect": "/admin/paginas"})


def _list_response(request: Request, db: Session, *, error: str | None = None):
    """The list fragment with the counts out of band, as after a move."""
    return templates.TemplateResponse(
        request,
        "_cp_kaarten.html",
        {
            "csrf_token": csrf_from_request(request),
            **_lijst_ctx(request, db, oob=True, error=error),
        },
    )


@router.get("/admin/paginas/{page_id}/voorbeeld", response_class=HTMLResponse)
def pagina_voorbeeld(
    page_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PAGE_VIEW)),
):
    """Admin-voorbeeld van een pagina — óók een concept (ongepubliceerd), #554. De
    publieke /{slug}-route blijft enkel gepubliceerde pagina's tonen (404 op concept),
    dus 'Bekijk' linkt hierheen zodat je een concept kan bekijken vóór publicatie."""
    from app.domains.cms.api import draft_parts, get_page_by_id, hero_view, section_back
    from app.ui import site_context

    page = get_page_by_id(db, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=_("Pagina niet gevonden"))
    return templates.TemplateResponse(
        request,
        "cms_pagina.html",
        {
            **site_context(db, request),
            "page": page,
            "section_back": section_back(db, page),
            "content_parts": draft_parts(db, page),
            "hero": hero_view(page, db, preview=True),
            # #924: het voorbeeld toont wat de bezoeker ziet, dus ook het contactblok
            # op de privacypagina. Expliciet meegeven en niet aan de sjabloon
            # overlaten: een sjabloon dat om iets vraagt wat zijn aanroeper niet
            # belooft, is precies wat de sjabloon-poort tegenhoudt.
            "toon_contactblok": page.slug == "privacy",
            "concept": not page.is_published,
        },
    )
