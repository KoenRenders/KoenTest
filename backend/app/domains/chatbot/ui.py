"""Server-rendered Raakje (chat) en ai-context (fase 4c-2, #404 — §21).

- /raakje/vraag: het publieke vraag-antwoord-eindpunt van de zwevende bel
  (htmx-fragment; het antwoord komt volledig server-side terug — geen SSE nodig,
  §20.5-lijn). De pagina /raakje die hier ook op stond is weg (#1120).
- /admin/ai-context: beheer van wat Raakje weet — notities toevoegen/wissen,
  tekst-override en aan/uit per bron. Hergebruikt de bestaande admin-API.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.domains.auth.api import (
    SESSION_COOKIE,
    Right,
    csrf_token_for,
    require_csrf,
    require_right,
)
from app.domains.chatbot.render import render_answer_markdown
from app.i18n import _, short_date
from app.kernel.tenant_config import tenant_public_chat_enabled
from app.limiter import chat_limiter
from app.ui import admin_nav, templates

# Raakje-antwoord: markdown → gesaneerde HTML (#566). Het domein registreert zijn
# eigen Jinja-filter op de gedeelde template-omgeving (de UI-schil mag niet in een
# domein grijpen — import-grens #396). app.main mount deze module bij startup, dus
# de filter staat klaar vóór het eerste antwoord rendert.
templates.env.filters["raakje_md"] = render_answer_markdown

router = APIRouter(include_in_schema=False)


# ── Publiek: Raakje ────────────────────────────────────────────────────────────

# #1120: de publieke pagina `/raakje` is weg. Gemeten op PROD: sinds 15 juni 2026
# 3451 gebeurtenissen in Umami en nul op een pad met `raakje` erin — te verklaren,
# want niets in de toepassing verwees ernaar. De zwevende bel op élke publieke
# pagina doet het werk.
#
# `POST /raakje/vraag` hieronder BLIJFT: de bel postuleert daarheen. Haal je die
# mee weg, dan valt Raakje op de hele publieke site stil. Vandaar dat dit hier
# staat en niet in een commit-bericht.


#: Says to the panel that the question was not answered, so the field keeps it
#: (K8, #1562; the same header as the back office's assistant).
NOT_ANSWERED = {"X-Raakje-Failed": "1"}


@router.post("/raakje/vraag", response_class=HTMLResponse, dependencies=[Depends(chat_limiter)])
def raakje_vraag(request: Request, db: Session = Depends(get_db), vraag: str = Form("")):
    from app.domains.chatbot.api import chat_char_budget
    from app.domains.chatbot.context import build_system_prompt
    from app.domains.chatbot.logbook import sink_for
    from app.domains.chatbot.providers import get_provider
    from app.domains.chatbot.seam import GuardedProvider, SeamBlocked, public_rules
    from app.domains.chatbot.service import QuestionRefused, answer_visitor, asked

    vraag = vraag.strip()
    # #1568: the environment's switch and the tenant's, one rule — the same the
    # site shell reads for the bell.
    if not tenant_public_chat_enabled(db):
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    # One question: not empty, and with a length (#1251) — the service's rule,
    # before the budget is charged and before anything goes to the provider.
    # The field carries the same number as its `maxlength`; this is what holds
    # when a script posts. A refused question that has words stays in the field.
    try:
        vraag = asked(vraag, max_chars=settings.chat_max_input_chars)
    except QuestionRefused as refusal:
        return templates.TemplateResponse(
            request,
            "_raakje_antwoord.html",
            {"vraag": vraag, "antwoord": None, "error": str(refusal)},
            headers=NOT_ANSWERED if vraag else None,
        )
    chat_char_budget.charge(request, len(vraag))
    messages = [
        {"role": "system", "content": build_system_prompt(db)},
        {"role": "user", "content": vraag},
    ]
    # Elke uitgaande oproep passeert de naadwachter en het logboek — ook de
    # publieke (CR-07 §5.8/§6.4). De publieke bot krijgt de patroon-controles en
    # niet de naam-/e-mailcontrole: zijn contactpad bestaat net om een naam en een
    # e-mailadres te ontvangen.
    provider = GuardedProvider(get_provider(), public_rules(), sink_for())
    try:
        antwoord = answer_visitor(db, messages, provider, max_rounds=settings.chat_max_tool_rounds)
    except SeamBlocked as geblokkeerd:
        # De logregel staat al — het logboek schrijft in zijn eigen sessie, juist
        # omdat deze beurt op een foutpad eindigt.
        return templates.TemplateResponse(
            request,
            "_raakje_antwoord.html",
            {"vraag": vraag, "antwoord": None, "error": str(geblokkeerd)},
            headers=NOT_ANSWERED,
        )
    except Exception:
        return templates.TemplateResponse(
            request,
            "_raakje_antwoord.html",
            {
                "vraag": vraag,
                "antwoord": None,
                "error": _(
                    "Raakje kon geen antwoord geven — probeer het opnieuw. Je vraag staat er nog."
                ),
            },
            headers=NOT_ANSWERED,
        )
    return templates.TemplateResponse(
        request, "_raakje_antwoord.html", {"vraag": vraag, "antwoord": antwoord, "error": None}
    )


# ── Admin: ai-context ──────────────────────────────────────────────────────────
#
# #2124 (CR-11 phase 5, track 2, round 3): the list on the kit's list page, one
# segment at a time, and a record per item in place of the row's disclosure —
# the same actions, nothing new. A record is addressed by its source (the
# document's asset, the page, the note's row), so a document or a page without a
# row of its own opens too and looking at it makes none.

PAGE = "/admin/ai-context"
LIST = PAGE + "/lijst"

#: The three kinds, as segments of the list (the concept's tabs).
SEGMENTS = [
    {"value": "documenten", "label": _("Documenten")},
    {"value": "paginas", "label": _("Pagina's")},
    {"value": "notities", "label": _("Notities")},
]
#: Segment → the kind `context_item` reads, and the record's path part.
KINDS = {"documenten": "document", "paginas": "page", "notities": "note"}


def _redirect(request: Request, url: str) -> Response:
    """The shell carries hx-boost: `HX-Redirect` lets the browser really navigate."""
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


def _segment(value: str) -> str:
    return value if value in KINDS else "documenten"


def _status(info: dict | None) -> dict[str, str]:
    """The item's status as a badge: on, off, or on by default without a row."""
    if info is None:
        return {"label": _("Standaard"), "tone": "blue"}
    if info["is_active"]:
        return {"label": _("Actief"), "tone": "green"}
    return {"label": _("Uit"), "tone": "gray"}


