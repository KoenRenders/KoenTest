"""The newsletter screens (CR-05, #984): letters, sending, subscribers.

Every route asks a right (CR-24): `newsletter.view` to look, `newsletter.manage`
to change. The paths are Dutch because
a board member reads them in the address bar; everything else is English.

A draft and a sent letter share one address, `/admin/nieuwsbrieven/{id}`: a
draft opens the composer, a letter that is (being) sent opens its archive. The
status decides, so a bookmark never leads to an editor for something that
already left.
"""

from __future__ import annotations

import json
import logging
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

import app.domains.mail.api as mail
from app.database import get_db
from app.domains.auth.api import (
    SESSION_COOKIE,
    Right,
    csrf_token_for,
    require_csrf,
    require_right,
)
from app.domains.cms.api import schema
from app.domains.newsletter import api as nb
from app.domains.newsletter.viewmodels import (
    AudienceLine,
    NewsletterAppliedView,
    NewsletterArchiveView,
    NewsletterChoicesView,
    NewsletterComposeView,
    NewsletterConversationView,
    NewsletterHead,
    NewsletterListView,
    NewsletterNoticeView,
    NewsletterParticipantsView,
    NewsletterPickerView,
    NewsletterSendView,
    NewsletterSettingsView,
    SubscriberImportView,
    SubscriberListView,
    SubscriberNewView,
)
from app.i18n import _, clock_time, local_moment, short_date, short_datetime
from app.kernel.clock import belgian_day, belgian_today
from app.kernel.codes import code_label, code_labels, code_of, register_tones, tone
from app.kernel.refusals import FieldError
from app.ui import (
    PER_PAGE_OPTIONS,
    admin_nav,
    delete_question,
    filterparams,
    is_fragment_request,
    per_page_from,
    refusal_response,
    templates,
)

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)

NAV = "/admin/nieuwsbrieven"
# The import file stays small: one address per line, about 800 of them. A
# megabyte is a hundred times that, and still refuses a file picked by mistake.
MAX_IMPORT_BYTES = 1_000_000
# A programme or a flyer, not a photo album.
MAX_ATTACHMENT_BYTES = 10_000_000

# The words of these five lists live in their label tables since CR-12 phase 3
# and are read with `code_label()`. What stays in Python is the **tone** of a
# badge: a design-system decision, not a translation (§B4.5), registered here
# next to the screen that draws it. Total by construction and by gate.
register_tones(
    nb.LETTER_STATUS.name,
    {
        nb.LetterStatus.DRAFT: "gray",
        nb.LetterStatus.SENDING: "blue",
        nb.LetterStatus.SENT: "green",
    },
)
register_tones(
    nb.DELIVERY_STATUS.name,
    {
        nb.DeliveryStatus.QUEUED: "gray",
        nb.DeliveryStatus.SENT: "green",
        nb.DeliveryStatus.FAILED: "yellow",
        nb.DeliveryStatus.SKIPPED: "gray",
    },
)
register_tones(
    nb.SUBSCRIBER_STATUS.name,
    {
        nb.SubscriberStatus.CONFIRMED: "green",
        nb.SubscriberStatus.PENDING: "yellow",
        nb.SubscriberStatus.UNSUBSCRIBED: "gray",
    },
)


def _csrf(request: Request) -> str:
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


def _base_url(db: Session) -> str:
    from app.kernel.tenant_config import tenant_base_url

    return tenant_base_url(db).rstrip("/")


def _go(request: Request, target: str) -> Response:
    """Navigate for real after a POST — the shell is boosted, so a plain 303
    would be swapped in without the address bar following."""
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=303)


def _letter_or_404(db: Session, newsletter_id: int):
    letter = nb.get_newsletter(db, newsletter_id)
    if letter is None:
        raise HTTPException(status_code=404, detail=_("Nieuwsbrief niet gevonden."))
    return letter


def _raakje_enabled(db: Session) -> bool:
    from app.kernel.tenant_config import tenant_admin_chat_enabled

    return tenant_admin_chat_enabled(db)


# ── The list ─────────────────────────────────────────────────────────────────


def _list_view(
    request: Request, db: Session, error: Optional[str] = None, oob: bool = False
) -> NewsletterListView:
    """Nieuwsbrieven on the kit's list page (#2123): the statuses as the segments with
    their counts, the search on the subject, the table."""
    from app.ui.list_state import page_of, read_state, segments_of

    # Three segments, as the concept draws them: four with their counts are wider than a
    # phone (measured at 390 px, 41 px). A letter that is still going out counts with the
    # sent ones — its row says "Wordt verstuurd" on its own badge.
    gone = (nb.LetterStatus.SENDING.value, nb.LetterStatus.SENT.value)
    statuses = [nb.LetterStatus.DRAFT.value, nb.LetterStatus.SENT.value]
    state = read_state(request, statuses)
    everyone = nb.list_newsletters(db, query=state.q)

    def _in(letter, status: str) -> bool:
        code = code_of(letter.status)
        return code in gone if status == nb.LetterStatus.SENT.value else code == status

    shown = [lt for lt in everyone if not state.status or _in(lt, state.status)]
    letters, total, page = page_of(shown, state)
    progress = {
        letter.id: nb.progress_of(db, letter)
        for letter in letters
        if letter.status != nb.LetterStatus.DRAFT
    }
    moments = {}
    for letter in letters:
        if letter.status == nb.LetterStatus.DRAFT:
            moments[letter.id] = _("laatst bewaard %(m)s") % {
                "m": short_datetime(letter.updated_at)
            }
        elif letter.status == nb.LetterStatus.SENDING:
            moments[letter.id] = _("gestart %(m)s") % {"m": short_datetime(letter.send_started_at)}
        else:
            moments[letter.id] = _("verstuurd %(m)s") % {
                "m": short_datetime(letter.send_finished_at)
            }
    labels = dict(code_labels(nb.LETTER_STATUS.name, db=db))
    return NewsletterListView(
        letters=letters,
        q=state.q,
        status=state.status,
        status_labels={
            lt.id: code_label(nb.LETTER_STATUS.name, lt.status, db=db) for lt in letters
        },
        status_tones={lt.id: tone(nb.LETTER_STATUS.name, lt.status) for lt in letters},
        audience_labels={
            lt.id: (
                code_label(nb.AUDIENCE.name, lt.audience, db=db)
                if lt.audience
                else _("nog niet gekozen")
            )
            for lt in letters
        },
        progress=progress,
        moments=moments,
        results=nb.results_of(db, list(progress)),
        columns=[
            {"key": "onderwerp", "label": _("Onderwerp"), "cell": "name"},
            {"key": "status", "label": _("Status"), "cell": "status"},
            {"key": "doelgroep", "label": _("Doelgroep"), "cell": "extra", "priority": 1},
            {"key": "resultaat", "label": _("Geopend · geklikt"), "cell": "extra", "priority": 2},
            {"key": "moment", "label": _("Bijgewerkt"), "cell": "moment"},
        ],
        segments=segments_of(
            [(code, labels[code]) for code in statuses],
            {code: sum(1 for lt in everyone if _in(lt, code)) for code in statuses},
            len(everyone),
            _("Alle"),
        ),
        page=page,
        per_page=state.per_page,
        total=total,
        page_sizes=list(PER_PAGE_OPTIONS),
        pager_url=f"{NAV}?{state.query()}",
        empty_reason=(
            _("Geen nieuwsbrieven gevonden.")
            if (state.q or state.status)
            else _("Nog geen nieuwsbrieven. Maak er een aan — Raakje kan meeschrijven.")
        ),
        csrf_token=_csrf(request),
        error=error,
        oob=oob,
        nav_items=[] if oob else admin_nav(NAV, request),
    )


