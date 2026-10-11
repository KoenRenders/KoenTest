"""Server-rendered ledenbeheer (fase 2b, #400 — §21): gezinnenlijst met zoeken
en paginering, gezinsdetail (personen, adres, bestuurslid, lidmaatschappen) en
de leden-import-wizard (preview → commit).

De schermen hergebruiken de bestaande admin-API-functies (routers/members.py,
domains/mdm/import_router.py — #444) als servicelaag — geen dubbele businesslogica; deze
module bouwt alleen view-models en kiest templates.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    Right,
    admin_user_by_email,
    csrf_from_request,
    require_csrf,
    require_right,
)
from app.domains.mdm.viewmodels import HouseholdRecordView, LedenView
from app.i18n import _
from app.ui import admin_nav, filterparams, refusal_response, templates

router = APIRouter(include_in_schema=False)

NAV = "/admin/leden"


def _codes(db: Session) -> dict:
    """The code lists a person form shows, and the longest name it takes — the
    number the server refuses at, so the field's `maxlength` cannot drift from it."""
    from app.domains.mdm.api import PERSON_NAME_MAX, admin_code_lists

    return {**admin_code_lists(db), "person_name_max": PERSON_NAME_MAX}


def _lidmaatschapsjaren(db: Session) -> list[int]:
    from app.domains.membership.api import membership_years

    return membership_years(db)


LIST = NAV + "/lijst"
#: The list's segments (#1899): no "Alle" — a list opens on a status.
STATUSES = ("actief", "vernieuwen", "opgezegd")
SORTS = ("naam", "-naam")


def _figures(db: Session, to_renew: int) -> list[dict]:
    """The three figures in the title row (#582, #1899). "Te vernieuwen" carries
    its target year, which tilts on the tenant's date
    ``membership_next_year_from_md``; the rules are membership's — this screen
    counts nothing itself. `to_renew` comes with the list (`to_renew_total`):
    the same set its segment filters on."""
    from app.domains.membership.api import current_membership_counts, renewal_years

    households, persons = current_membership_counts(db)
    reference, target = renewal_years()
    return [
        {
            "value": str(households),
            "label": _("Actieve gezinnen"),
            "title": _("Gezinnen met een lidmaatschap dat vandaag geldig is."),
        },
        {
            "value": str(persons),
            "label": _("Actieve personen"),
            "title": _("Personen in die gezinnen."),
        },
        {
            "value": str(to_renew),
            "label": _("Te vernieuwen %(jaar)s") % {"jaar": target},
            "title": _("Lid in %(referentie)s, nog niet vernieuwd voor %(doel)s.")
            % {"referentie": reference, "doel": target},
            "warning": to_renew > 0,
        },
    ]


def _empty_reason(status: str, q: str, jaar: int | None) -> str:
    if q or jaar:
        return _("Geen gezinnen gevonden voor deze zoekopdracht.")
    if status == "vernieuwen":
        return _("Er is geen gezin te vernieuwen.")
    if status == "opgezegd":
        return _("Er zijn geen opgezegde gezinnen.")
    return _("Er zijn nog geen actieve gezinnen.")