def _items(db: Session, segment: str) -> list[dict]:
    """The segment's items as (label, record href, info, read at)."""
    from app.domains.chatbot.api import list_chatbot_info

    data = list_chatbot_info(db)
    if segment == "paginas":
        return [
            {"label": c["title"], "href": f"{PAGE}/{segment}/{c['page_id']}", "info": c["info"]}
            for c in data["cms"]
        ]
    if segment == "notities":
        return [
            {
                "label": n["title"] or _("Notitie #%(id)s") % {"id": n["id"]},
                "href": f"{PAGE}/{segment}/{n['id']}",
                "info": n,
            }
            for n in data["notes"]
        ]
    return [
        {
            "label": d["label"],
            "href": f"{PAGE}/{segment}/{d['asset_id']}",
            "info": d["info"],
            "read_at": (d["info"] or {}).get("extracted_at"),
        }
        for d in data["documents"]
    ]


def _list_view(
    request: Request, db: Session, segment: str, q: str, *, oob: bool = False, nav_items=None
):
    from app.domains.chatbot.viewmodels import AiContextListView
    from app.ui import list_return

    items = _items(db, segment)
    if q.strip():
        needle = q.strip().casefold()
        items = [i for i in items if needle in (i["label"] or "").casefold()]
    way = list_return(PAGE, segment=segment, q=q.strip())
    head, empty = _words(segment)
    columns: list[dict[str, Any]] = [
        {"key": "naam", "label": head, "cell": "name"},
        {"key": "status", "label": _("Status"), "cell": "status"},
    ]
    if segment == "documenten":
        columns.append(
            {"key": "gelezen", "label": _("Gelezen op"), "cell": "moment", "priority": 1}
        )
    rows = [
        {
            "label": i["label"],
            "href": f"{i['href']}?terug={quote(way, safe='/')}",
            "badge": _status(i["info"]),
            "read_at": short_date(i["read_at"]) if i.get("read_at") else "",
        }
        for i in items
    ]
    return AiContextListView(
        columns=columns,
        rows=rows,
        segment=segment,
        segments=SEGMENTS,
        q=q,
        total=len(rows),
        empty_reason=_("Niets gevonden voor deze zoekopdracht.") if q.strip() else empty,
        oob=oob,
        nav_items=nav_items or [],
    )


def _words(segment: str) -> tuple[str, str]:
    """The first column's head and the empty list's sentence of a segment."""
    if segment == "paginas":
        return _("Pagina"), _("Geen pagina's.")
    if segment == "notities":
        return _("Notitie"), _("Nog geen notities.")
    return _("Document"), _("Geen documenten.")


@router.get("/admin/ai-context", response_class=HTMLResponse)
def ai_context_page(
    request: Request,
    segment: str = "documenten",
    q: str = "",
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_VIEW)),
):
    view = _list_view(request, db, _segment(segment), q, nav_items=admin_nav(PAGE, request))
    return templates.TemplateResponse(request, "ai_context.html", view.as_context())