@router.get("/admin/nieuwsbrieven", response_class=HTMLResponse)
def newsletter_list(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_VIEW)),
):
    fragment = is_fragment_request(request)
    view = _list_view(request, db, oob=fragment)
    template = "_nb_lijst.html" if fragment else "admin_nieuwsbrieven.html"
    return templates.TemplateResponse(request, template, view.as_context())


@router.post(
    "/admin/nieuwsbrieven", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
def newsletter_create(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
):
    """A new, empty draft — the composer is its own full page (no modal), open for
    editing: there is nothing to read yet (#2183)."""
    letter = nb.create_newsletter(db, created_by=email)
    return _go(request, f"/admin/nieuwsbrieven/{letter.id}?bewerken=1")


# ── Subscribers ──────────────────────────────────────────────────────────────
# Declared before `/{newsletter_id}`; the id also carries an `:int` converter,
# so "abonnees" can never be read as a letter.


SUBSCRIBERS = "/admin/nieuwsbrieven/abonnees"
SUBSCRIBERS_LIST = SUBSCRIBERS + "/lijst"


def _subscriber_state(request: Request) -> dict:
    """The list's state from the URL (the toolbar's form pushes it; a row's
    mutation reads it back from the current URL, so Uitschrijven keeps the filter)."""
    stand = filterparams(request)
    status = (stand.get("status") or "").strip()
    sort = (stand.get("sort") or "").strip()
    try:
        page = max(1, int(stand.get("page") or 1))
    except ValueError:
        page = 1
    return {
        "q": (stand.get("q") or "").strip(),
        "status": status if status in {m.value for m in nb.SubscriberStatus} else "",
        "sort": sort if sort.lstrip("-") == "since" else "",
        "page": page,
        "per_page": per_page_from(stand.get("per_page")),
    }


def _subscriber_figures(counts: dict[str, int]) -> list[dict]:
    """The figures of the title row (§5.1; Koen, CR-11 Q28: the figure is acted on weekly)."""
    return [
        {
            "value": str(counts["confirmed"]),
            "label": _("Bevestigd"),
            "title": _("Adressen die hun inschrijving bevestigden."),
        },
        {
            "value": str(counts["pending"]),
            "label": _("Wachten"),
            "title": _("Adressen die hun inschrijving nog moeten bevestigen."),
        },
        {
            "value": str(counts["unsubscribed"]),
            "label": _("Uitgeschreven"),
            "title": _("Adressen die zich uitschreven."),
        },
    ]


def _subscriber_view(
    request: Request, db: Session, error: Optional[str] = None, **extra
) -> SubscriberListView:
    s = _subscriber_state(request)
    oldest_first = s["sort"] == "since"
    rows = nb.list_subscribers(
        db,
        query=s["q"],
        status=s["status"],
        oldest_first=oldest_first,
        page=s["page"],
        per_page=s["per_page"],
    )
    total = nb.count_subscribers(db, query=s["q"], status=s["status"])
    post = 'hx-target="#nb-abonnees" hx-swap="innerHTML" hx-post="/admin/nieuwsbrieven/abonnees'
    row_controls = {
        s_.id: {
            "action": {
                "label": _("Uitschrijven"),
                "attrs": f'{post}/{s_.id}/uitschrijven"',
                "confirm": _("%(adres)s uitschrijven? Het adres krijgt geen nieuwsbrief meer.")
                % {"adres": s_.email},
            }
            if s_.status is not nb.SubscriberStatus.UNSUBSCRIBED
            else None,
            # Verwijderen wist het adres helemaal — ook in het archief (recht op
            # vergetelheid). Uitschrijven bewaart de keuze; verwijderen bewaart niets.
            "menu": [
                {
                    "kind": "delete",
                    "label": _("Verwijderen"),
                    "attrs": f'{post}/{s_.id}/verwijderen"',
                    "confirm": delete_question(_("Adres"), s_.email),
                }
            ],
        }
        for s_ in rows
    }
    counts = nb.subscriber_counts(db)
    filters = {k: s[k] for k in ("q", "status") if s[k]}
    way = {**filters, "per_page": s["per_page"]}
    next_sort = "" if s["sort"] == "since" else "since"
    since_query = urlencode({**way, "sort": next_sort})
    return SubscriberListView(
        subscribers=rows,
        counts=counts,
        figures=_subscriber_figures(counts),
        # In the order and the words of §5.1 (the code list's own order and label —
        # "Wacht op bevestiging" — are for the badge of a row).
        segments=[
            {"value": "", "label": _("Alle")},
            {"value": nb.SubscriberStatus.CONFIRMED.value, "label": _("Bevestigd")},
            {"value": nb.SubscriberStatus.PENDING.value, "label": _("Wachten")},
            {"value": nb.SubscriberStatus.UNSUBSCRIBED.value, "label": _("Uitgeschreven")},
        ],
        columns=[
            {"key": "email", "label": _("Adres"), "cell": "name"},
            # Koen, 16 October 2026 ("b"): on a wide screen Bron before Voornaam —
            # priority 2 shows from a narrower table than priority 1.
            {"key": "first_name", "label": _("Voornaam"), "cell": "extra", "priority": 1},
            {"key": "source", "label": _("Bron"), "cell": "extra", "priority": 2},
            {"key": "status", "label": _("Status"), "cell": "status"},
            {
                "key": "since",
                "label": _("Sinds"),
                "cell": "moment",
                "sort_url": f"{SUBSCRIBERS_LIST}?{since_query}",
                "sort_page_url": f"{SUBSCRIBERS}?{since_query}",
                "sorted": "asc" if oldest_first else "desc",
            },
            {"key": "actions", "label": _("Acties"), "cell": "actions"},
        ],
        row_controls=row_controls,
        source_labels={
            s_.id: (
                _("import %(d)s") % {"d": nb.short_date(local_moment(s_.imported_at).date())}
                if s_.source == nb.SubscriberSource.IMPORT and s_.imported_at
                else code_label(nb.SUBSCRIBER_SOURCE.name, s_.source, db=db)
            )
            for s_ in rows
        },
        moments={s_.id: short_datetime(s_.confirmed_at or s_.created_at) for s_ in rows},
        q=s["q"],
        status=s["status"],
        sort=s["sort"],
        sort_options=[("", _("Recentste eerst")), ("since", _("Oudste eerst"))],
        page=s["page"],
        per_page=s["per_page"],
        total=total,
        page_sizes=list(PER_PAGE_OPTIONS),
        pager_url=f"{SUBSCRIBERS_LIST}?{urlencode({**way, 'sort': s['sort']})}",
        empty_reason=_("Geen abonnees die hierbij passen.")
        if filters
        else _("Er zijn nog geen abonnees."),
        csrf_token=_csrf(request),
        error=error,
        **extra,
    )


@router.get(SUBSCRIBERS, response_class=HTMLResponse)
def subscriber_list(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_VIEW)),
    toegevoegd: str = "",
):
    notice = _("%(adres)s staat op de lijst.") % {"adres": toegevoegd} if toegevoegd else None
    view = _subscriber_view(request, db, notice=notice, nav_items=admin_nav(NAV, request))
    return templates.TemplateResponse(request, "admin_abonnees.html", view.as_context())