def _lijst_view(request: Request, db: Session, **extra) -> LedenView:
    """The view-model of the member list (#643, #1899): the page and its fragment.

    The list's state — segment, search, year, sort, page, page size — lives in
    the URL (#671: from HX-Current-URL when htmx sends it, else the query)."""
    from urllib.parse import urlencode

    from app.domains.mdm.api import household_address_line, membership_badge
    from app.domains.membership.api import family_label, list_families
    from app.ui import PER_PAGE_OPTIONS, per_page_from

    stand = filterparams(request)
    q = (stand.get("q") or "").strip()
    status = (stand.get("status") or "").strip()
    if status not in STATUSES:
        status = STATUSES[0]
    sort = (stand.get("sort") or "").strip()
    if sort not in SORTS:
        sort = SORTS[0]
    jaar_raw = (stand.get("jaar") or "").strip()
    jaar = int(jaar_raw) if jaar_raw.isdigit() else None
    per_page = per_page_from(stand.get("per_page"))
    try:
        page = max(1, int(stand.get("page") or 1))
    except ValueError:
        page = 1

    def _found(at: int):
        return list_families(
            db,
            page=at,
            page_size=per_page,
            q=q or None,
            status=status,
            membership_year=jaar,
            sort=sort,
        )

    data = _found(page)
    last = max(1, data.total_pages)
    if page > last:
        page = last
        data = _found(page)
    state = {"status": status, "q": q, "jaar": jaar or "", "per_page": per_page}

    def _query(**more) -> str:
        return urlencode({k: v for k, v in {**state, **more}.items() if v != ""})

    # A click on the head turns the sort; it keeps the rest and goes to page 1.
    turned = "-naam" if sort == "naam" else "naam"
    labels = {
        "actief": _("Actief"),
        "vernieuwen": _("Te vernieuwen"),
        "opgezegd": _("Opgezegd"),
    }
    return LedenView(
        rows=[
            {
                "id": f.id,
                "name": family_label(f),
                "address": household_address_line(f),
                "persons": len(f.members),
                "badge": membership_badge(f),
            }
            for f in data.items
        ],
        columns=[
            {
                "key": "gezin",
                "label": _("Gezin"),
                "cell": "name",
                "sort_url": f"{LIST}?{_query(sort=turned)}",
                "sort_page_url": f"{NAV}?{_query(sort=turned)}",
                "sorted": "desc" if sort.startswith("-") else "asc",
            },
            {
                "key": "personen",
                "label": _("Personen"),
                "cell": "extra",
                "num": True,
                "priority": 1,
            },
            {"key": "lidmaatschap", "label": _("Lidmaatschap"), "cell": "status"},
        ],
        segments=[
            # Opgezegd carries no count (#1899): the two others are what the
            # board acts on.
            {
                "value": s,
                "label": labels[s],
                **({"count": data.counts[s]} if s in data.counts else {}),
            }
            for s in STATUSES
        ],
        figures=_figures(db, data.to_renew_total),
        status=status,
        q=q,
        jaar=jaar,
        jaren=_lidmaatschapsjaren(db),
        sort=sort,
        sort_options=[("naam", _("Gezin (A–Z)")), ("-naam", _("Gezin (Z–A)"))],
        page=page,
        per_page=per_page,
        total=data.total,
        page_sizes=list(PER_PAGE_OPTIONS),
        pager_url=f"{LIST}?{_query(sort=sort)}",
        empty_reason=_empty_reason(status, q, jaar),
        csrf_token=csrf_from_request(request),
        **extra,
    )


RECORD_MESSAGE = "#gezin-melding"


def _record_view(
    request: Request, db: Session, family_id: int, email: str, *, edit: bool, saved: bool = False
) -> HouseholdRecordView:
    """The household's record (#1899; end state §5.2): the head, the tabs, the
    summary, and the cards — the persons from membership's one group of person
    cards (the cards of Mijn gezin), the board member and the years.

    `edit` is asked AND allowed: without the right to change master data the
    record is read."""
    from app.domains.auth.api import may
    from app.domains.mdm.api import (
        form_code_lists,
        gezin_tabs,
        household_record_head,
        list_persons,
        membership_badge,
    )
    from app.domains.membership.api import board_household_group, get_family
    from app.ui import record_frame

    geld = templates.env.filters["geld"]

    family = get_family(db, family_id)
    may_change = may(db, email, Right.PARTY_MASTERDATA)
    edit = edit and may_change
    frame = record_frame(request, db, NAV)
    group = board_household_group(
        db,
        family_id,
        form_code_lists(db),
        short_date=templates.env.filters["kortedatum"],
        edit=edit,
    )
    label, tone = membership_badge(family)
    figures: list[dict[str, object]] = [{"label": _("Personen"), "value": str(len(family.members))}]
    if may(db, email, Right.PAYMENT_VIEW):
        from app.domains.payment.api import balance_of_family

        open_amount = balance_of_family(db, family_id)
        figures.append(
            {
                "label": _("Openstaand"),
                "value": "€ " + geld(open_amount),
                "warning": open_amount != 0,
            }
        )
    years = [
        {
            "id": m.id,
            "year": m.year,
            # The year the household is a member through today.
            "active": bool(m.is_active and m.valid_to and family.member_until == m.valid_to.year),
            "waiting": not m.is_active,
        }
        for m in sorted(family.memberships, key=lambda m: m.year, reverse=True)
    ]
    board = family.board_member
    return HouseholdRecordView(
        family_id=family_id,
        page_title=family_label_of(family),
        record_head=household_record_head(family, may_change=may_change),
        record_tabs=gezin_tabs(db, family, email, "overzicht"),
        way_back=frame["way_back"],
        head_editing=edit,
        summary={"state": {"label": label, "tone": tone}, "figures": figures},
        group=group,
        edit=edit,
        saved=saved,
        years=years,
        board_member_id=str(board.id) if board else "",
        board_member_name=f"{board.first_name} {board.last_name}".strip() if board else "",
        board_options=[("", _("— Geen —"))]
        + [(str(p.id), f"{p.last_name} {p.first_name}".strip()) for p in list_persons(db)]
        if edit
        else [],
        csrf_token=csrf_from_request(request),
        nav_items=admin_nav(NAV, request),
    )