@router.get("/admin/ai-context/lijst", response_class=HTMLResponse)
def ai_context_lijst(
    request: Request,
    segment: str = "documenten",
    q: str = "",
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_VIEW)),
):
    """The list alone: the toolbar swaps this fragment, so the search field is not
    replaced under the fingers."""
    view = _list_view(request, db, _segment(segment), q, oob=True)
    return templates.TemplateResponse(request, "_ai_context_lijst.html", view.as_context())


def _record_view(
    request: Request, db: Session, segment: str, item_id: int, terug: str, editing: bool
):
    """One document, page or note: what the row showed — its status, the read text
    of a document, the texts for Raakje or the note — and what the row did:
    Bewerken, Aan/uit, Opnieuw lezen and Verwijderen, each where the row had it.
    A document without a row has only Opnieuw lezen, as before; a page without a
    row has Bewerken and Aan/uit, which make its row at their first use (#1791)."""
    from app.domains.chatbot.api import context_item
    from app.domains.chatbot.viewmodels import AiContextRecordView
    from app.ui import delete_question, way_back

    kind = KINDS[segment]
    item = context_item(db, kind, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    info = item if kind == "note" else item["info"]
    record_url = f"{PAGE}/{segment}/{item_id}"
    back = way_back(db, terug, f"{PAGE}?segment={segment}")
    keep = f"?terug={quote(terug, safe='/')}" if terug else ""

    if kind == "document":
        title = item["label"]
        facts = [{"text": _("Document")}]
        if info and info.get("extracted_at"):
            facts.append(
                {"text": _("gelezen op %(datum)s") % {"datum": short_date(info["extracted_at"])}}
            )
        row_base = f"{PAGE}/{info['id']}" if info else ""
        form_url = f"{row_base}/bewerken" if info else ""
    elif kind == "page":
        title = item["title"]
        facts = [{"text": _("Pagina")}]
        row_base = f"{PAGE}/paginas/{item_id}"
        form_url = f"{row_base}/bewerken"
    else:
        title = item["title"] or _("Notitie #%(id)s") % {"id": item_id}
        facts = [{"text": _("Notitie")}]
        row_base = f"{PAGE}/{item_id}"
        form_url = f"{row_base}/bewerken"

    actions: list[dict] = []
    if row_base:
        on = info is None or info["is_active"]
        actions.append(
            {
                "kind": "record",
                "verb": "state",
                "label": _("Zet uit") if on else _("Zet aan"),
                "attrs": f'hx-post="{row_base}/toggle"',
            }
        )
    if kind == "document":
        actions.append(
            {
                "kind": "tool",
                "label": _("Opnieuw lezen"),
                "attrs": f'hx-post="{PAGE}/documenten/{item_id}/opnieuw-lezen"',
                "confirm": _("De tekst van dit document opnieuw inlezen?"),
            }
        )
    if info:
        actions.append(
            {
                "kind": "delete",
                "label": _("Verwijderen"),
                "attrs": f'hx-post="{PAGE}/{info["id"]}/verwijderen"'
                + f' hx-vals=\'{{"segment": "{segment}"}}\'',
                "confirm": delete_question(_("Contextrij"), title),
            }
        )
    editable = bool(form_url)
    return AiContextRecordView(
        kind=kind,
        title=title,
        badges=[_status(info)],
        facts=facts,
        primary={
            "label": _("Bewerken"),
            "href": f"{record_url}?bewerken=1"
            + (f"&terug={quote(terug, safe='/')}" if terug else ""),
        }
        if editable and not editing
        else None,
        actions=actions if not editing else [],
        way_back=back,
        editing=editing and editable,
        item=item,
        info=info,
        form_url=form_url,
        record_url=record_url + keep,
        csrf_token=csrf_token_for(request.cookies.get(SESSION_COOKIE) or ""),
        nav_items=admin_nav(PAGE, request),
    )


@router.get("/admin/ai-context/notities/nieuw", response_class=HTMLResponse)
def note_new(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_VIEW)),
):
    """A new note: the form the list carried under its notes (#2124). Shown to who
    may see the list, as the form was; saving asks `settings.manage`."""
    from app.domains.chatbot.viewmodels import AiContextNoteNewView
    from app.ui import way_back

    view = AiContextNoteNewView(
        way_back=way_back(db, "", f"{PAGE}?segment=notities"),
        csrf_token=csrf_token_for(request.cookies.get(SESSION_COOKIE) or ""),
        nav_items=admin_nav(PAGE, request),
    )
    return templates.TemplateResponse(request, "ai_context_notitie_nieuw.html", view.as_context())


