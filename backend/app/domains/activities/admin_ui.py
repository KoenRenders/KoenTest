"""Server-rendered admin-activiteitenbeheer (fase 4a-4, #402 — §21).

Volledige CRUD op activiteiten, datums, onderdelen en producten, plus de
inschrijvingenlijst en de .ods-export per onderdeel. Hergebruikt de bestaande
router-functies als servicelaag; sessie-auth + CSRF zoals de andere schermen.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Request,
)
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.datastructures import FormData

from app.database import get_db
from app.domains.activities.viewmodels import AdminActiviteitenView, CopyActivityView
from app.domains.auth.api import (
    SESSION_COOKIE,
    csrf_from_request,
    require_admin_ui,
    require_csrf,
)
from app.i18n import _
from app.ui import admin_nav, is_fragment_request, refusal_response, templates

router = APIRouter(include_in_schema=False)

# #1428: the badge tone of an activity's status. A draft is "attention": it is
# not on the site yet. Published is the normal case (the card shows no badge).
from app.domains.activities.api import ACTIVITY_STATUS, ActivityStatus  # noqa: E402
from app.kernel.codes import register_tones  # noqa: E402

register_tones(
    ACTIVITY_STATUS.name,
    {ActivityStatus.DRAFT: "orange", ActivityStatus.PUBLISHED: "gray"},
)

NAV = "/admin/activiteiten"


SCOPES = ("upcoming", "archived", "all")


def _lijst_ctx(db: Session, scope: str = "all", q: str = "") -> dict:
    """Lijst-context voor de records-lijst (C1, #586): scope-chips + vrij zoeken.

    Zoeken gebeurt op de reeds opgehaalde lijst i.p.v. in een tweede query: het
    zijn tientallen activiteiten, geen duizenden, en list_activities levert al de
    view-modellen mét telling en volzet-status waar de kaarten op steunen.
    """
    from app.domains.activities.api import list_activities

    if scope not in SCOPES:
        scope = "all"
    activiteiten = list_activities(db, scope=scope, include_drafts=True)
    term = q.strip().lower()
    if term:
        activiteiten = [
            a
            for a in activiteiten
            if term in (a.name or "").lower() or term in (a.location or "").lower()
        ]
    # #1391 (CR-11 W12): an activity without a single component has nothing to
    # register for, so its card says nothing about registrations rather than
    # "0 inschrijvingen". The criterion is "has a component", not "is open": a
    # closed component with 23 registrations still shows its 23.
    activiteiten = [
        a if a.sub_registrations else a.model_copy(update={"registration_count": None})
        for a in activiteiten
    ]
    return {"activities": activiteiten, "scope": scope, "q": q}


def _kpi(activities: list) -> dict:
    """De twee kengetallen boven het activiteitenbeheer (#528, design-system §7).

    Bewust GEEN betalings-KPI's hier: geld hoort op /admin/betalingen, en het
    dashboard linkt daar al naartoe. Wie activiteiten beheert, wil weten wat er
    openstaat en wat vol zit.

    Krijgt de reeds opgehaalde lijst mee i.p.v. zelf te bevragen — dezelfde
    gegevens twee keer ophalen voor twee cijfers is verspilling.
    """
    onderdelen = [c for a in activities for c in a.sub_registrations]
    return {
        # The state and not `status`: that is the label, a translatable word, so
        # comparing it with "Open" counted only while the word happened to be
        # "Open" (CR-12 phase 4 residue).
        "kpi_open": sum(1 for a in activities if a.registration_open),
        "kpi_vol": sum(1 for c in onderdelen if getattr(c, "is_full", False)),
        "kpi_onderdelen": len(onderdelen),
    }


def _aa_detail_ctx(
    request: Request,
    db: Session,
    activiteit: Any,
    error: str | None = None,
    *,
    organiser_query: str = "",
    organiser_candidates: list | None = None,
) -> dict:
    """De context van `_aa_detail.html`, op één plek.

    Dat fragment wordt vanuit twee routes gerenderd: als volledige pagina
    (admin_activiteit.html omhult het) en als htmx-fragment na elke bewerking.
    Beide bouwden hun eigen dict, en zo'n paar drift: #650 voegde één sleutel toe
    en de paginaroute rende meteen op StrictUndefined.
    """
    # De zonder-onderdeel-kaart (#650) verdween in feedbackronde 2 van golf 8:
    # de Inschrijvingen-tab toont die inschrijvingen als groep "Zonder onderdeel",
    # dus ze blijven bereikbaar — de reden achter #650 blijft gedekt.
    from app.domains.activities.api import (
        board_notes,
        booked_per_component,
        organisers_for,
        question_forms,
    )
    from app.domains.designstudio.api import on_the_poster
    from app.domains.mdm.api import household_ids

    organisers = organisers_for(db, activiteit.id)
    vraagformulieren, gekozen_formulier = question_forms(db, activiteit.id)
    return {
        "a": activiteit,
        "csrf_token": csrf_from_request(request),
        "error": error,
        # #1004: organisatoren horen bij het record zelf, dus ze reizen mee met
        # elke rendering van dit fragment.
        "organisers": organisers,
        "contact_count": sum(1 for o in organisers if o.is_contact),
        # #1433: who the poster names, asked of Design Studio — the rule is theirs.
        "poster_ids": {o.id for o in on_the_poster(organisers)},
        # #1559: the occupancy stands on the component itself in read mode
        # (the same count as the full-check, #451).
        "component_booked": booked_per_component(db, [activiteit.id]),
        # #1559: an organiser's name is a jump link to the household.
        "organiser_households": household_ids(db, [o.person_id for o in organisers]),
        # #1028: de interne nota komt NIET uit `activiteit` — dat is
        # `ActivityResponse`, en dat schema is óók het publieke JSON-antwoord. Een
        # veld erbij zou de nota meteen publiek maken. Ze reist apart, en alleen
        # naar dit scherm.
        "board_notes": board_notes(db, activiteit.id),
        # CR-14 phase 2 (§B4.5): the forms a component can ask ("Extra vragen"),
        # and which one each component asks. Not on `a`: that is the public JSON.
        "question_forms": vraagformulieren,
        "component_form": gekozen_formulier,
        # #1428: the audience choice; `selected` is decided here, so the template
        # compares no code. Not on `a`: that is the public JSON.
        "audience_options": _audience_options(db, activiteit.id),
    }


def _audience_options(db: Session, activity_id: int) -> list[tuple[str, str, bool]]:
    """(code, label, selected) for the target audience select (#1428)."""
    from app.domains.activities.api import TARGET_AUDIENCE, publication
    from app.kernel.codes import code_labels

    chosen = publication(db, activity_id).audience
    return [(code, label, code == chosen) for code, label in code_labels(TARGET_AUDIENCE.name)]


def _detail_response(
    request: Request,
    db: Session,
    activity_id: int,
    error: str | None = None,
    *,
    toast: bool = False,
    organiser_query: str = "",
    organiser_candidates: list | None = None,
    read_mode: bool = False,
) -> HTMLResponse:
    from app.domains.activities.api import get_activity_detail

    # #651: was `list_activities(scope="all")` + in Python filteren op id. Het
    # detail van één activiteit kostte zo meer dan de lijst van alle 167 (483 ms
    # tegen 89 ms op HDEV), en élke mutatie op dit scherm betaalde dat opnieuw.
    activiteit = get_activity_detail(db, activity_id)
    if activiteit is None:
        return HTMLResponse('<div id="aa-detail" hx-swap-oob="true"></div>')
    ctx = _aa_detail_ctx(
        request,
        db,
        activiteit,
        error,
        organiser_query=organiser_query,
        organiser_candidates=organiser_candidates,
    )
    ctx["toast_opgeslagen"] = toast
    # HDEV-melding 15 sep: kop en rail staan buiten #aa-detail en bleven na een
    # opslag op de oude stand. Het fragment stuurt ze nu out-of-band mee; de
    # e-mail (voor de tab-rollen) komt uit de sessie die require_admin_ui al
    # gevalideerd heeft.
    from app.domains.activities.api import registration_count_for
    from app.domains.auth.api import read_session_value

    email = read_session_value(request.cookies.get(SESSION_COOKIE))
    if email:
        reg_count = registration_count_for(db, activity_id)
        tabs = _record_tabs(activiteit, reg_count, db, email, "overzicht", request)
        ctx.update(tabs)
        ctx.update(_record_summary(db, activiteit, tabs, reg_count, ctx["component_booked"]))
        # Alleen op het FRAGMENT-antwoord: de volledige pagina rendert de kop
        # zelf al — een oob-blok zou hem daar dubbel zetten.
        ctx["oob_kop"] = True
    headers = {}
    if read_mode and "way_back" in ctx:
        # #1558: the page was in its edit state (`?bewerken=1`); after the save
        # it reads again, and the address says so — a reload must not reopen
        # the editor.
        ctx["head_editing"] = False
        keep = ctx["way_back"]["keep"]
        headers["HX-Push-Url"] = f"{NAV}/{activity_id}" + (f"?{keep}" if keep else "")
    return templates.TemplateResponse(request, "_aa_detail.html", ctx, headers=headers)


@router.get("/admin/activiteiten", response_class=HTMLResponse)
def admin_activiteiten(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    scope: str = "upcoming",
    q: str = "",
) -> Response:
    lijst = _lijst_ctx(db, scope, q)
    # De kengetallen tellen wat er openstaat, niet wat er toevallig gefilterd is:
    # een zoekterm mag "Open inschrijving" niet doen dalen. Zonder filter is de
    # getoonde lijst al de juiste bron en blijft het bij één query.
    kpi_bron = (
        lijst["activities"]
        if (scope == "upcoming" and not q.strip())
        else _lijst_ctx(db, "upcoming")["activities"]
    )
    # De filterbalk vraagt enkel de kaarten op; zou ze de pagina vervangen, dan
    # sneuvelt het zoekveld (en de focus) bij elke aanslag.
    fragment = is_fragment_request(request)
    from app.domains.activities.api import publication_of
    from app.ui import list_return

    view = AdminActiviteitenView(
        **lijst,
        **_kpi(kpi_bron),
        # #1557: a card hands the list as it stands to the record it opens, so
        # the record's way back returns to the same search and scope.
        list_url=list_return(NAV, scope=scope if scope != "upcoming" else "", q=q.strip()),
        # #1428: "Concept" and the audience on the cards.
        publication=publication_of(db, [a.id for a in lijst["activities"]]),
        csrf_token=csrf_from_request(request),
        nav_items=[] if fragment else admin_nav(NAV),
    )
    sjabloon = "_aa_kaarten.html" if fragment else "admin_activiteiten.html"
    return templates.TemplateResponse(request, sjabloon, view.as_context())


@router.get("/admin/activiteiten/nieuw", response_class=HTMLResponse)
def activiteit_nieuw(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
) -> Response:
    """Paginabreed aanmaakscherm i.p.v. een modal (#623).

    Bewust géén lege activiteit vooraf aanmaken: dan staat er een naamloze activiteit
    in de databank zodra iemand per ongeluk klikt, en die kan publiek opduiken zodra
    ze een datum krijgt. Het scherm draagt dezelfde kaart als de editor waarin je
    daarna werkt, dus er is geen tweede lay-out om te onderhouden.
    """
    return templates.TemplateResponse(
        request,
        "admin_activiteit_nieuw.html",
        {
            "nav_items": admin_nav(NAV),
            "csrf_token": csrf_from_request(request),
        },
    )


def _copy_view(
    request: Request, db: Session, activity_id: int, error: Optional[str] = None
) -> CopyActivityView:
    from app.domains.activities.api import (
        copy_suggestions,
        first_date_of,
        get_activity,
    )

    activity = get_activity(db, activity_id)
    if activity is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    first = first_date_of(activity)
    suggestions = copy_suggestions(first) if first else None
    return CopyActivityView(
        activity=activity,
        first_date=first,
        same_weekday=suggestions.same_weekday if suggestions else None,
        same_date=suggestions.same_date if suggestions else None,
        error=error,
        csrf_token=csrf_from_request(request),
        nav_items=admin_nav(NAV),
    )


@router.post(
    "/admin/activiteiten/{activity_id}/status",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def activity_status_submit(
    activity_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    status: str = Form(""),
) -> Response:
    """Publish a draft or take it back to draft (#1428); the rule is the service's."""
    from app.domains.activities import service
    from app.domains.activities.api import set_activity_status

    try:
        changed = set_activity_status(db, activity_id, status, actor=email)
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=422, detail=str(fout))
    if changed is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    # The header sits on every tab of the activity; the page that pressed the
    # button reloads, so the badge and the button show the new status.
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.post(
    "/admin/activiteiten/{activity_id}/annulering",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def activity_cancellation_submit(
    activity_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    cancelled: str = Form(""),
) -> Response:
    """Call the activity off, or take that back (#1558): a record action in the
    head's menu, where it was a checkbox in the form."""
    from app.domains.activities import service

    changed = service.update_activity(
        db, activity_id, {"is_cancelled": cancelled == "1"}, actor=email
    )
    if changed is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    # The badge sits in the head of every tab; the page that asked reloads.
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.get("/admin/activiteiten/{activity_id}/kopieren", response_class=HTMLResponse)
def copy_activity_step(
    activity_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """The step before a copy (#1397): where the dates move to."""
    return templates.TemplateResponse(
        request, "admin_activiteit_kopieren.html", _copy_view(request, db, activity_id).as_context()
    )


@router.post(
    "/admin/activiteiten/{activity_id}/kopieren",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def copy_activity_submit(
    activity_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    start_date: Optional[date] = Form(None),
    with_components: bool = Form(False),
    status: str = Form(""),
) -> Response:
    """Make the copy and open it (#1397). The copying, and its rules, are in the
    service; the form's `start_date` is the new start of the first date row."""
    from app.domains.activities import service
    from app.domains.activities.api import copy_activity

    try:
        copy = copy_activity(
            db,
            activity_id,
            first_date=start_date,
            actor=email,
            with_components=with_components,
            status=status or None,
        )
    except service.ActiviteitFout as fout:
        view = _copy_view(request, db, activity_id, error=str(fout))
        return templates.TemplateResponse(
            request, "admin_activiteit_kopieren.html", view.as_context()
        )
    if copy is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    return Response(status_code=204, headers={"HX-Redirect": f"/admin/activiteiten/{copy.id}"})


@router.get("/admin/activiteiten/{activity_id}", response_class=HTMLResponse)
def admin_activiteit_detail(
    activity_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """Een kaart opent de paginabrede editor (C1, #586); de bewerkingen daarin
    blijven htmx-fragmenten die in #aa-detail landen."""
    if is_fragment_request(request):
        return _detail_response(request, db, activity_id)
    from app.domains.activities.api import get_activity_detail

    activiteit = get_activity_detail(db, activity_id)
    if activiteit is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    from app.domains.activities.api import registration_count_for

    reg_count = registration_count_for(db, activity_id)
    detail = _aa_detail_ctx(request, db, activiteit)
    tabs = _record_tabs(activiteit, reg_count, db, email, "overzicht", request)
    return templates.TemplateResponse(
        request,
        "admin_activiteit.html",
        {
            "nav_items": admin_nav(NAV),
            **detail,
            **tabs,
            **_record_summary(db, activiteit, tabs, reg_count, detail["component_booked"]),
        },
    )


@router.post(
    "/admin/activiteiten", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
def activiteit_aanmaken(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    name: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    start_time: str = Form(""),
    end_time: str = Form(""),
    location: str = Form(""),
    poster_url: str = Form(""),
    members_only: str = Form(""),
) -> Response:
    from app.domains.activities import service
    from app.schemas.activity import ActivityDateCreate

    if not name.strip() or not start_date:
        raise HTTPException(status_code=400, detail=_("Naam en eerste datum zijn verplicht."))
    # #792: the complete first row, the same four fields as `datum_toevoegen`. They
    # were thrown away here while both the schema and the model already accepted them —
    # this was not a missing feature but a narrower form.
    first_row = ActivityDateCreate(
        start_date=start_date,
        end_date=end_date or None,
        start_time=start_time or None,
        end_time=end_time or None,
    )
    try:
        nieuw = service.create_activity(
            db,
            name=name.strip(),
            location=location.strip() or None,
            poster_url=poster_url.strip() or None,
            members_only=bool(members_only),
            dates=[first_row],
            actor=email,
        )
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=422, detail=str(fout))
    # Aanmaken opent meteen de editor: een verse activiteit heeft nog datums en
    # onderdelen nodig, en die staan daar (C1, #586).
    return Response(status_code=204, headers={"HX-Redirect": f"/admin/activiteiten/{nieuw.id}"})


@router.post(
    "/admin/activiteiten/{activity_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def activiteit_bijwerken(
    activity_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """The one "Opslaan" of the fiche (#1559): its sections, its dates, its
    components with their products, its organisers and its attachments, written
    in one transaction by `activities.fiche.save_fiche`.

    Until #1559 every row had a route of its own — nineteen of them, each with
    its own commit. The form is read by name (`fiche_form`), because its rows are
    not a fixed list of parameters.

    A refusal writes nothing and leaves the form as it was typed: the answer is
    the reason alone, placed in the fiche's message line. A re-rendered form
    would throw away every row added or changed in the page.
    """
    from app.domains.activities import service
    from app.domains.activities.fiche import (
        ContactConfirmation,
        FicheRefusal,
        FieldError,
        save_fiche,
    )
    from app.domains.activities.fiche_form import fiche_from_form

    form = await request.form()
    poster = form.get("file")
    try:
        fiche, component_files = fiche_from_form(form)
        saved = await save_fiche(
            db,
            activity_id,
            fiche,
            actor=email,
            poster=None if isinstance(poster, str) else poster,
            component_files=component_files,
            background_tasks=background_tasks,
        )
    except ContactConfirmation as question:
        return _refusal(request, question=str(question))
    except FicheRefusal as refusal:
        return _refusal(request, refusal.errors)
    except service.ActiviteitFout as fout:
        return _refusal(request, [FieldError("", str(fout))])
    if saved is None:
        raise HTTPException(status_code=404, detail=_("Activity not found"))
    # #742: this closing "Opslaan" confirms. #1558: and it ends the edit state.
    return _detail_response(request, db, activity_id, toast=True, read_mode=True)


def _refusal(
    request: Request, errors: list | None = None, *, question: str | None = None
) -> Response:
    """Why the save was refused, for the fiche's message line — and nothing else,
    so the form keeps what was typed. An HTML 422 is swapped (#1515); the two
    headers send it to that line instead of to the form's own target.

    `errors` name their field or row (#1561): the banner lists them and the
    form's script marks each one. `question`: the refusal is a question; the
    answer carries the button that confirms and saves again.
    """
    return templates.TemplateResponse(
        request,
        "_aa_refusal.html",
        {"errors": errors or [], "question": question, "confirm": question is not None},
        status_code=422,
        # `transition:false`: a banner that arrives is no navigation; with the
        # shell's view transition the whole record cross-faded (Refs #1589).
        headers={"HX-Retarget": "#aa-fiche-message", "HX-Reswap": "innerHTML transition:false"},
    )


@router.post(
    "/admin/activiteiten/{activity_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def activiteit_verwijderen(
    activity_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    from app.domains.activities import service

    try:
        deleted = service.delete_activity(db, activity_id, actor=email)
    except service.ActiviteitFout as refusal:
        # The screen says so before the click (#1561); this is the request that
        # came anyway.
        raise HTTPException(status_code=422, detail=str(refusal)) from refusal
    if not deleted:
        raise HTTPException(status_code=404, detail=_("Activity not found"))
    # Verwijderen gebeurt vanuit de editor; die pagina bestaat daarna niet meer.
    return Response(status_code=204, headers={"HX-Redirect": "/admin/activiteiten"})


# ── Datums ─────────────────────────────────────────────────────────────────────


# ── Onderdelen ─────────────────────────────────────────────────────────────────


# ── Producten ──────────────────────────────────────────────────────────────────


# ── Gedeelde inschrijving-detail (betalingen + activiteiten-admin, #455/#451) ──


def _detail_ctx(
    request: Request,
    db: Session,
    registration_id: int,
    *,
    edit_open: bool = False,
    quantities: dict | None = None,
) -> dict | None:
    """Gedeelde context voor de inschrijving-detail/editor: de verrijkte
    inschrijving + de beschikbare producten van haar onderdeel (voor de
    'regel toevoegen'-keuze). Geeft None als de inschrijving niet bestaat."""
    from app.domains.activities.api import (
        enrich_registration,
        get_activity,
        get_registration,  # noqa: F401
    )

    # include_deleted: een betaling is een financieel feit, dus de bewaarde naam
    # blijft zichtbaar ook als de inschrijving geschrapt is (#190).
    reg = get_registration(db, registration_id, include_deleted=True)
    if reg is None:
        return None
    activity = get_activity(db, reg.activity_id, include_deleted=True)
    # #1305: made visible by typing, not new — the registration's foreign key
    # points at a row that is soft-deleted at most, so with `include_deleted` it is
    # always found. Said here instead of crashing on `None` further down.
    assert activity is not None, f"registration {reg.id} without its activity"
    component = None
    if activity is not None and reg.component_id:
        component = next((c for c in activity.sub_registrations if c.id == reg.component_id), None)
    # Bedragen per regel + totaal (#613-4): zonder bedragen zie je in het paneel
    # niet wát je aan het wijzigen bent. Ze komen uit compute_registration_total —
    # de enige bron voor "wat kost deze inschrijving" (totals.py) — zodat het paneel
    # nooit een ander bedrag toont dan de betaalrecords. We lopen items en regels
    # parallel af en slaan items zonder product over, precies zoals die functie doet.
    # #670: met `quantities` rekent hij door op de aantallen uit het formulier,
    # zónder iets te bewaren — dat is de live-herberekening. Zonder is het de
    # bewaarde stand, zoals voorheen. Beide via totals.py, want een tweede
    # berekening in deze module is precies wat §19.3 uitsluit.
    from app.domains.activities.api import (
        compute_registration_total,
        quote_registration_products,
    )

    # #1494: the card shows every product of the component as a counter, keyed by
    # PRODUCT like the form; `quantities` are the form's while typing, else the
    # stored order. 0 is "not chosen".
    stored: dict[int, int] = {}
    for item in reg.items or []:
        stored[item.product_id] = stored.get(item.product_id, 0) + item.quantity
    counts = {**stored, **(quantities or {})}
    if quantities is not None and component is not None:
        totaal, regels = quote_registration_products(reg, component, counts)
    else:
        totaal, regels = compute_registration_total(reg)
    product_rows = []
    if component is not None:
        _t, prices = quote_registration_products(
            reg, component, {p.id: 1 for p in component.products}
        )
        for product, price in zip(component.products, prices):
            product_rows.append(
                {
                    "id": product.id,
                    "name": product.name,
                    "unit_price": price["unit_price"],
                    "quantity": counts.get(product.id, 0),
                }
            )
    bedragen, idx = {}, 0
    for item in reg.items or []:
        if getattr(item, "product", None) is None:
            continue
        if idx < len(regels):
            bedragen[item.id] = regels[idx]
        idx += 1

    verrijkt = enrich_registration(reg, activity)
    from app.domains.activities.api import (
        answer_link_action,
        question_block_context,
        question_form,
        registration_answers,
    )
    from app.domains.forms.api import submission_form_values

    antwoorden, gevraagd_op = registration_answers(db, reg)
    link_actie = answer_link_action(db, reg)
    # CR-14 §B4.7: the questions to correct the answers in, filled with the answers.
    vragenformulier = question_form(db, component) if reg.form_submission_id else None
    for regel in verrijkt["items"]:
        bedrag = bedragen.get(regel["id"])
        regel["unit_price"] = bedrag["unit_price"] if bedrag else None
        # #732: ook het AANTAL moet meekomen, niet alleen de bedragen. Het antwoord
        # van /totaal vervangt het hele paneel — inclusief het veld waarin je net
        # typte — en `enrich_registration` zet daar de BEWAARDE stand in. Wie 2 naar
        # 1 bracht, kreeg dus een 1-prijs naast een 2 in het invoerveld, en bij
        # Opslaan stuurde het formulier die 2 terug: `inschrijving_opslaan` zag geen
        # verschil met de bewaarde waarde en bewaarde niets. De wijziging verdween
        # zonder melding.
        #
        # Zonder `quantities` blijft het de bewaarde stand — dat is het gewone
        # openen van het paneel — en dit endpoint bewaart nog steeds niets (#613-2).

    return {
        "reg": verrijkt,
        "product_rows": product_rows,
        "totaal": totaal,
        # #716: de ploegnaam is bewerkbaar wanneer het onderdeel er een vraagt, óf
        # wanneer de inschrijving er al een heeft. Die tweede reden is nodig: gaat
        # `team_name_required` later af, dan blijft de bewaarde ploegnaam in de kop
        # staan en moet ze corrigeerbaar blijven. Zonder een van beide is het veld
        # enkel ruis.
        "toon_ploegnaam": bool(
            (component is not None and component.team_name_required) or verrijkt.get("team_name")
        ),
        # #733: getoond en verplicht zijn twee dingen. Het veld verschijnt óók bij
        # een bewaarde ploegnaam op een onderdeel dat er geen vraagt — daar mag ze
        # wél leeggemaakt worden, dus daar hoort geen sterretje.
        "ploegnaam_verplicht": bool(component is not None and component.team_name_required),
        "editable": reg.deleted_at is None,
        "edit_open": edit_open,
        "csrf_token": csrf_from_request(request),
        # Golf 4 (#913): de paginavariant heeft de kop en de canonieke terugweg
        # nodig. Ze komen hiervandaan — activiteit en onderdeel zijn hierboven al
        # geladen — zodat de pagina ze niet zelf opnieuw afleidt.
        "activiteit_id": reg.activity_id,
        "activiteit_titel": activity.name if activity is not None else "",
        "component_naam": component.name if component is not None else None,
        # CR-14 phase 2 (§B4.4): the answers to the component's questions, or the
        # moment they were asked while the answer link is still open.
        "antwoorden": antwoorden,
        "antwoorden_gevraagd_op": gevraagd_op,
        # CR-14 phase 3 (§B4.8): "opnieuw" / "sturen" / None — the answer link.
        "link_actie": link_actie,
        # CR-14 phase 3 (§B4.7): the answers, editable — the form builder's field
        # partial reads `values`; `vraag_fout` marks the question a refusal names.
        # #1380: the form's own question block.
        **question_block_context(vragenformulier),
        "values": submission_form_values(db, reg.form_submission_id) if vragenformulier else {},
        "vraag_fout": None,
    }


def _render_detail(
    request: Request,
    db: Session,
    registration_id: int,
    *,
    edit_open: bool = False,
    ververs: bool = False,
    error: str | None = None,
    toast: str | None = None,
    quantities: dict | None = None,
    answer_values: dict | None = None,
    vraag_fout: int | None = None,
) -> HTMLResponse:
    """Rendert het detailfragment.

    ``edit_open`` houdt het paneel na een bewerking open (#613-3): het fragment
    vervangt zichzelf via outerHTML, dus zonder dit viel het terug in lees-modus en
    voelde het alsof er niets gebeurd was. Dat geldt voor de tussenacties; de
    afsluitende "Opslaan" sluit het paneel juist wél (#717).

    ``toast`` stuurt een bevestiging out-of-band mee. Deze functie is de enige plek
    die dit template rendert, dus die ene vlag volstaat om de toast weg te houden
    bij de detailroute, /totaal en /regels — die renderen hetzelfde fragment.

    ``ververs`` zet een ``HX-Trigger`` (#613-4/#617-3). De kaart erboven op
    /admin/betalingen staat buiten dit fragment en bleef op het oude bedrag staan —
    of toonde een nieuwe terugbetaling pas na F5 — terwijl de server al
    gereconcilieerd had. De betalingenlijst luistert op dat event.
    """
    ctx = _detail_ctx(request, db, registration_id, edit_open=edit_open, quantities=quantities)
    if ctx is None:
        return HTMLResponse("")
    ctx["error"] = error
    ctx["toast_bericht"] = toast
    # CR-14 §B4.7: a refused correction shows what was typed, the question marked.
    if answer_values is not None:
        ctx["values"] = answer_values
        ctx["vraag_fout"] = vraag_fout
    # Golf 8-feedback: op de eigen pagina draagt het cluster ook Verwijderen
    # (achter de bewerkklik, uiterst links). Of we óp die pagina zijn, zegt
    # HX-Current-URL — de POSTs van het fragment reizen daarmee.
    huidig = request.headers.get("HX-Current-URL", "")
    ctx["op_pagina"] = (
        f"/admin/inschrijvingen/{registration_id}" in huidig and "/fragment" not in huidig
    )
    resp = templates.TemplateResponse(request, "_inschrijving_detail.html", ctx)
    if ververs:
        resp.headers["HX-Trigger"] = "betalingen-ververst"
    return resp


@router.get("/admin/inschrijvingen/{registration_id}/fragment", response_class=HTMLResponse)
def inschrijving_detail(
    registration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """Detail/editor van één inschrijving (contact + producten + opmerking) als
    htmx-fragment. Herbruikbaar vanuit betalingen ('Toon inschrijvingsdetails')
    en de activiteiten-admin. Verrijking neemt soft-deleted mee (financieel feit);
    een soft-deleted inschrijving is niet bewerkbaar.

    Tot golf 4 (#913) woonde dit fragment op de id-URL zelf; die is nu van de
    volwaardige pagina hieronder (huispatroon: pagina op de id-URL, fragmenten op
    subpaden — zoals /admin/activiteiten/{id} naast zijn fragmentroutes)."""
    return _render_detail(request, db, registration_id)


@router.get("/admin/inschrijvingen/{registration_id}", response_class=HTMLResponse)
def inschrijving_pagina(
    registration_id: int,
    request: Request,
    terug: str = "",
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """De inschrijving als volwaardige pagina (golf 4, #913 — B2).

    De recordnaam in een lijst opent deze pagina; het inline openvouwen blijft
    bestaan als secundaire variant (het fragment op /fragment). Zelfde bron:
    beide renderen `_inschrijving_detail.html` uit `_detail_ctx`.

    `terug` is de A7-retourcontext: de lijst die hierheen linkte geeft haar eigen
    adres mee, zodat de terugknop filters en sortering herstelt. Gevalideerd via
    `veilige_terug`; alles wat geen intern pad is valt terug op de canonieke plek
    van dit record — zijn activiteit."""
    from app.domains.activities.viewmodels import AdminInschrijvingView

    # De rij-knop in de lijsten heet sinds de feedback van 15 sep "Details" en
    # opent LEESmodus: de consistente Bewerken-opener (met Verwijderen in het
    # cluster) staat op de pagina zelf. De vroegere `bewerk=1` verdween daarmee.
    ctx = _detail_ctx(request, db, registration_id, edit_open=False)
    if ctx is None:
        raise HTTPException(status_code=404, detail=_("Inschrijving niet gevonden"))
    from app.domains.activities.api import inschrijving_kop_ctx

    # Kop (terugweg + label + tabs) uit de gedeelde bouwer — de ingebedde
    # Betalingen-tab rendert exact dezelfde kop.
    kop = inschrijving_kop_ctx(db, registration_id, email, "overzicht", terug)
    if kop is None:  # kan niet meer na de 404 hierboven; mypy weet dat niet
        raise HTTPException(status_code=404, detail=_("Inschrijving niet gevonden"))
    ctx.update(kop)
    vm = AdminInschrijvingView(
        **ctx, error=None, toast_bericht=None, op_pagina=True, nav_items=admin_nav(NAV)
    )
    return templates.TemplateResponse(request, "admin_inschrijving.html", vm.as_context())


def _reg_or_404(db: Session, registration_id: int) -> Any:
    from app.domains.activities.api import get_registration

    reg = get_registration(db, registration_id)
    if reg is None:
        raise HTTPException(status_code=404, detail=_("Inschrijving niet gevonden"))
    return reg


@router.post(
    "/admin/inschrijvingen/{registration_id}/totaal",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def inschrijving_totaal(
    registration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """Herberekent regelbedragen en totaal bij een gewijzigd aantal (#670).

    **Bewaart niets.** Er is bewust één "Opslaan" voor aantallen én opmerking
    (#613-2), en de autosave-op-change is daar destijds uitgehaald. Een
    live-endpoint dat stilletjes opslaat brengt die via de achterdeur terug, dus
    dit leest het formulier en rekent — meer niet. Daar staat een test op.

    Eigen endpoint en niet het publieke `/totaal`: dat laatste is open, dit vraagt
    `require_admin_ui` + CSRF. Het patroon is hetzelfde, de rekenkant is dezelfde
    (`totals.py`), alleen de deur verschilt.
    """
    formulier = await request.form()
    return _render_detail(
        request, db, registration_id, edit_open=True, quantities=_product_quantities(formulier)
    )


def _product_quantities(form: FormData) -> dict[int, int]:
    """The counters of the card, per product (`product_<id>`, as on the form;
    #1494). An empty or unreadable field is left out: that product keeps its
    stored quantity."""
    quantities: dict[int, int] = {}
    for key, value in form.items():
        # form.items() may yield an UploadFile; only text fields are quantities.
        if not key.startswith("product_") or not isinstance(value, str):
            continue
        try:
            quantities[int(key[len("product_") :])] = max(0, int(value))
        except ValueError:
            continue
    return quantities


@router.post(
    "/admin/inschrijvingen/{registration_id}/opmerking",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def inschrijving_opmerking(
    registration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    remarks: str = Form(""),
) -> Response:
    from app.domains.activities import service
    from app.schemas.activity import RegistrationContactUpdate

    reg = _reg_or_404(db, registration_id)
    velden = RegistrationContactUpdate(remarks=remarks).model_dump(exclude_unset=True)
    try:
        bijgewerkt = service.update_registration_contact(
            db, reg.activity_id, registration_id, velden, actor=email
        )
    except service.ActiviteitFout as fout:
        # #733 toetst op de uitkomst, dus ook een opmerking-opslag op een inschrijving
        # waar een verplicht veld al leeg stond loopt hier langs. In de banner, niet
        # als 500.
        return _render_detail(request, db, registration_id, edit_open=True, error=str(fout))
    if bijgewerkt is None:
        raise HTTPException(status_code=404, detail=_("Registration not found"))
    return _render_detail(request, db, registration_id, edit_open=True, ververs=True)


@router.post(
    "/admin/inschrijvingen/{registration_id}/antwoordlink",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def answer_link_send(
    registration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """ "Link sturen" / "link opnieuw sturen" (CR-14 §B4.8): the answer link by mail
    to the registration's contact address, and a history row."""
    from app.domains.activities import service

    try:
        service.send_answer_link(db, registration_id, actor=email)
    except LookupError:
        raise HTTPException(status_code=404, detail=_("Registration not found"))
    except service.ActiviteitFout as fout:
        return _render_detail(request, db, registration_id, error=str(fout))
    return _render_detail(
        request, db, registration_id, toast=_("De link naar de vragen is verstuurd.")
    )


@router.post(
    "/admin/inschrijvingen/{registration_id}/antwoorden",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def answers_save(
    registration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """Correct a registration's answers (CR-14 §B4.7, R7): the same fields and rules
    as when they were given, a history row with old and new."""
    from app.domains.activities import service
    from app.domains.activities.api import form_values, question_form
    from app.domains.forms.api import answers_from_form

    reg = _reg_or_404(db, registration_id)
    form = await request.form()
    questions = question_form(db, reg.component)
    if questions is None:
        raise HTTPException(status_code=404, detail=_("Registration not found"))
    try:
        service.edit_answers(db, registration_id, answers_from_form(questions, form), actor=email)
    except service.ActiviteitFout as fout:
        return _render_detail(request, db, registration_id, error=str(fout))
    except HTTPException as exc:
        return _render_detail(
            request,
            db,
            registration_id,
            edit_open=True,
            error=str(exc.detail),
            answer_values=form_values(form),
            vraag_fout=getattr(exc, "veld_id", None),
        )
    return _render_detail(request, db, registration_id, toast=_("De antwoorden zijn opgeslagen."))


@router.post(
    "/admin/inschrijvingen/{registration_id}/opslaan",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def inschrijving_opslaan(
    registration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """Aantallen én opmerking in één "Opslaan" (#613-2).

    Voorheen sloeg elk onderdeel apart op — het aantal bij `change`, de opmerking met
    een eigen knop — waardoor je niet kon zien wat er samen bewaard werd. "Toevoegen"
    en "Verwijder" blijven wél aparte acties: die wijzigen wélke regels er zijn, niet
    hun waarden.

    We gaan per gewijzigd aantal door ``update_order_line``, zodat validatie en
    audit-snapshot dezelfde blijven als bij de losse route. Dat reconcilieert per
    aanroep, maar ``reconcile_registration_charges`` is integraal — het verwijdert de
    onbetaalde posten en herrekent naar één open post — dus tussenstanden laten geen
    verdwaalde refund achter.
    """
    from app.domains.activities import service
    from app.domains.payment.api import PayableType, open_refund_amount
    from app.schemas.activity import RegistrationContactUpdate

    reg = _reg_or_404(db, registration_id)
    form = await request.form()

    # #1494: every product is a counter; the differences go through ONE call, one
    # transaction and one reconciliation. Removing a paid line refuses nothing,
    # as "Verwijderen" did: the payment side prepares the refund, and the toast
    # below says so.
    terug_voor = open_refund_amount(db, PayableType.REGISTRATION, registration_id)
    try:
        gewijzigd = service.set_order_quantities(
            db, reg.activity_id, registration_id, _product_quantities(form), actor=email
        )
    except service.ActiviteitFout as fout:
        return _render_detail(request, db, registration_id, edit_open=True, error=str(fout))
    if gewijzigd is None:
        raise HTTPException(status_code=404, detail=_("Registration not found"))
    terug_na = open_refund_amount(db, PayableType.REGISTRATION, registration_id)

    # Contactgegevens meenemen in dezelfde "Opslaan" (#624). Enkel wat het formulier
    # meestuurt wordt gewijzigd; de route laat de rest ongemoeid.
    contact = {"remarks": str(form.get("remarks") or "")}
    for veld in ("contact_name", "contact_email", "phone", "team_name"):
        if veld in form:
            contact[veld] = str(form.get(veld) or "")
    try:
        gegevens = RegistrationContactUpdate(**contact)
    except ValidationError:
        # Het schema wordt hier zelf gebouwd (geen request-body), dus Pydantic werpt
        # i.p.v. FastAPI een 422 te laten maken. Het paneel opnieuw renderen mét een
        # foutbanner: htmx swapt een 200, dus de gebruiker ziet de fout écht staan.
        return _render_detail(
            request, db, registration_id, edit_open=True, error=_("Vul een geldig e-mailadres in.")
        )
    try:
        bijgewerkt = service.update_registration_contact(
            db,
            reg.activity_id,
            registration_id,
            gegevens.model_dump(exclude_unset=True),
            actor=email,
        )
    except service.ActiviteitFout as fout:
        # #733: een verplicht veld leeggemaakt. In de bestaande foutbanner en met een
        # 200, want htmx swapt een 4xx niet — dan zou de gebruiker niets zien
        # gebeuren, precies zoals bij een ongeldig e-mailadres hierboven.
        return _render_detail(request, db, registration_id, edit_open=True, error=str(fout))
    if bijgewerkt is None:
        raise HTTPException(status_code=404, detail=_("Registration not found"))
    # #717: dit is de afsluitende handeling, geen tussenstap. Openblijven gaf
    # hetzelfde scherm terug als vóór de klik — zelfde velden, zelfde knop, geen
    # enkel teken dat er bewaard was — en dus de reflex om nog eens te klikken.
    # Sluiten alleen volstaat niet (dan zie je leesmodus zonder bevestiging), een
    # toast alleen ook niet (dan blijft de knop staan). De tussenacties hierboven
    # en hieronder houden edit_open=True: dat is #613-3 en blijft gelden.
    bevestiging = _("De inschrijving is opgeslagen.")
    if terug_na > terug_voor:
        from app.kernel.geld import bedrag

        bevestiging += " " + _(
            "Er staat een terugbetaling van € %(bedrag)s klaar om te bevestigen."
        ) % {"bedrag": bedrag(terug_na)}
    return _render_detail(request, db, registration_id, ververs=True, toast=bevestiging)


@router.post(
    "/admin/inschrijvingen/{registration_id}/regels/{item_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def inschrijving_regel_bijwerken(
    registration_id: int,
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    quantity: int = Form(...),
) -> Response:
    from app.domains.activities import service

    reg = _reg_or_404(db, registration_id)
    try:
        gewijzigd = service.update_order_line(
            db, reg.activity_id, registration_id, item_id, quantity=quantity, actor=email
        )
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=400, detail=str(fout))
    if gewijzigd is None:
        raise HTTPException(status_code=404, detail=_("Order line not found"))
    return _render_detail(request, db, registration_id, edit_open=True, ververs=True)


# ── Inschrijvingen + export ────────────────────────────────────────────────────

# Sorteersleutels voor de inschrijvingenlijst (golf 4, #913 — zelfde regels als de
# golf 3-referentie op het e-maillog): een whitelist omdat de sleutel uit de
# querystring komt, en elke ordening eindigt op id (#761) zodat gelijke waarden een
# stabiele volgorde houden. Python-side, zoals ledenwijzigingen: de lijst is al
# verrijkt tot dicts wanneer hij hier aankomt.
# De sorteer-whitelist verhuisde naar de service (sorteer_inschrijvingen):
# de gezinstab sorteert sinds de unificatie met exact dezelfde sleutels.


def _record_tabs(
    activiteit: Any, reg_count: int, db: Session, email: str, actief: str, request: Request
) -> dict:
    """Doorgeefluik naar de ene bouwer van de recordkop-context (#1070).

    Stelde tot dan zelf twee sleutels samen, en `payment.ui` deed hetzelfde nog
    eens — zie `service.record_kop_ctx` voor waarom dat één plek geworden is.
    """
    from app.domains.activities.api import record_kop_ctx
    from app.ui import record_frame

    return {
        **record_kop_ctx(db, activiteit, email, actief, reg_count=reg_count),
        # #1557: the way back and the edit state, from the request.
        **record_frame(request, db, NAV),
    }


def _record_summary(
    db: Session, activiteit: Any, tabs: dict, reg_count: int, occupancy: dict[int, int]
) -> dict:
    """The summary card of the Gegevens tab (CR-11 K6, #1560; end state §3.10):
    the publication state, Inschrijvingen · Deelnemers · Openstaand, and the
    public link with its copy button. It replaces the card "Publicatie":
    Toegang is the head's badge and a form field, Inschrijven tot and Bezetting
    belong to the component (its row on the form).

    Counted, never listed (#651: the record page does not fetch the tree):
    `reg_count` is the tab's count and `occupancy` the one the component rows
    show (the same count as the full-up test, #451) — both asked once per
    request — and the open balance is one aggregate row. "Openstaand" only for
    who may see payments (#544): exactly who gets the Betalingen tab, so the
    answer is read from `tabs` (the head's context) and not asked again."""
    from app.domains.activities.api import publication
    from app.domains.payment.api import registration_balance_by_activity
    from app.kernel.codes import code_label, tone
    from app.kernel.geld import bedrag as money
    from app.kernel.tenant_config import tenant_base_url

    pub = publication(db, activiteit.id)
    if activiteit.is_cancelled:
        state = {"label": _("Geannuleerd"), "tone": "red"}
    else:
        state = {
            "label": code_label("activity_status", pub.status),
            "tone": tone("activity_status", pub.status),
        }
    figures: list[dict[str, Any]] = [
        {"label": _("Inschrijvingen"), "value": str(reg_count)},
        {
            "label": _("Deelnemers"),
            "value": str(sum(occupancy.get(c.id, 0) for c in activiteit.sub_registrations)),
        },
    ]
    if any(tab["href"].endswith("/betalingen") for tab in tabs["record_tabs"]):
        balance = registration_balance_by_activity(db, activiteit.id)
        figures.append(
            {"label": _("Openstaand"), "value": "€ " + money(balance), "warning": balance != 0}
        )
    action = None
    if not pub.draft:
        # The canonical address /activiteiten/<slug|nr>: the route itself leads
        # on to the coming list or the archive, so a link shared beforehand
        # keeps working after the event.
        href = f"{tenant_base_url(db)}/activiteiten/{activiteit.slug or activiteit.id}"
        action = {
            "href": href,
            "text": href.split("://", 1)[-1],
            "label": _("Kopieer de publieke link"),
        }
    return {"summary": {"state": state, "figures": figures, "action": action}}


def _board_form_page(
    request: Request,
    db: Session,
    activiteit: Any,
    onderdeel_id: int | None,
    *,
    values: dict | None = None,
    error: str | None = None,
) -> dict:
    """The board's "add a registration" page (#1192, #1284): the one registration
    form (`activities.api.form_context`, the board's channel) inside a back-office
    page with the component buttons above it."""
    from app.domains.activities.api import board_channel, form_context

    values = values or {}
    basis = f"/admin/activiteiten/{activiteit.id}/inschrijvingen"
    onderdelen = [
        {
            "id": c.id,
            "naam": c.name,
            "url": f"{basis}/nieuw?onderdeel={c.id}",
            "gekozen": c.id == onderdeel_id,
        }
        for c in activiteit.sub_registrations
    ]
    component = next((c for c in activiteit.sub_registrations if c.id == onderdeel_id), None)
    ctx: dict = {"error": error}
    if component is not None:
        channel = board_channel(db, activiteit, component, values.get("contact_email", ""))
        ctx = form_context(channel, activiteit, component, values=values, error=error)
    ctx.update(
        a=activiteit,
        onderdelen=onderdelen,
        onderdeel_id=component.id if component else None,
        terug_url=basis,
        csrf_token=csrf_from_request(request),
        nav_items=admin_nav(NAV),
    )
    return ctx


def _board_component(activiteit: Any, values: Mapping[str, Any]) -> tuple[int | None, Any]:
    onderdeel_id = int(values["onderdeel"]) if str(values.get("onderdeel", "")).isdigit() else None
    return onderdeel_id, next(
        (c for c in activiteit.sub_registrations if c.id == onderdeel_id), None
    )


@router.get("/admin/activiteiten/{activity_id}/inschrijvingen/nieuw", response_class=HTMLResponse)
def inschrijving_nieuw(
    activity_id: int,
    request: Request,
    onderdeel: int = 0,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """The board adds a registration (#1192). With one component it is chosen."""
    from app.domains.activities.api import get_activity

    activiteit = get_activity(db, activity_id)
    if activiteit is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    if not onderdeel and len(activiteit.sub_registrations) == 1:
        onderdeel = activiteit.sub_registrations[0].id
    return templates.TemplateResponse(
        request,
        "admin_inschrijving_nieuw.html",
        _board_form_page(request, db, activiteit, onderdeel or None),
    )


@router.post(
    "/admin/activiteiten/{activity_id}/inschrijvingen/nieuw/totaal",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def inschrijving_nieuw_totaal(
    activity_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """The board's recalculation (#1284): the public one's `total_context`, priced
    by the person of the TYPED e-mail address."""
    from app.domains.activities.api import board_channel, get_activity, total_context

    activiteit = get_activity(db, activity_id)
    if activiteit is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    form = await request.form()
    values = {k: (v if isinstance(v, str) else "") for k, v in form.items()}
    _onderdeel_id, component = _board_component(activiteit, values)
    if component is None:
        raise HTTPException(status_code=404, detail=_("Onderdeel niet gevonden"))
    channel = board_channel(db, activiteit, component, values.get("contact_email", ""))
    return templates.TemplateResponse(
        request, "_inschrijf_totaal.html", total_context(channel, component, form)
    )


@router.post(
    "/admin/activiteiten/{activity_id}/inschrijvingen/nieuw/prijzen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def inschrijving_nieuw_prijzen(
    activity_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """The board's price block after the e-mail address changed (#1284).

    Koen: the product rows follow the typed member address, not only the total.
    Rows and total come back together, from the same `form_context` as the page,
    with the quantities that were entered — the address field itself is not
    part of the swap, so it keeps its focus."""
    from app.domains.activities.api import (
        board_channel,
        form_context,
        form_quantities,
        get_activity,
    )

    activiteit = get_activity(db, activity_id)
    if activiteit is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    form = await request.form()
    values = {k: (v if isinstance(v, str) else "") for k, v in form.items()}
    _onderdeel_id, component = _board_component(activiteit, values)
    if component is None:
        raise HTTPException(status_code=404, detail=_("Onderdeel niet gevonden"))
    channel = board_channel(db, activiteit, component, values.get("contact_email", ""))
    return templates.TemplateResponse(
        request,
        "_inschrijf_prijsblok.html",
        form_context(
            channel, activiteit, component, values=values, quantities=form_quantities(form)
        ),
    )


@router.post(
    "/admin/activiteiten/{activity_id}/inschrijvingen/nieuw",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def inschrijving_nieuw_opslaan(
    activity_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """The board's channel of the one form (#1284): the processing is shared with
    the public form (`activities.api.submit`); what differs is where it lands —
    Mollie, or the registration in the back office (Koen: "de terugroutering")."""
    from app.domains.activities.api import OutcomeKind, board_channel, get_activity, submit

    activiteit = get_activity(db, activity_id)
    if activiteit is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    form = await request.form()
    values = {k: (v if isinstance(v, str) else "") for k, v in form.items()}
    onderdeel_id, component = _board_component(activiteit, values)
    if component is None:
        return templates.TemplateResponse(
            request,
            "admin_inschrijving_nieuw.html",
            _board_form_page(
                request, db, activiteit, onderdeel_id, values=values, error=_("Kies een onderdeel.")
            ),
        )
    channel = board_channel(db, activiteit, component, values.get("contact_email", ""))
    outcome = submit(db, channel, activiteit, component, form, background_tasks, actor=email)
    if outcome.kind is OutcomeKind.REFUSED:
        # #1589: the same answer as the public page — the banner, into the
        # form's message line.
        return refusal_response(request, outcome.errors, "#inschrijf-melding", send=True)
    response = HTMLResponse("")
    # Vaste UI-beslissing: harde redirect naar Mollie; zonder betaling naar de
    # inschrijving in het beheer.
    response.headers["HX-Redirect"] = (
        outcome.checkout_url
        if outcome.kind is OutcomeKind.CHECKOUT
        else f"/admin/inschrijvingen/{outcome.registration_id}"
    )
    return response


def _registrations_ctx(db: Session, activiteit: Any, request: Request) -> dict:
    """The registrations table of the activity's tab (K6, #1560), from the
    list's state — the URL's, or `HX-Current-URL` after a fragment request.

    Grouped per component, and "Zonder onderdeel" last so those stay reachable
    (the reason behind #650). Exporteren and Antwoorden stand under the group
    row's `⋯` (Q41)."""
    from app.domains.activities.api import (
        parse_registration_sort,
        registration_table,
        registrations_for,
    )
    from app.ui import filterparams

    stand = filterparams(request)
    regs = registrations_for(db, activiteit.id, alle=True) or []
    base = f"/admin/activiteiten/{activiteit.id}"
    groups = []
    for c in activiteit.sub_registrations:
        items = [
            {
                "label": _("Exporteren"),
                "href": f"{base}/onderdelen/{c.id}/export",
                "attrs": 'hx-boost="false"',
            }
        ]
        # CR-14 F14: the answers of a component that asks questions.
        if c.form_id is not None:
            items.append(
                {
                    "label": _("Antwoorden"),
                    "href": f"{base}/onderdelen/{c.id}/antwoorden",
                    "attrs": 'hx-boost="false" target="_blank"',
                }
            )
        groups.append(
            {
                "name": c.name,
                "regs": [r for r in regs if r["component_id"] == c.id],
                "items": items,
            }
        )
    without = [r for r in regs if r["component_id"] is None]
    if without:
        groups.append({"name": _("Zonder onderdeel"), "regs": without})
    return {
        **registration_table(
            db,
            groups,
            page_url=f"{base}/inschrijvingen",
            fragment_url=f"{base}/inschrijvingen/lijst",
            view=stand.get("zicht", "alle"),
            q=stand.get("q", ""),
            sort=parse_registration_sort(stand.get("sort", "datum"), stand.get("richting", "")),
            open_row=stand.get("rij", ""),
        ),
        "reg_target": "#inschrijvingen-lijst",
        "reg_count": len(regs),
    }


@router.get("/admin/activiteiten/{activity_id}/inschrijvingen", response_class=HTMLResponse)
def activiteit_inschrijvingen_tab(
    activity_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """The Inschrijvingen tab of the record page (golf 8, #913; K6, #1560): every
    registration of the activity in one table, a collapsible group row per
    component, under the toolbar of the embedded list."""
    from app.domains.activities.api import get_activity
    from app.domains.activities.viewmodels import AdminActiviteitInschrijvingenView

    activiteit = get_activity(db, activity_id)
    if activiteit is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    ctx = _registrations_ctx(db, activiteit, request)
    reg_count = ctx.pop("reg_count")
    vm = AdminActiviteitInschrijvingenView(
        a=activiteit,
        **ctx,
        **_record_tabs(activiteit, reg_count, db, email, "inschrijvingen", request),
        csrf_token=csrf_from_request(request),
        nav_items=admin_nav(NAV),
    )
    return templates.TemplateResponse(
        request, "admin_activiteit_inschrijvingen.html", vm.as_context()
    )


@router.get("/admin/activiteiten/{activity_id}/inschrijvingen/lijst", response_class=HTMLResponse)
def activity_registrations_list(
    activity_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """The list alone, for the toolbar and a sort link: the table, and
    out-of-band the toolbar's count, the count on "Openstaand" and the sort."""
    from app.domains.activities.api import get_activity
    from app.domains.activities.viewmodels import ActivityRegistrationsListView

    activiteit = get_activity(db, activity_id)
    if activiteit is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    ctx = _registrations_ctx(db, activiteit, request)
    ctx.pop("reg_count")
    vm = ActivityRegistrationsListView(**ctx, reg_oob=True)
    return templates.TemplateResponse(request, "_aa_inschrijvingen_lijst.html", vm.as_context())


@router.post(
    "/admin/activiteiten/{activity_id}/inschrijvingen/{registration_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def inschrijving_verwijderen(
    activity_id: int,
    registration_id: int,
    request: Request,
    component_id: int | None = None,
    sort: str = "datum",
    richting: str = "asc",
    vanuit: str = "",
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    """Verwijdert een inschrijving en keert terug naar de activiteit.

    Sinds feedbackronde 2 van golf 8 is de inschrijvingspagina (cluster,
    uiterst links) de enige plek met een verwijderknop — de lijstfragmenten
    met een directe rij-delete bestaan niet meer. De oude parameters blijven
    aanvaard zodat bestaande links geen 422 geven."""
    from app.domains.activities import service

    if not service.delete_registration(db, activity_id, registration_id, actor=email):
        raise HTTPException(status_code=404, detail=_("Registration not found"))
    return Response(status_code=204, headers={"HX-Redirect": f"/admin/activiteiten/{activity_id}"})


@router.get("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/export")
def onderdeel_export(
    activity_id: int,
    component_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> Response:
    from app.domains.activities import service

    resultaat = service.component_export(db, activity_id, component_id)
    if resultaat is None:
        raise HTTPException(status_code=404, detail=_("Component not found"))
    inhoud, bestandsnaam = resultaat
    return Response(
        content=inhoud,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={"Content-Disposition": f'attachment; filename="{bestandsnaam}"'},
    )


@router.get("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/boek")
def component_book_old_path(activity_id: int, component_id: int) -> Response:
    """The page was called "Boek" until #1382; a saved or shared old address keeps
    working. A path a person sees follows the UI's word (CLAUDE.md, URL paths)."""
    return RedirectResponse(
        f"/admin/activiteiten/{activity_id}/onderdelen/{component_id}/antwoorden",
        status_code=301,
    )


@router.get(
    "/admin/activiteiten/{activity_id}/onderdelen/{component_id}/antwoorden",
    response_class=HTMLResponse,
)
def component_book_page(
    activity_id: int,
    component_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
) -> HTMLResponse:
    """The answers of a component (CR-14 F14, "Antwoorden" since #1382 — the book in
    the code): one page per registration, to print or to read and copy. Admin only,
    like the export it is read from."""
    from app.domains.activities.api import (
        component_book,
        get_activity,
        get_component,
        question_form,
    )

    activity = get_activity(db, activity_id)
    component = get_component(db, component_id, activity_id=activity_id)
    if activity is None or component is None:
        raise HTTPException(status_code=404, detail=_("Component not found"))
    return templates.TemplateResponse(
        request,
        "onderdeel_boek.html",
        {
            "activiteit": activity.name,
            "onderdeel": component.name,
            "vraagt_antwoorden": question_form(db, component) is not None,
            "blokken": component_book(db, activity, component),
        },
    )


# ── Organisatoren (#1004, CR-10 §3.9) ────────────────────────────────────────


@router.get("/admin/activiteiten/{activity_id}/organisatoren", response_class=HTMLResponse)
def organisatoren_zoeken(
    activity_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
    organiser_q: str = "",
) -> Response:
    """The candidates of the organiser search — members only (#1004).

    Searching is `search_persons` of mdm (#1006), the function the meeting circle
    uses; `members_only`, because an organiser is a member. Since #1559 the answer
    is the list of candidates alone: picking one adds a row to the fiche in the
    page, and the one save writes it.
    """
    from app.domains.activities.api import organisers_for
    from app.domains.mdm.api import household_ids, search_persons

    taken = {o.person_id for o in organisers_for(db, activity_id)}
    candidates = search_persons(db, organiser_q, members_only=True, exclude_ids=taken)
    found = {
        "organiser_query": organiser_q,
        "organiser_candidates": candidates,
        "organiser_households": household_ids(db, [c.person.id for c in candidates]),
    }
    return templates.TemplateResponse(request, "_aa_org_candidates.html", found)