def family_label_of(family) -> str:
    from app.domains.membership.api import family_label

    return family_label(family)


def _record_page(
    request: Request, db: Session, family_id: int, email: str, *, edit: bool, saved: bool = False
):
    view = _record_view(request, db, family_id, email, edit=edit, saved=saved)
    return templates.TemplateResponse(request, "leden_gezin.html", view.as_context())


# ── Overzicht ──────────────────────────────────────────────────────────────────


@router.get("/admin/leden", response_class=HTMLResponse)
def leden_page(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_VIEW)),
):
    return templates.TemplateResponse(
        request,
        "leden.html",
        _lijst_view(request, db, nav_items=admin_nav(NAV, request)).as_context(),
    )


@router.get("/admin/leden/lijst", response_class=HTMLResponse)
def leden_lijst(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_VIEW)),
):
    """The list alone: the toolbar swaps this fragment, so the search field is
    not replaced under the fingers."""
    return templates.TemplateResponse(
        request, "_leden_lijst.html", _lijst_view(request, db, oob=True).as_context()
    )


@router.get("/admin/leden/nieuw", response_class=HTMLResponse)
def lid_nieuw(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_VIEW)),
):
    """Aanmaken als volledige pagina (#627, §2.8) i.p.v. een modal."""
    from app.domains.mdm.api import list_postal_codes

    return templates.TemplateResponse(
        request,
        "leden_nieuw.html",
        {
            "nav_items": admin_nav(NAV, request),
            "csrf_token": csrf_from_request(request),
            "postal_codes": list_postal_codes(db),
            "values": {},
            "error": None,
            **_codes(db),
        },
    )


@router.get("/admin/leden/nieuw/persoon-rij", response_class=HTMLResponse)
def lid_nieuw_persoon_rij(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_VIEW)),
):
    """Een lege rij voor een extra gezinslid (#1110).

    Hetzelfde fragment als het publieke formulier, want het zijn dezelfde velden;
    een eigen admin-route omdat dit scherm achter de beheerdeur hoort te zitten.
    Er gaat niets naar de databank en er wordt niets vervangen, dus wat je al
    typte blijft staan.
    """
    try:
        index = max(1, int(request.query_params.get("index", "1")))
    except ValueError:
        index = 1
    return templates.TemplateResponse(
        request, "_lid_persoon_rij.html", {**_codes(db), "i": index, "values": {}}
    )


@router.post("/admin/leden", dependencies=[Depends(require_csrf)])
async def gezin_aanmaken(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_MASTERDATA)),
) -> Response:
    """Nieuw gezin met hoofdlid, adres, contactgegevens en lidmaatschap (#1110).

    Eén formulier, één opslaan-actie, één transactie — in de vorm van het publieke
    "Word lid" en langs dezelfde schrijfweg. Tot #1110 waren het vier aparte
    opslag-acties en vroeg dit scherm e-mail en gsm van het hoofdlid niet eens,
    terwijl het publieke formulier ze verplicht: je kon via de beheerkant dus een
    lid aanmaken dat publiek geweigerd zou worden. Dezelfde regel op één plek
    (`FamilyCreate`) betekent dat dat niet meer kan.

    #713: de beheerder tekent de auditregels.
    """
    from app.domains.mdm.api import EmailAddressInUse, list_postal_codes
    from app.domains.membership.api import (
        create_family_by_admin,
        family_from_rows,
        parse_member_rows,
    )

    form = await request.form()
    values = {k: (v if isinstance(v, str) else "") for k, v in form.items()}

    def _fout(melding: str):
        """Het formulier opnieuw, mét wat er ingevuld stond en de reden.

        De keuzelijsten worden hier opgehaald en niet bovenaan: een mislukte
        opslag rolt de transactie terug (#1110), en objecten die vóór die rollback
        geladen zijn, bestaan daarna niet meer. Ze alsnog renderen geeft een
        harde fout in plaats van de nette foutpagina.
        """
        return templates.TemplateResponse(
            request,
            "leden_nieuw.html",
            {
                "nav_items": admin_nav(NAV, request),
                "csrf_token": csrf_from_request(request),
                "postal_codes": list_postal_codes(db),
                "values": values,
                "error": melding,
                **_codes(db),
            },
            status_code=422,
        )

    try:
        data = family_from_rows(values, parse_member_rows(form))
        gezin = create_family_by_admin(db, data, actor=email)
    except HTTPException as exc:
        return _fout(str(exc.detail))
    except EmailAddressInUse as in_use:
        # mdm's own refusal, which the application answers as a JSON 422 for
        # every other door: here it belongs in the page's banner (#1831).
        return _fout(str(in_use))

    return Response(status_code=204, headers={"HX-Redirect": f"/admin/leden/gezin/{gezin.id}"})