@router.get(SUBSCRIBERS_LIST, response_class=HTMLResponse)
def subscriber_fragment(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_VIEW)),
):
    """The list alone: the toolbar swaps this fragment, so the search field is not
    replaced under the fingers."""
    view = _subscriber_view(request, db, oob=True)
    return templates.TemplateResponse(request, "_nb_abonnees.html", view.as_context())


@router.get(SUBSCRIBERS + "/nieuw", response_class=HTMLResponse)
def subscriber_new(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_VIEW)),
):
    return templates.TemplateResponse(
        request, "admin_abonnee_nieuw.html", _subscriber_new_view(request).as_context()
    )


def _subscriber_new_view(request: Request) -> SubscriberNewView:
    return SubscriberNewView(csrf_token=_csrf(request), nav_items=admin_nav(NAV, request))


@router.post(
    SUBSCRIBERS,
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def subscriber_add(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
    subscriber_email: str = Form(""),
    first_name: str = Form(""),
):
    """The page "+ Adres" opens: on success back to the list, with the address named;
    on a refusal its reason in the page's message line."""
    try:
        row = nb.add_by_admin(db, subscriber_email, first_name)
    except nb.NewsletterError as exc:
        return refusal_response(
            request, [FieldError("subscriber_email", str(exc))], "#abonnee-melding", send=True
        )
    return Response(
        status_code=204,
        headers={"HX-Redirect": f"{SUBSCRIBERS}?{urlencode({'toegevoegd': row.email})}"},
    )


@router.post(
    "/admin/nieuwsbrieven/abonnees/{subscriber_id:int}/uitschrijven",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def subscriber_unsubscribe(
    subscriber_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
):
    nb.unsubscribe_by_admin(db, subscriber_id)
    return templates.TemplateResponse(
        request, "_nb_abonnees.html", _subscriber_view(request, db, oob=True).as_context()
    )


@router.post(
    "/admin/nieuwsbrieven/abonnees/{subscriber_id:int}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def subscriber_erase(
    subscriber_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
):
    """The right to erasure: the address disappears, also from the archive."""
    nb.erase(db, subscriber_id)
    return templates.TemplateResponse(
        request, "_nb_abonnees.html", _subscriber_view(request, db, oob=True).as_context()
    )


def _import_view(
    request: Request, preview=None, text: str = "", error: Optional[str] = None
) -> SubscriberImportView:
    return SubscriberImportView(
        preview=preview,
        text=text,
        csrf_token=_csrf(request),
        error=error,
        nav_items=admin_nav(NAV, request),
    )


@router.get("/admin/nieuwsbrieven/abonnees/import", response_class=HTMLResponse)
def subscriber_import_screen(
    request: Request, _email: str = Depends(require_right(Right.NEWSLETTER_VIEW))
):
    return templates.TemplateResponse(
        request, "admin_abonnees_import.html", _import_view(request).as_context()
    )


@router.post(
    "/admin/nieuwsbrieven/abonnees/import",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def subscriber_import_preview(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
    file: UploadFile = File(...),
):
    """Step 1 → 2: read the file and show what would happen. Nothing is written."""
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        return templates.TemplateResponse(
            request,
            "_nb_import.html",
            _import_view(
                request, error=_("Dit bestand is te groot voor een adressenlijst.")
            ).as_context(),
        )
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    preview = nb.preview_import(db, text)
    return templates.TemplateResponse(
        request, "_nb_import.html", _import_view(request, preview=preview, text=text).as_context()
    )


@router.post(
    "/admin/nieuwsbrieven/abonnees/import/bevestigen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def subscriber_import_run(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
    text: str = Form(""),
):
    """Step 2 → done. The rules are applied again to the text, not to the
    numbers the preview showed: what is written is what is allowed now."""
    result = nb.run_import(db, text)
    view = _subscriber_view(
        request,
        db,
        notice=_("%(n)s adressen toegevoegd. Gekende en uitgeschreven adressen bleven ongewijzigd.")
        % {"n": len(result.new)},
        nav_items=admin_nav(NAV, request),
    )
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": "/admin/nieuwsbrieven/abonnees"})
    return templates.TemplateResponse(request, "admin_abonnees.html", view.as_context())


# ── Settings ─────────────────────────────────────────────────────────────────


def _settings_view(
    request: Request, db: Session, notice: Optional[str] = None, error: Optional[str] = None
) -> NewsletterSettingsView:
    from app.kernel.tenant_config import (
        NEWSLETTER_DAILY_CAP_DEFAULT,
        tenant_newsletter_daily_cap,
        tenant_newsletter_house_style,
    )

    return NewsletterSettingsView(
        house_style=tenant_newsletter_house_style(db),
        daily_cap=tenant_newsletter_daily_cap(db),
        daily_cap_default=NEWSLETTER_DAILY_CAP_DEFAULT,
        csrf_token=_csrf(request),
        notice=notice,
        error=error,
        nav_items=admin_nav(NAV, request),
    )


@router.get("/admin/nieuwsbrieven/instellingen", response_class=HTMLResponse)
def settings_screen(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_VIEW)),
):
    return templates.TemplateResponse(
        request, "admin_nieuwsbrief_instellingen.html", _settings_view(request, db).as_context()
    )


@router.post(
    "/admin/nieuwsbrieven/instellingen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def settings_save(
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
    house_style: str = Form(""),
    daily_cap: str = Form(""),
):
    try:
        cap = int(daily_cap) if daily_cap.strip() else None
    except ValueError:
        cap = 0
    try:
        nb.save_settings(db, house_style=house_style, daily_cap=cap)
    except nb.NewsletterError as exc:
        return templates.TemplateResponse(
            request,
            "_nb_instellingen.html",
            _settings_view(request, db, error=str(exc)).as_context(),
        )
    return templates.TemplateResponse(
        request,
        "_nb_instellingen.html",
        _settings_view(request, db, notice=_("Bewaard.")).as_context(),
    )


# ── One letter ───────────────────────────────────────────────────────────────


def _choices(db: Session, letter) -> list[dict]:
    """The three groups as the page shows them (#1562)."""
    chosen = nb.choices_of(db, letter)
    facts = nb.activity_facts(db, chosen.all_ids, base_url=_base_url(db))

    def group(key: str, title: str, hint: str, ids, can_add: bool = True) -> dict:
        items = [facts[i] for i in ids if i in facts]
        return {"key": key, "title": title, "hint": hint, "items": items, "can_add": can_add}

    return [
        group(
            "past",
            _("Voorbije activiteiten"),
            _("Wat doorging sinds de vorige nieuwsbrief: Raakje blikt erop terug."),
            chosen.past,
        ),
        group(
            "featured",
            _("Uitgelicht"),
            _("Hoogstens drie. Elk wordt een blok met affiche, omschrijving en inschrijflink."),
            chosen.featured,
            can_add=len(chosen.featured) < nb.FEATURED_MAX,
        ),
        group(
            "calendar",
            _("In de kalender"),
            _("Eén blok met een regel per activiteit; de uitgelichte staan er ook in."),
            chosen.calendar,
        ),
    ]


def _proposal_fields(shown: dict) -> list[dict]:
    """Which fields of the page a proposal touches — for marking them while it
    is offered. The values come with Toepassen (`raakje_apply`)."""
    fields = []
    if shown.get("subject"):
        fields.append({"name": "subject", "label": _("Onderwerp")})
    if shown.get("preview"):
        fields.append({"name": "preview_text", "label": _("Voorbeeldtekst")})
    fields.append({"name": "body", "label": _("Inhoud")})
    return fields


def _turn_views(db: Session, letter, messages: list) -> list[dict]:
    """The conversation as turns — a question and its answer — oldest first, as
    the panel reads them."""
    turns: list[dict] = []
    for message in messages:
        if message.role == nb.MessageRole.AUTHOR or not turns:
            turns.append({"question": "", "answer": "", "proposal": None, "failed": False})
        turn = turns[-1]
        if message.role == nb.MessageRole.AUTHOR:
            turn["question"] = message.text
            continue
        turn["answer"] = message.text
        if message.proposal:
            shown = nb.display_proposal(db, letter, message)
            shown["fields"] = _proposal_fields(shown)
            # What the screen needs, decided here and not compared in the
            # template (§B4.7): may it still be applied, and if not, why.
            status = shown.get("status")
            shown["open"] = status == "open" and not shown.get("stale")
            if status == "applied":
                shown["closed_text"] = _("Toegepast.")
            elif status == "open":
                shown["closed_text"] = _(
                    "De brief veranderde sinds dit voorstel. Vraag het opnieuw."
                )
            else:
                shown["closed_text"] = _("Voorstel genegeerd.")
            turn["proposal"] = shown
    return turns


def _head(request: Request, db: Session, letter) -> NewsletterHead:
    """The facts of the record head: whom the letter goes to and when it was last
    saved (#2113)."""
    facts: list[dict[str, str]] = []
    if letter.audience:
        facts.append({"text": code_label(nb.AUDIENCE.name, letter.audience, db=db)})
    else:
        facts.append({"text": _("Nog geen doelgroep")})
    saved = letter.updated_at
    if belgian_day(saved) == belgian_today():
        facts.append({"text": _("Opgeslagen om %(tijd)s") % {"tijd": clock_time(saved)}})
    else:
        facts.append(
            {
                "text": _("Opgeslagen op %(dag)s om %(tijd)s")
                % {"dag": short_date(saved), "tijd": clock_time(saved)}
            }
        )
    return NewsletterHead(
        letter=letter,
        title=letter.subject or _("Nieuwe nieuwsbrief"),
        facts=facts,
        csrf_token=_csrf(request),
        delete_confirm=delete_question(_("Concept"), letter.subject or _("zonder onderwerp")),
    )


def _audience_options(db: Session) -> list[tuple[str, str]]:
    """`(code, label)` per audience on offer, in the code list's order. The value is the
    CODE: it goes into the form as the radio's value, so the template never renders an
    enum member into an attribute (CR-12 phase 3). How many addresses each one reaches
    is said under the choice (`_audience_said`), not on the choice."""
    options = [
        (audience.value, code_label(nb.AUDIENCE.name, audience, db=db))
        for audience in (nb.Audience.MEMBERS, nb.Audience.NON_MEMBERS, nb.Audience.BOTH)
    ]
    # CR-19 (#1477): without the membership module there are no members, so the
    # letter goes to its subscribers — "both" reaches exactly them — offered as
    # the one choice "Iedereen".
    from app.domains.mdm.api import module_enabled
    from app.kernel.modules import ModuleCode

    if not module_enabled(ModuleCode.MEMBERSHIP):
        options = [(nb.Audience.BOTH.value, _("Iedereen"))]
    # CR-36: the fourth audience reads the registrations, so only a tenant with the
    # activities module is offered it.
    if module_enabled(ModuleCode.ACTIVITIES):
        options.append(
            (
                nb.Audience.PARTICIPANTS.value,
                code_label(nb.AUDIENCE.name, nb.Audience.PARTICIPANTS, db=db),
            )
        )
    return options


def _notice_view(error: Optional[str] = None, notice: Optional[str] = None) -> NewsletterNoticeView:
    return NewsletterNoticeView(error=error, notice=notice)


def _compose_view(
    request: Request,
    db: Session,
    letter,
    error: Optional[str] = None,
    notice: Optional[str] = None,
    choices_error: Optional[str] = None,
    editing: bool = False,
) -> NewsletterComposeView:
    featured_options = _featured_options(db, letter)
    editor_config = schema.schema_for(
        "letter", letter_activities=[(o["id"], o["label"]) for o in featured_options]
    )
    # Who each audience is, in words: what the send screen says of "both" names the two
    # lists and what they share, so it is said here once for all the choices — one
    # function, one wording (#1834). Without the membership module it names the
    # subscribers only (CR-19, #1477).
    lines, overlap, _send_label, _count = _audience_said(db, nb.Audience.BOTH)
    participant_offered, participant_lines, participant_notes = _participant_panel(db, letter)
    return NewsletterComposeView(
        head=_head(request, db, letter),
        letter=letter,
        editing=editing,
        subject=letter.subject or "",
        preview_text=letter.preview_text or "",
        audience=code_of(letter.audience) or "",
        audience_options=_audience_options(db),
        audience_label=code_label(nb.AUDIENCE.name, letter.audience, db=db)
        if letter.audience
        else "",
        audience_lines=lines,
        audience_overlap=overlap,
        participants_shown=letter.audience == nb.Audience.PARTICIPANTS,
        participant_offered=participant_offered,
        participant_lines=participant_lines,
        participant_notes=participant_notes,
        body_json=json.dumps(letter.body_document),
        editor_config=editor_config,
        featured_options=featured_options,
        button_pages=_button_pages(db),
        raakje_enabled=_raakje_enabled(db),
        choices=_choices(db, letter),
        report_count=len(nb.reports_since_previous_letter(db)),
        csrf_token=_csrf(request),
        error=error,
        notice=notice,
        choices_error=choices_error,
        nav_items=admin_nav(NAV, request),
    )


def _participant_said(db: Session, letter) -> tuple[list[AudienceLine], list[str], int]:
    """Who a letter to *Eerdere deelnemers* goes to, in words (CR-36): the line for the
    send screen and the panel, what was left out, and the number of recipients. The
    numbers are the service's (`participant_recipients`); only the words are made here."""

    def ngettext(one: str, many: str, n: int) -> str:
        return _(one) if n == 1 else _(many)

    _recipients, said = nb.participant_recipients(db, letter)
    notes: list[str] = []
    if not said.activities:
        line = AudienceLine(
            head=_("Eerdere deelnemers · 0 adressen"),
            sentence=_("Kies één of meer activiteiten waarop de ontvangers waren ingeschreven."),
        )
    else:
        which = ", ".join(f"{name} ({nb.short_date(day)})" for name, day in said.activities)
        addresses = ngettext("%(num)s adres", "%(num)s adressen", said.recipients) % {
            "num": said.recipients
        }
        sentence = _("%(adressen)s van mensen die waren ingeschreven op %(wat)s") % {
            "adressen": addresses,
            "wat": which,
        }
        shared = []
        if said.as_member:
            shared.append(
                ngettext(
                    "%(num)s krijgt hem al als lid",
                    "%(num)s krijgen hem al als lid",
                    said.as_member,
                )
                % {"num": said.as_member}
            )
        if said.as_subscriber:
            shared.append(
                ngettext(
                    "%(num)s krijgt hem als abonnee",
                    "%(num)s krijgen hem als abonnee",
                    said.as_subscriber,
                )
                % {"num": said.as_subscriber}
            )
        if shared:
            sentence += _(", waarvan %(wie)s") % {"wie": " en ".join(shared)}
        line = AudienceLine(
            head=_("Eerdere deelnemers · %(adressen)s") % {"adressen": addresses},
            sentence=sentence + ".",
        )
    for name in said.dropped:
        notes.append(
            _(
                "De activiteit “%(naam)s” bestaat niet meer of is geannuleerd: ze is uit de lijst gehaald."
            )
            % {"naam": name}
        )
    if said.unsubscribed:
        notes.append(
            ngettext(
                "%(num)s adres heeft zich uitgeschreven en krijgt hem niet.",
                "%(num)s adressen hebben zich uitgeschreven en krijgen hem niet.",
                said.unsubscribed,
            )
            % {"num": said.unsubscribed}
        )
    if said.skipped:
        notes.append(
            ngettext(
                "%(num)s adres is geen geldig e-mailadres en wordt overgeslagen.",
                "%(num)s adressen zijn geen geldig e-mailadres en worden overgeslagen.",
                said.skipped,
            )
            % {"num": said.skipped}
        )
    return [line], notes, said.recipients


def _participant_panel(db: Session, letter) -> tuple[list, list[AudienceLine], list[str]]:
    """The list under the audience and what it says — empty unless the letter's
    audience is *Eerdere deelnemers*."""
    if letter.audience != nb.Audience.PARTICIPANTS:
        return [], [], []
    lines, notes, _count = _participant_said(db, letter)
    return nb.offered_activities(db, letter), lines, notes


def _button_pages(db: Session) -> list[tuple[int, str]]:
    """The pages of the site a button of the letter may lead to: the ones the site
    serves at an address (the same rule the page editor's button uses)."""
    from app.domains.cms.api import button_page_choices

    return button_page_choices(db)


def _featured_options(db: Session, letter) -> list[dict]:
    """The letter's featured activities as the editor's activity dialog lists them."""
    featured = nb.choices_of(db, letter).featured
    facts = nb.activity_facts(db, featured, base_url=_base_url(db))
    return [
        {"id": i, "label": f"{facts[i].name} · {nb.short_date(facts[i].start)}"}
        for i in featured
        if i in facts
    ]


def _choices_response(
    request: Request, db: Session, letter, error: Optional[str] = None
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "_nb_keuzes.html",
        NewsletterChoicesView(
            letter=letter,
            choices=_choices(db, letter),
            featured_options=_featured_options(db, letter),
            report_count=len(nb.reports_since_previous_letter(db)),
            raakje_enabled=_raakje_enabled(db),
            csrf_token=_csrf(request),
            choices_error=error,
        ).as_context(),
    )


def _archive_view(
    request: Request,
    db: Session,
    letter,
    status: str = "",
    q: str = "",
    error: Optional[str] = None,
    requeued: int = 0,
) -> NewsletterArchiveView:
    progress = nb.progress_of(db, letter)
    notice = ""
    if requeued:
        notice = (
            _("%(n)s mislukt adres staat opnieuw in de wachtrij.")
            if requeued == 1
            else _("%(n)s mislukte adressen staan opnieuw in de wachtrij.")
        ) % {"n": requeued}
    # Not a delete: the question keeps its own words and names the number (#1783).
    resend_question = (
        _("De nieuwsbrief opnieuw sturen naar %(n)s mislukt adres?")
        if progress.failed == 1
        else _("De nieuwsbrief opnieuw sturen naar %(n)s mislukte adressen?")
    ) % {"n": progress.failed}
    # A send button names whom it sends to (#1780), with the same count.
    resend_label = (
        _("Opnieuw versturen naar %(n)s mislukt adres")
        if progress.failed == 1
        else _("Opnieuw versturen naar %(n)s mislukte adressen")
    ) % {"n": progress.failed}
    deliveries = nb.deliveries_of(db, letter, status=status, query=q)
    return NewsletterArchiveView(
        letter=letter,
        # A letter that started to send shows the body it went with (frozen by
        # `start_sending`); the blocks of one that has not stand with today's data.
        body_html=nb.render_body(db, letter, base_url=letter.link_base or _base_url(db)),
        status_label=code_label(nb.LETTER_STATUS.name, letter.status, db=db),
        status_tone=tone(nb.LETTER_STATUS.name, letter.status),
        audience_label=code_label(nb.AUDIENCE.name, letter.audience or "", db=db),
        audience_activities=", ".join(
            f"{row.name or row.activity_id}"
            + (f" ({nb.short_date(row.last_date)})" if row.last_date else "")
            for row in nb.chosen_activities(db, letter)
        )
        if letter.audience == nb.Audience.PARTICIPANTS
        else "",
        progress=progress,
        expected=short_datetime(progress.expected_finish) if progress.expected_finish else "",
        started=short_datetime(letter.send_started_at),
        finished=short_datetime(letter.send_finished_at),
        deliveries=deliveries,
        delivery_options=code_labels(nb.DELIVERY_STATUS.name, db=db),
        moments={d.id: short_datetime(d.sent_at) for d in deliveries},
        result=nb.results_of(db, [letter.id])[letter.id],
        status_filter=status,
        q=q,
        csrf_token=_csrf(request),
        error=error,
        notice=notice,
        resend_question=resend_question,
        resend_label=resend_label,
        nav_items=admin_nav(NAV, request),
    )


@router.get("/admin/nieuwsbrieven/{newsletter_id:int}", response_class=HTMLResponse)
def newsletter_screen(
    newsletter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_VIEW)),
    status: str = "",
    q: str = "",
    opnieuw: int = 0,
    bewerken: int = 0,
):
    letter = _letter_or_404(db, newsletter_id)
    if letter.status == nb.LetterStatus.DRAFT:
        return templates.TemplateResponse(
            request,
            "admin_nieuwsbrief.html",
            _compose_view(request, db, letter, editing=bool(bewerken)).as_context(),
        )
    view = _archive_view(request, db, letter, status=status, q=q, requeued=opnieuw)
    template = (
        "_nb_afleveringen.html"
        if is_fragment_request(request)
        else "admin_nieuwsbrief_archief.html"
    )
    return templates.TemplateResponse(request, template, view.as_context())


