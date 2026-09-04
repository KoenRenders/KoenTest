"""Server-rendered admin-activiteitenbeheer (fase 4a-4, #402 — §21).

Volledige CRUD op activiteiten, datums, onderdelen en producten, plus de
inschrijvingenlijst en de .ods-export per onderdeel. Hergebruikt de bestaande
router-functies als servicelaag; sessie-auth + CSRF zoals de andere schermen.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    admin_user_by_email, csrf_from_request,
    SESSION_COOKIE, User, csrf_token_for, require_admin_ui, require_csrf,
)
from app.ui import admin_nav, templates
from app.i18n import _
from pydantic import ValidationError

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/activiteiten")


def _decimal(value: str, default: str = "0") -> Decimal:
    try:
        return Decimal((value or default).replace(",", "."))
    except InvalidOperation:
        raise HTTPException(status_code=400, detail=_("Ongeldig bedrag."))


def _opt_int(value: str) -> Optional[int]:
    value = (value or "").strip()
    return int(value) if value else None


def _opt_str(value: str) -> Optional[str]:
    value = (value or "").strip()
    return value or None


def _upload_error(exc: HTTPException) -> str:
    """Toon de upload-fout aan de beheerder i.p.v. ze stil te laten mislukken (htmx
    swapt niet op een 4xx). Bij een niet-ondersteund type een concrete hint —
    o.a. iPhone-HEIC-foto's worden niet aanvaard."""
    detail = str(exc.detail)
    if "bestandstype" in detail.lower():
        return detail + " — " + _("gebruik een PNG, JPG, WEBP, GIF of PDF "
                                  "(een iPhone-HEIC-foto werkt niet).")
    return detail


def _verplaats(db: Session, siblings, item_id: int, richting: str) -> None:
    """Herorden broers/zussen via ``sort_order``: normaliseer eerst naar 0..n (zo
    zijn er altijd distincte waarden, ook als alles nog op de default 0 staat) en
    wissel dan met de buur in de gevraagde richting. Buiten bereik = no-op."""
    ordered = sorted(siblings, key=lambda s: (s.sort_order or 0, s.id))
    for idx, s in enumerate(ordered):
        s.sort_order = idx
    positie = next((i for i, s in enumerate(ordered) if s.id == item_id), None)
    if positie is not None:
        buur = positie - 1 if richting == "omhoog" else positie + 1
        if 0 <= buur < len(ordered):
            ordered[positie].sort_order, ordered[buur].sort_order = (
                ordered[buur].sort_order, ordered[positie].sort_order)
    db.commit()


SCOPES = ("upcoming", "archived", "all")


def _lijst_ctx(db: Session, scope: str = "all", q: str = "") -> dict:
    """Lijst-context voor de records-lijst (C1, #586): scope-chips + vrij zoeken.

    Zoeken gebeurt op de reeds opgehaalde lijst i.p.v. in een tweede query: het
    zijn tientallen activiteiten, geen duizenden, en list_activities levert al de
    view-modellen mét telling en volzet-status waar de kaarten op steunen.
    """
    from app.domains.activities.router import list_activities

    if scope not in SCOPES:
        scope = "all"
    activiteiten = list_activities(scope=scope, db=db)
    term = q.strip().lower()
    if term:
        activiteiten = [a for a in activiteiten
                        if term in (a.name or "").lower()
                        or term in (a.location or "").lower()]
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
        "kpi_open": sum(1 for a in activities if a.status == "Open"),
        "kpi_vol": sum(1 for c in onderdelen if getattr(c, "is_full", False)),
        "kpi_onderdelen": len(onderdelen),
    }


def _detail_response(request: Request, db: Session, activity_id: int,
                     error: str | None = None):
    from app.domains.activities.router import list_activities

    activiteit = next((a for a in list_activities(scope="all", db=db)
                       if a.id == activity_id), None)
    if activiteit is None:
        return HTMLResponse('<div id="aa-detail" hx-swap-oob="true"></div>')
    return templates.TemplateResponse(request, "_aa_detail.html", {
        "a": activiteit, "csrf_token": csrf_from_request(request), "error": error})