@router.get("/admin/leden/gezin/{family_id}", response_class=HTMLResponse)
def gezin_detail(
    family_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_VIEW)),
):
    """The household's record (#1899): read first, `?bewerken=1` the edit mode
    with ONE "Opslaan" — the shape of Mijn gezin, in the admin shell."""
    return _record_page(
        request, db, family_id, email, edit=request.query_params.get("bewerken") == "1"
    )


@router.post(
    "/admin/leden/gezin/{family_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def save_household_record(
    family_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_MASTERDATA)),
):
    """The one "Opslaan" of the household's record (#1899): the address, the
    persons with their e-mail addresses and relations, the board member and the
    removed membership years, in ONE transaction — mdm's `save_household` with
    the board as its caller, and the years handed to membership inside it.

    Until #1899 the record had eleven partial routes that each committed on
    their own. A refusal writes nothing and leaves the form as it was typed: the
    answer is the banner alone, with every refused field or row named. A good
    save answers the record in read mode."""
    from app.domains.mdm.api import (
        HouseholdSaveRefused,
        household_from_form,
        household_refusals_as_http,
        household_with_id,
        save_household,
    )
    from app.domains.membership.api import get_family, remove_memberships

    form = await request.form()
    payload = household_from_form(form)
    with household_refusals_as_http():
        household = household_with_id(db, family_id)
    kept = {key for key in form.getlist("y_order")}
    removed = [m.id for m in get_family(db, family_id).memberships if str(m.id) not in kept]
    board_member = str(form.get("board_member_id") or "").strip()

    def _years(session: Session) -> None:
        remove_memberships(session, family_id, removed, actor=email)

    try:
        save_household(
            db,
            household,
            payload,
            by=None,
            actor=email,
            board_member=int(board_member) if board_member.isdigit() else None,
            also=_years if removed and "y_sent" in form else None,
        )
    except HouseholdSaveRefused as refusal:
        return refusal_response(request, refusal.errors, RECORD_MESSAGE)
    response = _record_page(request, db, family_id, email, edit=False, saved=True)
    response.headers["HX-Push-Url"] = f"/admin/leden/gezin/{family_id}"
    return response


@router.get("/admin/leden/gezin/{family_id}/inschrijvingen", response_class=HTMLResponse)
def gezin_inschrijvingen_tab(
    family_id: int,
    request: Request,
    sort: str = "datum",
    richting: str = "",
    rij: str = "",
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_VIEW)),
):
    """The Inschrijvingen tab of the household's page (Koen, 15 September — it
    replaced the Wijzigingen tab): what this household registered for, grouped
    per activity, from the household's persons (person_id and the e-mail
    fallback for guest registrations — the same one source as the Betalingen
    tab). The table is the one of the activity's tab (K6, #1560); the toolbar
    and the rest of the household's page are pilot B."""
    from app.domains.activities.api import parse_registration_sort, registration_table
    from app.domains.auth.api import Right, may
    from app.domains.mdm.api import family_registrations, household_record_frame
    from app.domains.membership.api import get_family

    try:
        family = get_family(db, family_id)
    except Exception:
        family = None
    if family is None:
        raise HTTPException(status_code=404, detail=_("Gezin niet gevonden"))
    table = registration_table(
        db,
        family_registrations(db, family_id),
        page_url=f"/admin/leden/gezin/{family_id}/inschrijvingen",
        # A forged sort never reaches a link: the builder validates it.
        sort=parse_registration_sort(sort, richting),
        open_row=rij,
        sub_is_component=True,
        may_mutate=may(db, email, Right.PAYMENT_MANAGE),
    )
    return templates.TemplateResponse(
        request,
        "admin_gezin_inschrijvingen.html",
        {
            "nav_items": admin_nav(NAV, request),
            "family": family,
            **household_record_frame(request, db, family, email, "inschrijvingen"),
            **table,
            # No list fragment of its own: a sort link is the page.
            "reg_target": "",
            "csrf_token": csrf_from_request(request),
        },
    )