@router.post(
    "/admin/nieuwsbrieven/{newsletter_id:int}/bewaren",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def newsletter_save(
    newsletter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
    subject: str = Form(""),
    preview_text: str = Form(""),
    audience: str = Form(""),
    body: str = Form(""),
    chosen: list[str] = Form([]),
):
    """Opslaan of the letter: the subject, the preview text, the audience, the earlier
    activities ticked under *Eerdere deelnemers* and the text, in one go (#2183).
    Nothing of the letter saves itself. A refusal stands on the page's message line and
    the form keeps what was typed; a saved letter sends the browser back to its page."""
    letter = _letter_or_404(db, newsletter_id)
    try:
        nb.update_draft(
            db,
            letter,
            subject=subject,
            body=body or None,
            audience=audience or None,
            preview_text=preview_text,
        )
        if letter.audience == nb.Audience.PARTICIPANTS:
            nb.set_participant_activities(db, letter, [int(c) for c in chosen if c.isdigit()])
    except nb.NewsletterError as exc:
        field = "audience" if letter.audience is None and audience else ""
        return refusal_response(request, [{"field": field, "message": str(exc)}], "#nb-melding")
    return _go(request, f"/admin/nieuwsbrieven/{letter.id}")


def _participants_response(request: Request, db: Session, letter, *, shown: bool = True):
    """The list under *Eerdere deelnemers* as a fragment: empty when the audience the
    page is about to save is another one."""
    return templates.TemplateResponse(
        request,
        "_nb_deelnemers.html",
        NewsletterParticipantsView(
            letter=letter,
            participants_shown=shown,
            participant_offered=nb.offered_activities(db, letter) if shown else [],
        ).as_context(),
    )


@router.get("/admin/nieuwsbrieven/{newsletter_id:int}/deelnemers", response_class=HTMLResponse)
def participants_panel(
    newsletter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_VIEW)),
    audience: str = "",
):
    """The list of earlier activities, loaded when the author picks *Eerdere
    deelnemers* — before the choice is saved, so the page says which audience it asks
    for. The ticks are part of the record form and are stored by its Opslaan."""
    letter = _letter_or_404(db, newsletter_id)
    return _participants_response(
        request, db, letter, shown=audience == nb.Audience.PARTICIPANTS.value
    )