@router.get("/admin/activiteiten", response_class=HTMLResponse)
def admin_activiteiten(request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_admin_ui),
                       scope: str = "upcoming", q: str = ""):
    ctx = _lijst_ctx(db, scope, q)
    # De kengetallen tellen wat er openstaat, niet wat er toevallig gefilterd is:
    # een zoekterm mag "Open inschrijvingen" niet doen dalen. Zonder filter is de
    # getoonde lijst al de juiste bron en blijft het bij één query.
    kpi_bron = (ctx["activities"] if (scope == "upcoming" and not q.strip())
                else _lijst_ctx(db, "upcoming")["activities"])
    # De filterbalk vraagt enkel de kaarten op; zou ze de pagina vervangen, dan
    # sneuvelt het zoekveld (en de focus) bij elke aanslag.
    sjabloon = ("_aa_kaarten.html" if request.headers.get("hx-request")
                else "admin_activiteiten.html")
    return templates.TemplateResponse(request, sjabloon, {
        "nav_items": NAV, "csrf_token": csrf_from_request(request),
        **_kpi(kpi_bron), **ctx})


@router.get("/admin/activiteiten/{activity_id}", response_class=HTMLResponse)
def admin_activiteit_detail(activity_id: int, request: Request,
                            db: Session = Depends(get_db),
                            email: str = Depends(require_admin_ui)):
    """Een kaart opent de paginabrede editor (C1, #586); de bewerkingen daarin
    blijven htmx-fragmenten die in #aa-detail landen."""
    if request.headers.get("hx-request"):
        return _detail_response(request, db, activity_id)
    from app.domains.activities.router import list_activities

    activiteit = next((a for a in list_activities(scope="all", db=db)
                       if a.id == activity_id), None)
    if activiteit is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    return templates.TemplateResponse(request, "admin_activiteit.html", {
        "nav_items": NAV, "a": activiteit,
        "csrf_token": csrf_from_request(request), "error": None})


@router.get("/admin/activiteiten/nieuw", response_class=HTMLResponse)
def activiteit_nieuw(request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui)):
    """Paginabreed aanmaakscherm i.p.v. een modal (#623).

    Bewust géén lege activiteit vooraf aanmaken: dan staat er een naamloze activiteit
    in de databank zodra iemand per ongeluk klikt, en die kan publiek opduiken zodra
    ze een datum krijgt. Het scherm draagt dezelfde kaart als de editor waarin je
    daarna werkt, dus er is geen tweede lay-out om te onderhouden.
    """
    return templates.TemplateResponse(request, "admin_activiteit_nieuw.html", {
        "nav_items": NAV,
        "csrf_token": csrf_from_request(request),
    })


@router.post("/admin/activiteiten", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def activiteit_aanmaken(request: Request, db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui),
                        name: str = Form(""), start_date: str = Form(""),
                        location: str = Form(""), poster_url: str = Form(""),
                        members_only: str = Form("")):
    from app.domains.activities.router import create_activity
    from app.schemas.activity import ActivityCreate, ActivityDateCreate

    if not name.strip() or not start_date:
        raise HTTPException(status_code=400, detail=_("Naam en eerste datum zijn verplicht."))
    nieuw = create_activity(ActivityCreate(
        name=name.strip(), location=location.strip() or None,
        poster_url=poster_url.strip() or None,
        members_only=bool(members_only),
        dates=[ActivityDateCreate(start_date=start_date)],
    ), db=db, admin=admin_user_by_email(db, email))
    # Aanmaken opent meteen de editor: een verse activiteit heeft nog datums en
    # onderdelen nodig, en die staan daar (C1, #586).
    return Response(status_code=204,
                    headers={"HX-Redirect": f"/admin/activiteiten/{nieuw.id}"})