# ── The delete of the household ───────────────────────────────────────────────


@router.post(
    "/admin/leden/gezin/{family_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def gezin_verwijderen(
    family_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_MASTERDATA)),
):
    from app.domains.mdm.api import delete_household

    delete_household(db, family_id, admin=admin_user_by_email(db, email))
    # Verwijderen gebeurt vanuit de gezinseditor; die pagina bestaat daarna niet
    # meer, dus terug naar de lijst (#582).
    return Response(status_code=204, headers={"HX-Redirect": "/admin/leden"})


# ── Leden-import-wizard ────────────────────────────────────────────────────────


@router.get("/admin/leden-import", response_class=HTMLResponse)
def import_page(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_VIEW)),
):
    nav = [dict(item, active=False) for item in admin_nav(NAV, request)]
    return templates.TemplateResponse(
        request,
        "leden_import.html",
        {
            "csrf_token": csrf_from_request(request),
            "nav_items": nav,
        },
    )


@router.post(
    "/admin/leden-import/preview", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
async def import_preview(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_MASTERDATA)),
    file: UploadFile = File(...),
):
    from app.domains.mdm.api import import_preview

    try:
        data = await import_preview(db, file, admin=admin_user_by_email(db, email))
    except HTTPException as exc:
        return templates.TemplateResponse(
            request, "_leden_import_resultaat.html", {"error": exc.detail, "stap": "preview"}
        )
    return templates.TemplateResponse(
        request,
        "_leden_import_resultaat.html",
        {"error": None, "stap": "preview", "data": data, "report": data["report"]},
    )


@router.post(
    "/admin/leden-import/commit", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
def import_commit(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.PARTY_MASTERDATA)),
    token: str = Form(...),
):
    from app.domains.mdm.api import import_commit

    try:
        data = import_commit(db, token, admin=admin_user_by_email(db, email))
    except HTTPException as exc:
        return templates.TemplateResponse(
            request, "_leden_import_resultaat.html", {"error": exc.detail, "stap": "commit"}
        )
    return templates.TemplateResponse(
        request,
        "_leden_import_resultaat.html",
        {"error": None, "stap": "commit", "data": data, "report": data["report"]},
    )


# ── The family portal: a member changes a person of their household ──────────
#
# CR-13 phase 3 (#1250): the household and its persons are master data (Koen, 27
# September 2026: *"gezin en personen is mdm"*), so the doors that change them are
# `mdm`'s. The portal itself stays `membership`'s screen; these routes ask it who is
# logged in and for the page to answer with, both reads through `membership.api`.
# Since #1590 there is one door: the page's one "Opslaan". The three row routes
# (a person saved, added, removed on their own) are gone; the JSON API under
# `/api/v1/member/household/…` keeps its own doors on the same cores.


#: Where a refused save of the household is shown: the page's message line.
HOUSEHOLD_MESSAGE = "#gezin-melding"


@router.post("/leden/gezin", response_class=HTMLResponse)
async def portal_household_save(request: Request, db: Session = Depends(get_db)):
    """The one "Opslaan" of the household (#1590): its persons, their e-mail
    addresses and the address, written in one transaction by
    `mdm.household_save.save_household`.

    The form is read by name (`household_form`), because its rows are not a fixed
    list of parameters. A refusal writes nothing and leaves the form as it was
    typed: the answer is the banner alone, for the page's message line, with every
    refused field or row named (`app.ui.refusal_response`, the frame's one way).
    A good save answers the page in read mode.
    """
    from app.domains.mdm.api import (
        HouseholdSaveRefused,
        actor_of,
        household_from_form,
        household_of,
        household_refusals_as_http,
        save_household,
    )
    from app.domains.membership.api import family_portal_page, portal_member

    person = portal_member(request, db)
    payload = household_from_form(await request.form())
    with household_refusals_as_http():
        household = household_of(db, person)
    try:
        save_household(db, household, payload, by=person, actor=actor_of(person))
    except HouseholdSaveRefused as refusal:
        return refusal_response(request, refusal.errors, HOUSEHOLD_MESSAGE)
    # The page is back in read mode and says so (§2.6: "Opgeslagen ✓").
    return family_portal_page(request, db, person)