@router.get("/admin/nieuwsbrieven/{newsletter_id:int}/activiteiten", response_class=HTMLResponse)
def activity_picker(
    newsletter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_VIEW)),
    purpose: str = "",
    q: str = "",
):
    """The picker. `purpose` says which of the letter's three groups a click puts
    the activity in (`past`, `featured`, `calendar`; #1562)."""
    letter = _letter_or_404(db, newsletter_id)
    if purpose not in nb.GROUPS:
        raise HTTPException(status_code=404, detail=_("Onbekende groep."))
    spans = nb.insertable_activities(db, query=q, past=purpose == "past")
    items = [
        {"id": s.activity.id, "name": s.activity.name, "date": nb.short_date(s.start)}
        for s in spans
    ]
    view = NewsletterPickerView(
        letter=letter, items=items, q=q, purpose=purpose, csrf_token=_csrf(request)
    )
    return templates.TemplateResponse(request, "_nb_kiezer.html", view.as_context())


@router.post(
    "/admin/nieuwsbrieven/{newsletter_id:int}/keuzes/{group}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def choice_add(
    newsletter_id: int,
    group: str,
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
    activity_id: int = Form(...),
):
    """Put an activity in one of the three groups (#1562)."""
    letter = _letter_or_404(db, newsletter_id)
    try:
        nb.set_choice(db, letter, group, activity_id, chosen=True)
    except nb.NewsletterError as exc:
        return _choices_response(request, db, letter, error=str(exc))
    return _choices_response(request, db, letter)