@router.post("/admin/activiteiten/{activity_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def activiteit_bijwerken(activity_id: int, request: Request,
                               background_tasks: BackgroundTasks,
                               db: Session = Depends(get_db),
                               email: str = Depends(require_admin_ui),
                               name: str = Form(""), location: str = Form(""),
                               poster_url: str = Form(""),
                               members_only: str = Form(""), is_cancelled: str = Form(""),
                               file: Optional[UploadFile] = File(None)):
    """Bewerkt de activiteit; één "Opslaan" bewaart tekstvelden én de affiche (#623).

    `poster_url` was uit het scherm verdwenen terwijl het veld op het model en in de
    schemas bleef bestaan — je kon alleen nog uploaden. Beide horen in dezelfde vorm,
    zoals in v1.14: een geüploade affiche primeert op de URL (#223).
    """
    from app.domains.activities.router import update_activity
    from app.domains.media.api import upload_activity_poster
    from app.schemas.activity import ActivityUpdate

    admin = admin_user_by_email(db, email)
    update_activity(activity_id, ActivityUpdate(
        name=name.strip() or None, location=location.strip() or None,
        poster_url=poster_url.strip() or None,
        members_only=bool(members_only), is_cancelled=bool(is_cancelled),
    ), db=db, admin=admin)

    if file is not None and file.filename:
        try:
            await upload_activity_poster(activity_id, background_tasks, file=file,
                                         db=db, _admin=admin)
        except HTTPException as exc:
            return _detail_response(request, db, activity_id, error=_upload_error(exc))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def activiteit_verwijderen(activity_id: int, request: Request,
                           db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import delete_activity

    delete_activity(activity_id, db=db, admin=admin_user_by_email(db, email))
    # Verwijderen gebeurt vanuit de editor; die pagina bestaat daarna niet meer.
    return Response(status_code=204, headers={"HX-Redirect": "/admin/activiteiten"})


# ── Datums ─────────────────────────────────────────────────────────────────────

@router.post("/admin/activiteiten/{activity_id}/datums", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def datum_toevoegen(activity_id: int, request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui),
                    start_date: str = Form(...), end_date: str = Form(""),
                    start_time: str = Form(""), end_time: str = Form("")):
    from app.domains.activities.router import add_activity_date
    from app.schemas.activity import ActivityDateCreate

    add_activity_date(activity_id, ActivityDateCreate(
        start_date=start_date, end_date=end_date or None,
        start_time=start_time or None, end_time=end_time or None,
    ), db=db, admin=admin_user_by_email(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/datums/{date_id}",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def datum_bijwerken(activity_id: int, date_id: int, request: Request,
                    db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui),
                    start_date: str = Form(...), end_date: str = Form(""),
                    start_time: str = Form(""), end_time: str = Form("")):
    """Bestaande datum (incl. begin-/einduur) bewerken — v1.14-pariteit."""
    from app.domains.activities.router import update_activity_date
    from app.schemas.activity import ActivityDateUpdate

    update_activity_date(activity_id, date_id, ActivityDateUpdate(
        start_date=start_date, end_date=end_date or None,
        start_time=start_time or None, end_time=end_time or None,
    ), db=db, admin=admin_user_by_email(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/datums/{date_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def datum_verwijderen(activity_id: int, date_id: int, request: Request,
                      db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import delete_activity_date

    delete_activity_date(activity_id, date_id, db=db, admin=admin_user_by_email(db, email))
    return _detail_response(request, db, activity_id)


# ── Onderdelen ─────────────────────────────────────────────────────────────────

@router.post("/admin/activiteiten/{activity_id}/onderdelen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def onderdeel_toevoegen(activity_id: int, request: Request,
                        db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui),
                        name: str = Form(...), team_name_required: str = Form(""),
                        max_participants: str = Form(""),
                        external_register_url: str = Form(""),
                        external_registrations_url: str = Form(""),
                        info_url: str = Form("")):
    from app.domains.activities.router import add_component
    from app.schemas.activity import ComponentCreate

    add_component(activity_id, ComponentCreate(
        name=name.strip(), team_name_required=bool(team_name_required),
        max_participants=_opt_int(max_participants),
        external_register_url=_opt_str(external_register_url),
        external_registrations_url=_opt_str(external_registrations_url),
        info_url=_opt_str(info_url),
    ), db=db, admin=admin_user_by_email(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def onderdeel_bijwerken(activity_id: int, component_id: int, request: Request,
                        db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui),
                        name: str = Form(...), team_name_required: str = Form(""),
                        max_participants: str = Form(""),
                        external_register_url: str = Form(""),
                        external_registrations_url: str = Form(""),
                        info_url: str = Form("")):
    from app.domains.activities.router import update_component
    from app.schemas.activity import ComponentUpdate

    update_component(activity_id, component_id, ComponentUpdate(
        name=name.strip(), team_name_required=bool(team_name_required),
        max_participants=_opt_int(max_participants),
        external_register_url=_opt_str(external_register_url),
        external_registrations_url=_opt_str(external_registrations_url),
        info_url=_opt_str(info_url),
    ), db=db, admin=admin_user_by_email(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def onderdeel_verwijderen(activity_id: int, component_id: int, request: Request,
                          db: Session = Depends(get_db),
                          email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import delete_component

    delete_component(activity_id, component_id, db=db, admin=admin_user_by_email(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/verplaats",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def onderdeel_verplaatsen(activity_id: int, component_id: int, request: Request,
                          db: Session = Depends(get_db),
                          email: str = Depends(require_admin_ui),
                          richting: str = Form("omhoog")):
    """Onderdeel omhoog/omlaag herordenen (sort_order-wissel) — #451."""
    from app.domains.activities.api import Activity

    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if activity is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    _verplaats(db, list(activity.sub_registrations), component_id, richting)
    return _detail_response(request, db, activity_id)


# ── Producten ──────────────────────────────────────────────────────────────────

@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/producten",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def product_toevoegen(activity_id: int, component_id: int, request: Request,
                      db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui),
                      name: str = Form(...), price: str = Form("0"),
                      member_price: str = Form(""), afrekening: str = Form("betalend"),
                      max_participants: str = Form("")):
    from app.domains.activities.router import add_product
    from app.schemas.activity import ProductCreate

    bedrag = _decimal(price)
    add_product(activity_id, component_id, ProductCreate(
        name=name.strip(), price=bedrag,
        member_price=_decimal(member_price) if member_price.strip() else None,
        is_free=(afrekening == "gratis"),
        pay_on_site=(afrekening == "ter_plaatse"),
        max_participants=_opt_int(max_participants),
    ), db=db, admin=admin_user_by_email(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/producten/{product_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def product_verwijderen(activity_id: int, component_id: int, product_id: int,
                        request: Request, db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import delete_product

    delete_product(activity_id, component_id, product_id,
                   db=db, admin=admin_user_by_email(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/producten/{product_id}/verplaats",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def product_verplaatsen(activity_id: int, component_id: int, product_id: int,
                        request: Request, db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui),
                        richting: str = Form("omhoog")):
    """Product omhoog/omlaag herordenen binnen zijn onderdeel (sort_order) — #451."""
    from app.domains.activities.api import ActivitySubRegistration

    component = db.query(ActivitySubRegistration).filter(
        ActivitySubRegistration.id == component_id,
        ActivitySubRegistration.activity_id == activity_id).first()
    if component is None:
        raise HTTPException(status_code=404, detail=_("Onderdeel niet gevonden"))
    _verplaats(db, list(component.products), product_id, richting)
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/producten/{product_id}",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def product_bijwerken(activity_id: int, component_id: int, product_id: int,
                      request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui),
                      name: str = Form(...), price: str = Form("0"),
                      member_price: str = Form(""), afrekening: str = Form("betalend"),
                      max_participants: str = Form("")):
    """Product bijwerken incl. prijs/ledenprijs (#451)."""
    from app.domains.activities.router import update_product
    from app.schemas.activity import ProductUpdate

    bedrag = _decimal(price)
    update_product(activity_id, component_id, product_id, ProductUpdate(
        name=name.strip(), price=bedrag,
        member_price=_decimal(member_price) if member_price.strip() else None,
        is_free=(afrekening == "gratis"),
        pay_on_site=(afrekening == "ter_plaatse"),
        max_participants=_opt_int(max_participants),
    ), db=db, admin=admin_user_by_email(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/affiche", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def affiche_uploaden(activity_id: int, request: Request,
                           background_tasks: BackgroundTasks,
                           file: Optional[UploadFile] = File(None),
                           db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui)):
    """Affiche (poster) uploaden vanuit de activiteiten-admin (#451)."""
    from app.domains.media.api import upload_activity_poster

    if file is not None and file.filename:
        try:
            await upload_activity_poster(activity_id, background_tasks, file=file,
                                         db=db, _admin=admin_user_by_email(db, email))
        except HTTPException as exc:
            return _detail_response(request, db, activity_id,
                                    error=_upload_error(exc))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/affiche/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def affiche_verwijderen(activity_id: int, request: Request,
                        db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui)):
    """Bestaande affiche verwijderen (#623).

    Ontbrak volledig: je kon een verkeerd bestand alleen overschrijven, niet weghalen.
    Loopt via de bestaande media-facade, zodat het asset-record én zijn
    extracted_text in één keer weg zijn (#206) — geen tweede verwijderpad.
    """
    from app.domains.media.api import delete_activity_poster

    delete_activity_poster(activity_id, db=db, _admin=admin_user_by_email(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/info/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def onderdeel_info_verwijderen(activity_id: int, component_id: int, request: Request,
                               db: Session = Depends(get_db),
                               email: str = Depends(require_admin_ui)):
    """Info-bijlage van een onderdeel verwijderen (#623), via dezelfde media-facade."""
    from app.domains.media.api import delete_component_info

    delete_component_info(component_id, db=db, _admin=admin_user_by_email(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/info",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
async def onderdeel_info_uploaden(activity_id: int, component_id: int, request: Request,
                             background_tasks: BackgroundTasks,
                             file: Optional[UploadFile] = File(None),
                             db: Session = Depends(get_db),
                             email: str = Depends(require_admin_ui)):
    """Info-bijlage (afbeelding of PDF) per onderdeel uploaden (#451).

    Heette "reglement" tot #623; één woord voor één ding (§2.12)."""
    from app.domains.media.api import upload_component_info

    if file is not None and file.filename:
        try:
            await upload_component_info(component_id, background_tasks, file=file,
                                        db=db, _admin=admin_user_by_email(db, email))
        except HTTPException as exc:
            return _detail_response(request, db, activity_id,
                                    error=_upload_error(exc))
    return _detail_response(request, db, activity_id)


# ── Gedeelde inschrijving-detail (betalingen + activiteiten-admin, #455/#451) ──

def _detail_ctx(request: Request, db: Session, registration_id: int,
                *, edit_open: bool = False) -> dict | None:
    """Gedeelde context voor de inschrijving-detail/editor: de verrijkte
    inschrijving + de beschikbare producten van haar onderdeel (voor de
    'regel toevoegen'-keuze). Geeft None als de inschrijving niet bestaat."""
    from app.domains.activities.api import Activity, Registration
    from app.domains.activities.router import _enrich_registration

    reg = (db.query(Registration).execution_options(include_deleted=True)
           .filter(Registration.id == registration_id).first())
    if reg is None:
        return None
    activity = (db.query(Activity).execution_options(include_deleted=True)
                .filter(Activity.id == reg.activity_id).first())
    products = []
    if activity is not None and reg.component_id:
        component = next((c for c in activity.sub_registrations
                          if c.id == reg.component_id), None)
        if component is not None:
            products = [{"id": p.id, "name": p.name} for p in component.products]
    # Bedragen per regel + totaal (#613-4): zonder bedragen zie je in het paneel
    # niet wát je aan het wijzigen bent. Ze komen uit compute_registration_total —
    # de enige bron voor "wat kost deze inschrijving" (totals.py) — zodat het paneel
    # nooit een ander bedrag toont dan de betaalrecords. We lopen items en regels
    # parallel af en slaan items zonder product over, precies zoals die functie doet.
    from app.domains.activities.api import compute_registration_total

    totaal, regels = compute_registration_total(reg)
    bedragen, idx = {}, 0
    for item in (reg.items or []):
        if getattr(item, "product", None) is None:
            continue
        if idx < len(regels):
            bedragen[item.id] = regels[idx]
        idx += 1

    verrijkt = _enrich_registration(reg, activity)
    for regel in verrijkt["items"]:
        bedrag = bedragen.get(regel["id"])
        regel["unit_price"] = bedrag["unit_price"] if bedrag else None
        regel["line_total"] = bedrag["subtotal"] if bedrag else None

    return {
        "reg": verrijkt,
        "products": products,
        "totaal": totaal,
        "editable": reg.deleted_at is None,
        "edit_open": edit_open,
        "csrf_token": csrf_from_request(request),
    }


def _render_detail(request: Request, db: Session, registration_id: int,
                   *, edit_open: bool = False, ververs: bool = False,
                   error: str | None = None) -> HTMLResponse:
    """Rendert het detailfragment.

    ``edit_open`` houdt het paneel na een bewerking open (#613-3): het fragment
    vervangt zichzelf via outerHTML, dus zonder dit viel het terug in lees-modus en
    voelde het alsof er niets gebeurd was.

    ``ververs`` zet een ``HX-Trigger`` (#613-4/#617-3). De kaart erboven op
    /admin/betalingen staat buiten dit fragment en bleef op het oude bedrag staan —
    of toonde een nieuwe terugbetaling pas na F5 — terwijl de server al
    gereconcilieerd had. De betalingenlijst luistert op dat event.
    """
    ctx = _detail_ctx(request, db, registration_id, edit_open=edit_open)
    if ctx is None:
        return HTMLResponse("")
    ctx["error"] = error
    resp = templates.TemplateResponse(request, "_inschrijving_detail.html", ctx)
    if ververs:
        resp.headers["HX-Trigger"] = "betalingen-ververst"
    return resp


@router.get("/admin/inschrijvingen/{registration_id}", response_class=HTMLResponse)
def inschrijving_detail(registration_id: int, request: Request,
                        db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui)):
    """Detail/editor van één inschrijving (contact + producten + opmerking) als
    htmx-fragment. Herbruikbaar vanuit betalingen ('Toon inschrijvingsdetails')
    en de activiteiten-admin. Verrijking neemt soft-deleted mee (financieel feit);
    een soft-deleted inschrijving is niet bewerkbaar."""
    return _render_detail(request, db, registration_id)


def _reg_or_404(db: Session, registration_id: int):
    from app.domains.activities.api import Registration

    reg = db.query(Registration).filter(Registration.id == registration_id).first()
    if reg is None:
        raise HTTPException(status_code=404, detail=_("Inschrijving niet gevonden"))
    return reg


@router.post("/admin/inschrijvingen/{registration_id}/opmerking",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def inschrijving_opmerking(registration_id: int, request: Request,
                           db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui),
                           remarks: str = Form("")):
    from app.domains.activities.router import update_registration_remarks
    from app.schemas.activity import RegistrationContactUpdate

    reg = _reg_or_404(db, registration_id)
    update_registration_remarks(reg.activity_id, registration_id,
                                RegistrationContactUpdate(remarks=remarks),
                                db=db, admin=admin_user_by_email(db, email))
    return _render_detail(request, db, registration_id, edit_open=True, ververs=True)


@router.post("/admin/inschrijvingen/{registration_id}/opslaan",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
async def inschrijving_opslaan(registration_id: int, request: Request,
                               db: Session = Depends(get_db),
                               email: str = Depends(require_admin_ui)):
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
    from app.domains.activities.router import update_order_line, update_registration_remarks
    from app.schemas.activity import RegistrationContactUpdate, RegistrationItemUpdate

    reg = _reg_or_404(db, registration_id)
    admin = admin_user_by_email(db, email)
    form = await request.form()

    huidig = {item.id: item.quantity for item in (reg.items or [])}
    for key, value in form.items():
        # form.items() kan een UploadFile geven; alleen tekstvelden zijn aantallen.
        if not key.startswith("quantity_") or not isinstance(value, str):
            continue
        try:
            item_id, aantal = int(key.removeprefix("quantity_")), int(value)
        except ValueError:
            continue
        if item_id not in huidig or aantal == huidig[item_id]:
            continue
        update_order_line(reg.activity_id, registration_id, item_id,
                          RegistrationItemUpdate(quantity=aantal), db=db, admin=admin)

    # Contactgegevens meenemen in dezelfde "Opslaan" (#624). Enkel wat het formulier
    # meestuurt wordt gewijzigd; de route laat de rest ongemoeid.
    contact = {"remarks": str(form.get("remarks") or "")}
    for veld in ("contact_name", "contact_email", "phone"):
        if veld in form:
            contact[veld] = str(form.get(veld) or "")
    try:
        gegevens = RegistrationContactUpdate(**contact)
    except ValidationError:
        # Het schema wordt hier zelf gebouwd (geen request-body), dus Pydantic werpt
        # i.p.v. FastAPI een 422 te laten maken. Het paneel opnieuw renderen mét een
        # foutbanner: htmx swapt een 200, dus de gebruiker ziet de fout écht staan.
        return _render_detail(request, db, registration_id, edit_open=True,
                              error=_("Vul een geldig e-mailadres in."))
    update_registration_remarks(reg.activity_id, registration_id, gegevens,
                                db=db, admin=admin)
    return _render_detail(request, db, registration_id, edit_open=True, ververs=True)


@router.post("/admin/inschrijvingen/{registration_id}/regels",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def inschrijving_regel_toevoegen(registration_id: int, request: Request,
                                 db: Session = Depends(get_db),
                                 email: str = Depends(require_admin_ui),
                                 product_id: int = Form(...),
                                 quantity: int = Form(1)):
    from app.domains.activities.router import add_order_line
    from app.schemas.activity import RegistrationItemCreate

    reg = _reg_or_404(db, registration_id)
    add_order_line(reg.activity_id, registration_id,
                   RegistrationItemCreate(product_id=product_id, quantity=quantity),
                   db=db, admin=admin_user_by_email(db, email))
    return _render_detail(request, db, registration_id, edit_open=True, ververs=True)


@router.post("/admin/inschrijvingen/{registration_id}/regels/{item_id}",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def inschrijving_regel_bijwerken(registration_id: int, item_id: int, request: Request,
                                 db: Session = Depends(get_db),
                                 email: str = Depends(require_admin_ui),
                                 quantity: int = Form(...)):
    from app.domains.activities.router import update_order_line
    from app.schemas.activity import RegistrationItemUpdate

    reg = _reg_or_404(db, registration_id)
    update_order_line(reg.activity_id, registration_id, item_id,
                      RegistrationItemUpdate(quantity=quantity),
                      db=db, admin=admin_user_by_email(db, email))
    return _render_detail(request, db, registration_id, edit_open=True, ververs=True)


@router.post("/admin/inschrijvingen/{registration_id}/regels/{item_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def inschrijving_regel_verwijderen(registration_id: int, item_id: int, request: Request,
                                   db: Session = Depends(get_db),
                                   email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import delete_order_line

    reg = _reg_or_404(db, registration_id)
    delete_order_line(reg.activity_id, registration_id, item_id,
                      db=db, admin=admin_user_by_email(db, email))
    return _render_detail(request, db, registration_id, edit_open=True, ververs=True)


# ── Inschrijvingen + export ────────────────────────────────────────────────────

@router.get("/admin/activiteiten/{activity_id}/inschrijvingen", response_class=HTMLResponse)
def inschrijvingen_lijst(activity_id: int, request: Request,
                         db: Session = Depends(get_db),
                         email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import get_registrations

    regs = get_registrations(activity_id, db=db, admin=admin_user_by_email(db, email))
    return templates.TemplateResponse(request, "_aa_inschrijvingen.html", {
        "registrations": regs, "activity_id": activity_id,
        "csrf_token": csrf_from_request(request)})


@router.post("/admin/activiteiten/{activity_id}/inschrijvingen/{registration_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def inschrijving_verwijderen(activity_id: int, registration_id: int, request: Request,
                             db: Session = Depends(get_db),
                             email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import delete_registration, get_registrations

    delete_registration(activity_id, registration_id, db=db,
                        admin=admin_user_by_email(db, email))
    regs = get_registrations(activity_id, db=db, admin=admin_user_by_email(db, email))
    return templates.TemplateResponse(request, "_aa_inschrijvingen.html", {
        "registrations": regs, "activity_id": activity_id,
        "csrf_token": csrf_from_request(request)})


@router.get("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/export")
def onderdeel_export(activity_id: int, component_id: int, request: Request,
                     db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui)) -> Response:
    from app.domains.activities.router import export_component_ods

    return export_component_ods(activity_id, component_id, db=db,
                                admin=admin_user_by_email(db, email))