@router.get("/admin/ai-context/{segment}/{item_id}", response_class=HTMLResponse)
def ai_context_record(
    request: Request,
    segment: str,
    item_id: int,
    terug: str = "",
    bewerken: str = "",
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_VIEW)),
):
    if segment not in KINDS:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    view = _record_view(request, db, segment, item_id, terug, editing=bool(bewerken))
    return templates.TemplateResponse(request, "ai_context_item.html", view.as_context())


@router.post("/admin/ai-context/notities", dependencies=[Depends(require_csrf)])
def notitie_toevoegen(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_MANAGE)),
    title: str = Form(""),
    text_addition: str = Form(""),
):
    from app.domains.chatbot.api import InfoRefused, add_note
    from app.kernel.refusals import FieldError
    from app.ui import refusal_response

    try:
        note = add_note(db, title=title, text=text_addition)
    except InfoRefused as refusal:
        return refusal_response(request, [FieldError("", str(refusal))], "#ai-context-melding")
    return _redirect(request, f"{PAGE}/notities/{note['id']}")


def _record_of_row(db: Session, row_id: int) -> str:
    """The record a row belongs to: its document, its page, or the note itself."""
    from app.domains.chatbot.api import get_row

    row = get_row(db, row_id)
    if row.media_asset_id is not None:
        return f"{PAGE}/documenten/{row.media_asset_id}"
    if row.cms_page_id is not None:
        return f"{PAGE}/paginas/{row.cms_page_id}"
    return f"{PAGE}/notities/{row.id}"


@router.post("/admin/ai-context/{row_id}/bewerken", dependencies=[Depends(require_csrf)])
def rij_bewerken(
    row_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_MANAGE)),
    title: str = Form(""),
    text_override: str = Form(""),
    text_addition: str = Form(""),
):
    from app.domains.chatbot.api import get_row, update_row
    from app.schemas.chatbot_info import ChatbotInfoEdit

    try:
        ci = get_row(db, row_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=_("Rij niet gevonden"))
    update_row(
        db,
        row_id,
        ChatbotInfoEdit(
            title=title.strip() or None,
            text_override=text_override.strip() or None,
            text_addition=text_addition.strip() or None,
            is_active=ci.is_active,
            sort_order=ci.sort_order,
        ),
    )
    return _redirect(request, _record_of_row(db, row_id))


@router.post("/admin/ai-context/paginas/{page_id}/toggle", dependencies=[Depends(require_csrf)])
def page_toggle(
    page_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_MANAGE)),
):
    """A page's switch goes by the page, not by its info row: a page that never
    got a row can be switched off too (#1791)."""
    from app.domains.chatbot.api import toggle_page

    try:
        toggle_page(db, page_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=_("Pagina niet gevonden"))
    return _redirect(request, f"{PAGE}/paginas/{page_id}")


@router.post("/admin/ai-context/paginas/{page_id}/bewerken", dependencies=[Depends(require_csrf)])
def page_edit(
    page_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_MANAGE)),
    text_override: str = Form(""),
    text_addition: str = Form(""),
):
    from app.domains.chatbot.api import edit_page

    try:
        edit_page(db, page_id, text_override=text_override, text_addition=text_addition)
    except LookupError:
        raise HTTPException(status_code=404, detail=_("Pagina niet gevonden"))
    return _redirect(request, f"{PAGE}/paginas/{page_id}")


@router.post(
    "/admin/ai-context/documenten/{asset_id}/opnieuw-lezen", dependencies=[Depends(require_csrf)]
)
def document_opnieuw_lezen(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_MANAGE)),
):
    """'Opnieuw lezen' (#235): her-extraheer de tekst van een document-asset. Draait
    op de achtergrond; override/aanvulling blijven staan."""
    from app.domains.chatbot.api import read_document_again

    try:
        read_document_again(db, asset_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=_("Document niet gevonden"))
    return _redirect(request, f"{PAGE}/documenten/{asset_id}")


@router.post("/admin/ai-context/{row_id}/verwijderen", dependencies=[Depends(require_csrf)])
def rij_verwijderen(
    row_id: int,
    request: Request,
    segment: str = Form(""),
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_MANAGE)),
):
    """Delete a row — for a document or a page that is back to its default, for a
    note the note — and back to the list of its kind."""
    from app.domains.chatbot.api import delete_row

    try:
        delete_row(db, row_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=_("Rij niet gevonden"))
    return _redirect(request, f"{PAGE}?segment={_segment(segment)}")


@router.post("/admin/ai-context/{row_id}/toggle", dependencies=[Depends(require_csrf)])
def rij_toggle(
    row_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_MANAGE)),
):
    from app.domains.chatbot.api import toggle_row

    try:
        toggle_row(db, row_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=_("Rij niet gevonden"))
    return _redirect(request, _record_of_row(db, row_id))