@router.post(
    "/admin/nieuwsbrieven/{newsletter_id:int}/keuzes/{group}/{activity_id:int}/weg",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def choice_remove(
    newsletter_id: int,
    group: str,
    activity_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
):
    letter = _letter_or_404(db, newsletter_id)
    try:
        nb.set_choice(db, letter, group, activity_id, chosen=False)
    except nb.NewsletterError as exc:
        return _choices_response(request, db, letter, error=str(exc))
    return _choices_response(request, db, letter)


@router.post(
    "/admin/nieuwsbrieven/{newsletter_id:int}/bijlage",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def insert_attachment(
    newsletter_id: int,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
    file: UploadFile = File(...),
):
    """ "Bijlage invoegen": the file is stored, the answer is the link that the
    editor puts at the cursor. A refusal answers 400 with the reason as text."""
    letter = _letter_or_404(db, newsletter_id)
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        return HTMLResponse(_("Dit bestand is te groot (hoogstens 10 MB)."), status_code=400)
    try:
        html = nb.add_attachment(
            db,
            letter,
            filename=file.filename or "",
            content_type=file.content_type or "",
            data=data,
            base_url=_base_url(db),
        )
    except nb.NewsletterError as exc:
        return HTMLResponse(str(exc), status_code=400)
    return HTMLResponse(html)


@router.get("/admin/nieuwsbrieven/{newsletter_id:int}/voorbeeld", response_class=HTMLResponse)
def newsletter_preview(
    newsletter_id: int,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_VIEW)),
):
    """The letter as it will arrive — markers expanded, styling applied.

    Needed since the activity block became a marker (Koen, 19 September 2026):
    the editor shows `[[activiteit:12|…]]`, so without this screen the author
    can only judge the result by mailing it to himself. Shown as a non-member
    would see it when non-members are in the audience, so the unsubscribe line
    is part of the picture.
    """
    letter = _letter_or_404(db, newsletter_id)
    base = _base_url(db)
    kind = nb.sample_kind_of(letter.audience)
    unsubscribe = (
        f"{base}/nieuwsbrief/uitschrijven/test" if kind != nb.DeliveryKind.MEMBER else None
    )
    return HTMLResponse(
        nb.render_mail(db, letter, kind=kind, unsubscribe_url=unsubscribe, base_url=base)
    )


@router.post(
    "/admin/nieuwsbrieven/{newsletter_id:int}/testmail",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def newsletter_test_mail(
    newsletter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
):
    letter = _letter_or_404(db, newsletter_id)
    try:
        rendered = nb.render_test(db, letter, base_url=_base_url(db))
    except nb.NewsletterError as exc:
        return templates.TemplateResponse(
            request,
            "_nb_bewaard.html",
            _notice_view(error=str(exc)).as_context(),
        )
    # The door's one command (§3.2.1): the newsletter rendered, mail sends.
    outcome = mail.send_campaign_mail(
        email,
        rendered.subject,
        rendered.body_html,
        email_type="newsletter",
        body_text=rendered.body_text,
    )
    notice = (
        _("Testmail verstuurd naar %(adres)s.") % {"adres": email}
        if outcome in ("sent", "logged")
        else _("De testmail kon niet vertrekken. Kijk in de e-maillog waarom.")
    )
    return templates.TemplateResponse(
        request,
        "_nb_bewaard.html",
        _notice_view(notice=notice).as_context(),
    )


@router.post(
    "/admin/nieuwsbrieven/{newsletter_id:int}/opnieuw",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def newsletter_resend_failed(
    newsletter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
):
    """Send the letter again to its failed addresses, and only to those (#1783)."""
    letter = _letter_or_404(db, newsletter_id)
    try:
        requeued = nb.resend_failed(db, letter)
    except nb.NewsletterError as exc:
        return templates.TemplateResponse(
            request,
            "admin_nieuwsbrief_archief.html",
            _archive_view(request, db, letter, error=str(exc)).as_context(),
        )
    return _go(request, f"/admin/nieuwsbrieven/{letter.id}?opnieuw={requeued}")


@router.post(
    "/admin/nieuwsbrieven/{newsletter_id:int}/kopieren",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def newsletter_copy(
    newsletter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
):
    letter = _letter_or_404(db, newsletter_id)
    copy = nb.copy_newsletter(db, letter, created_by=email)
    return _go(request, f"/admin/nieuwsbrieven/{copy.id}")


@router.post(
    "/admin/nieuwsbrieven/{newsletter_id:int}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def newsletter_delete(
    newsletter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
):
    letter = _letter_or_404(db, newsletter_id)
    try:
        nb.delete_draft(db, letter)
    except nb.NewsletterError as exc:
        return templates.TemplateResponse(
            request, "_nb_lijst.html", _list_view(request, db, error=str(exc)).as_context()
        )
    return _go(request, "/admin/nieuwsbrieven")


# ── Sending ──────────────────────────────────────────────────────────────────


def _audience_said(db: Session, audience, letter=None) -> tuple[list[AudienceLine], str, str, int]:
    """Who the letter goes to, in words (#1780): the lines of the first card,
    what the two lists share, the words on the send button, and the number of
    recipients. The numbers are the service's (`audience_summary`); only the
    words are made here. "Abonnees" is said only of subscribers."""
    from app.domains.mdm.api import module_enabled
    from app.kernel.modules import ModuleCode

    def ngettext(one: str, many: str, n: int) -> str:
        # As the templates' own `ngettext` (`app.i18n`): one form for 1, the other for the rest.
        return _(one) if n == 1 else _(many)

    if not audience:
        return [], "", "", 0
    if audience == nb.Audience.PARTICIPANTS:
        # CR-36: derived from the activities the letter names, so it needs the letter.
        lines, notes, count = _participant_said(db, letter)
        label = ngettext(
            "Verstuur naar %(num)s ontvanger", "Verstuur naar %(num)s ontvangers", count
        )
        return lines, " ".join(notes), label % {"num": count}, count
    said = nb.audience_summary(db, audience)
    # CR-19 (#1477): without the membership module there are no members, and
    # "both" is the subscribers.
    with_members = audience in (nb.Audience.MEMBERS, nb.Audience.BOTH) and module_enabled(
        ModuleCode.MEMBERSHIP
    )
    with_subscribers = audience in (nb.Audience.NON_MEMBERS, nb.Audience.BOTH)

    def addresses(n: int) -> str:
        return ngettext("%(num)s adres", "%(num)s adressen", n) % {"num": n}

    lines = []
    if with_members:
        households = ngettext("%(num)s gezin", "%(num)s gezinnen", said.households) % {
            "num": said.households
        }
        lines.append(
            AudienceLine(
                head=_("Leden van werkjaar %(jaar)s · %(adressen)s")
                % {"jaar": said.year, "adressen": addresses(said.member_addresses)},
                sentence=_(
                    "Elk e-mailadres van elke persoon in een gezin met een lidmaatschap "
                    "voor dit werkjaar: %(adressen)s in %(gezinnen)s. Oud-leden en gezinnen "
                    "zonder lidmaatschap dit jaar krijgen hem niet."
                )
                % {"adressen": addresses(said.member_addresses), "gezinnen": households},
            )
        )
    if with_subscribers:
        lines.append(
            AudienceLine(
                head=_("Abonnees · %(adressen)s")
                % {"adressen": addresses(said.subscriber_addresses)},
                sentence=_("Iedereen die zich inschreef op de nieuwsbrief en dat bevestigde."),
            )
        )
    overlap = ""
    if with_members and with_subscribers:
        overlap = (
            ngettext(
                "%(num)s adres staat op beide lijsten en krijgt hem één keer, als lid.",
                "%(num)s adressen staan op beide lijsten en krijgen hem één keer, als lid.",
                said.in_both,
            )
            % {"num": said.in_both}
            if said.in_both
            else _("Geen enkel adres staat op beide lijsten.")
        )
        send_label = ngettext(
            "Verstuur naar %(num)s ontvanger", "Verstuur naar %(num)s ontvangers", said.recipients
        )
    elif with_members:
        send_label = ngettext(
            "Verstuur naar %(num)s lid", "Verstuur naar %(num)s leden", said.recipients
        )
    else:
        send_label = ngettext(
            "Verstuur naar %(num)s abonnee", "Verstuur naar %(num)s abonnees", said.recipients
        )
    return lines, overlap, send_label % {"num": said.recipients}, said.recipients


def _send_view(
    request: Request, db: Session, letter, email: str, error: Optional[str] = None
) -> NewsletterSendView:
    from app.kernel.tenant_config import tenant_newsletter_daily_cap

    lines, overlap, send_label, count = _audience_said(db, letter.audience, letter)
    return NewsletterSendView(
        letter=letter,
        audience_lines=lines,
        audience_overlap=overlap,
        send_label=send_label,
        recipient_count=count,
        days=nb.expected_days(db, count) if count else 0,
        blocked=bool(nb.unfilled_placeholders(nb.markup_of(letter))),
        daily_cap=tenant_newsletter_daily_cap(db),
        reply_to_sender=email,
        csrf_token=_csrf(request),
        error=error,
        nav_items=admin_nav(NAV, request),
    )


@router.get("/admin/nieuwsbrieven/{newsletter_id:int}/versturen", response_class=HTMLResponse)
def send_screen(
    newsletter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.NEWSLETTER_VIEW)),
):
    letter = _letter_or_404(db, newsletter_id)
    if letter.status != nb.LetterStatus.DRAFT:
        return RedirectResponse(f"/admin/nieuwsbrieven/{letter.id}", status_code=303)
    error = None
    if not letter.audience:
        error = _("Kies eerst voor wie deze nieuwsbrief is.")
    error = error or nb.placeholder_refusal(nb.markup_of(letter))
    return templates.TemplateResponse(
        request,
        "admin_nieuwsbrief_versturen.html",
        _send_view(request, db, letter, email, error=error).as_context(),
    )


@router.post(
    "/admin/nieuwsbrieven/{newsletter_id:int}/versturen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def send_letter(
    newsletter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
    reply_to: str = Form(nb.ReplyToMode.ASSOCIATION),
):
    """After a human read it (CR-05 §3.9) — never automatically."""
    letter = _letter_or_404(db, newsletter_id)
    try:
        nb.start_sending(db, letter, sent_by=email, reply_to_mode=reply_to, base_url=_base_url(db))
    except nb.NewsletterError as exc:
        return templates.TemplateResponse(
            request,
            "_nb_versturen.html",
            _send_view(request, db, letter, email, error=str(exc)).as_context(),
        )
    return _go(request, f"/admin/nieuwsbrieven/{letter.id}")


# ── Raakje ───────────────────────────────────────────────────────────────────
# Every route here answers with the Raakje panel only; the editor is never
# replaced from the server. Off — and 404 — when Raakje in the back office is
# off for this tenant or this environment.


def _raakje_letter(db: Session, newsletter_id: int):
    if not _raakje_enabled(db):
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    return _letter_or_404(db, newsletter_id)


#: The header that tells the panel a question was not answered, so its field
#: keeps the question (the same one the reporting assistant sends).
NOT_ANSWERED = {"X-Raakje-Failed": "1"}


def _conversation(
    request: Request, db: Session, letter, turns: list[dict], *, failed: bool = False
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "_nb_gesprek.html",
        NewsletterConversationView(letter=letter, turns=turns).as_context(),
        headers=NOT_ANSWERED if failed else None,
    )


@router.get("/admin/nieuwsbrieven/{newsletter_id:int}/raakje/gesprek", response_class=HTMLResponse)
def raakje_conversation(
    newsletter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_VIEW)),
):
    """The conversation the draft keeps, for the Assistent's panel when it opens
    beside the letter (#1562)."""
    letter = _raakje_letter(db, newsletter_id)
    return _conversation(request, db, letter, _turn_views(db, letter, nb.messages_of(db, letter)))


@router.post(
    "/admin/nieuwsbrieven/{newsletter_id:int}/raakje/vraag",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def raakje_ask(
    newsletter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
    vraag: str = Form(""),
    body: str = Form(""),
    selection: str = Form(""),
    selection_range: str = Form(""),
    before_cursor: str = Form(""),
):
    """One turn with Raakje, asked from the Assistent's panel: the answer is the
    new turn alone, added under the conversation. The current text is saved
    first, so the proposal works on what the author sees."""
    from app.domains.chatbot.api import ChatTimeout, SeamBlocked, admin_chat_char_budget

    letter = _raakje_letter(db, newsletter_id)

    def failed(message: str) -> HTMLResponse:
        nb.record_turn(db, letter, author_text=vraag, error=message)
        turn = {"question": vraag, "answer": message, "proposal": None, "failed": True}
        return _conversation(request, db, letter, [turn], failed=True)

    try:
        nb.update_draft(
            db,
            letter,
            subject=letter.subject,
            body=body or None,
            audience=letter.audience,
            preview_text=letter.preview_text,
        )
    except nb.NewsletterError as exc:
        return failed(str(exc))
    admin_chat_char_budget.charge(request, max(len(vraag), 1), key=email)
    try:
        turn = nb.ask_raakje(
            db,
            letter,
            instruction=vraag,
            actor=email,
            base_url=_base_url(db),
            selection=selection,
            selection_range=selection_range,
            before_cursor=before_cursor,
        )
    except (nb.DraftingError, SeamBlocked, ChatTimeout) as exc:
        return failed(str(exc))
    except Exception:
        logger.exception("Raakje kon geen nieuwsbriefvoorstel maken (brief %s)", letter.id)
        return failed(
            _("Raakje kon geen antwoord geven — probeer het opnieuw. Je vraag staat er nog.")
        )
    answer = nb.record_turn(db, letter, author_text=vraag, turn=turn)
    turns = _turn_views(db, letter, [answer])
    turns[-1]["question"] = vraag
    return _conversation(request, db, letter, turns)


@router.post(
    "/admin/nieuwsbrieven/{newsletter_id:int}/raakje/{message_id:int}/toepassen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def raakje_apply(
    newsletter_id: int,
    message_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
):
    """Toepassen: the final values for the form. A marked sentence stays out
    unless it was ticked "klopt, behouden" (CR-05 §3.16). Nothing of the proposal
    is written here — the answer goes into the form's fields (#1562: the subject
    and the preview text too), and the page's own autosave stores them."""
    letter = _raakje_letter(db, newsletter_id)
    message = nb.get_drafting_message(db, letter, message_id)
    if message is None or not message.proposal:
        raise HTTPException(status_code=404, detail=_("Voorstel niet gevonden."))
    form = await request.form()
    keep = {int(str(v)) for v in form.getlist("keep") if str(v).isdigit()}
    shown = _proposal_fields(nb.display_proposal(db, letter, message))
    try:
        applied = nb.apply_proposal(
            db,
            letter,
            message,
            keep=keep,
            body=str(form.get("body") or ""),
            base_url=_base_url(db),
        )
    except nb.DraftingError as exc:
        return templates.TemplateResponse(
            request,
            "_nb_toegepast.html",
            NewsletterAppliedView(fields=shown, refusal=str(exc)).as_context(),
        )
    fields: list[dict] = []
    if applied.subject:
        fields.append(
            {
                "name": "subject",
                "label": _("Onderwerp"),
                "value": applied.subject,
                "base": applied.base_subject,
            }
        )
    if applied.preview:
        fields.append(
            {
                "name": "preview_text",
                "label": _("Voorbeeldtekst"),
                "value": applied.preview,
                "base": applied.base_preview,
            }
        )
    fields.append(
        {
            "name": "body",
            "label": _("Inhoud"),
            "value": applied.content,
            "placement": applied.placement,
            "range": applied.range,
        }
    )
    return templates.TemplateResponse(
        request, "_nb_toegepast.html", NewsletterAppliedView(fields=fields).as_context()
    )


@router.post(
    "/admin/nieuwsbrieven/{newsletter_id:int}/raakje/{message_id:int}/weigeren",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def raakje_dismiss(
    newsletter_id: int,
    message_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _email: str = Depends(require_right(Right.NEWSLETTER_MANAGE)),
):
    letter = _raakje_letter(db, newsletter_id)
    message = nb.get_drafting_message(db, letter, message_id)
    if message is not None:
        nb.dismiss_proposal(db, message)
    # Negeren is handled in the page (#1562); the server only remembers it.
    return Response(status_code=204)
