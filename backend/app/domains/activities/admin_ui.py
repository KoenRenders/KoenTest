"""Server-rendered admin-activiteitenbeheer (fase 4a-4, #402 — §21).

Volledige CRUD op activiteiten, datums, onderdelen en producten, plus de
inschrijvingenlijst en de .ods-export per onderdeel. Hergebruikt de bestaande
router-functies als servicelaag; sessie-auth + CSRF zoals de andere schermen.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
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


def _lijst_ctx(db: Session) -> dict:
    from app.domains.activities.router import list_activities

    return {"activities": list_activities(scope="all", db=db)}


def _detail_response(request: Request, db: Session, activity_id: int):
    from app.domains.activities.router import list_activities

    activiteit = next((a for a in list_activities(scope="all", db=db)
                       if a.id == activity_id), None)
    if activiteit is None:
        return HTMLResponse('<div id="aa-detail" hx-swap-oob="true"></div>')
    return templates.TemplateResponse(request, "_aa_detail.html", {
        "a": activiteit, "csrf_token": csrf_from_request(request)})


@router.get("/admin/activiteiten", response_class=HTMLResponse)
def admin_activiteiten(request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "admin_activiteiten.html", {
        "nav_items": NAV, "csrf_token": csrf_from_request(request), **_lijst_ctx(db)})


@router.get("/admin/activiteiten/lijst", response_class=HTMLResponse)
def admin_activiteiten_lijst(request: Request, db: Session = Depends(get_db),
                             email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "_aa_lijst.html", _lijst_ctx(db))


@router.get("/admin/activiteiten/{activity_id}", response_class=HTMLResponse)
def admin_activiteit_detail(activity_id: int, request: Request,
                            db: Session = Depends(get_db),
                            email: str = Depends(require_admin_ui)):
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def activiteit_aanmaken(request: Request, db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui),
                        name: str = Form(""), start_date: str = Form(""),
                        location: str = Form(""), members_only: str = Form("")):
    from app.domains.activities.router import create_activity
    from app.schemas.activity import ActivityCreate, ActivityDateCreate

    if not name.strip() or not start_date:
        raise HTTPException(status_code=400, detail=_("Naam en eerste datum zijn verplicht."))
    create_activity(ActivityCreate(
        name=name.strip(), location=location.strip() or None,
        members_only=bool(members_only),
        dates=[ActivityDateCreate(start_date=start_date)],
    ), db=db, admin=admin_user_by_email(db, email))
    return templates.TemplateResponse(request, "_aa_lijst.html", _lijst_ctx(db))


@router.post("/admin/activiteiten/{activity_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def activiteit_bijwerken(activity_id: int, request: Request,
                         db: Session = Depends(get_db),
                         email: str = Depends(require_admin_ui),
                         name: str = Form(""), location: str = Form(""),
                         members_only: str = Form(""), is_cancelled: str = Form("")):
    from app.domains.activities.router import update_activity
    from app.schemas.activity import ActivityUpdate

    update_activity(activity_id, ActivityUpdate(
        name=name.strip() or None, location=location.strip() or None,
        members_only=bool(members_only), is_cancelled=bool(is_cancelled),
    ), db=db, admin=admin_user_by_email(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def activiteit_verwijderen(activity_id: int, request: Request,
                           db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import delete_activity

    delete_activity(activity_id, db=db, admin=admin_user_by_email(db, email))
    return templates.TemplateResponse(request, "_aa_lijst.html", _lijst_ctx(db))


# ── Datums ─────────────────────────────────────────────────────────────────────

@router.post("/admin/activiteiten/{activity_id}/datums", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def datum_toevoegen(activity_id: int, request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui),
                    start_date: str = Form(...), end_date: str = Form("")):
    from app.domains.activities.router import add_activity_date
    from app.schemas.activity import ActivityDateCreate

    add_activity_date(activity_id, ActivityDateCreate(
        start_date=start_date, end_date=end_date or None,
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


# ── Producten ──────────────────────────────────────────────────────────────────

@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/producten",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def product_toevoegen(activity_id: int, component_id: int, request: Request,
                      db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui),
                      name: str = Form(...), price: str = Form("0"),
                      member_price: str = Form(""), pay_on_site: str = Form(""),
                      max_participants: str = Form("")):
    from app.domains.activities.router import add_product
    from app.schemas.activity import ProductCreate

    bedrag = _decimal(price)
    add_product(activity_id, component_id, ProductCreate(
        name=name.strip(), price=bedrag,
        member_price=_decimal(member_price) if member_price.strip() else None,
        is_free=(bedrag == 0 and not bool(pay_on_site)),
        pay_on_site=bool(pay_on_site),
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


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/producten/{product_id}",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def product_bijwerken(activity_id: int, component_id: int, product_id: int,
                      request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui),
                      name: str = Form(...), price: str = Form("0"),
                      member_price: str = Form(""), pay_on_site: str = Form(""),
                      max_participants: str = Form("")):
    """Product bijwerken incl. prijs/ledenprijs (#451)."""
    from app.domains.activities.router import update_product
    from app.schemas.activity import ProductUpdate

    bedrag = _decimal(price)
    update_product(activity_id, component_id, product_id, ProductUpdate(
        name=name.strip(), price=bedrag,
        member_price=_decimal(member_price) if member_price.strip() else None,
        is_free=(bedrag == 0 and not bool(pay_on_site)),
        pay_on_site=bool(pay_on_site),
        max_participants=_opt_int(max_participants),
    ), db=db, admin=admin_user_by_email(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/affiche", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def affiche_uploaden(activity_id: int, request: Request,
                           background_tasks: BackgroundTasks,
                           db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui)):
    """Affiche (poster) uploaden vanuit de activiteiten-admin (#451)."""
    from app.domains.media.router import upload_activity_poster

    form = await request.form()
    bestand = form.get("file")
    if bestand is not None and getattr(bestand, "filename", ""):
        await upload_activity_poster(activity_id, background_tasks, file=bestand,
                                     db=db, _admin=admin_user_by_email(db, email))
    return _detail_response(request, db, activity_id)


# ── Gedeelde inschrijving-detail (betalingen + activiteiten-admin, #455/#451) ──

def _detail_ctx(request: Request, db: Session, registration_id: int) -> dict | None:
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
    return {
        "reg": _enrich_registration(reg, activity),
        "products": products,
        "editable": reg.deleted_at is None,
        "csrf_token": csrf_from_request(request),
    }


def _render_detail(request: Request, db: Session, registration_id: int) -> HTMLResponse:
    ctx = _detail_ctx(request, db, registration_id)
    if ctx is None:
        return HTMLResponse("")
    return templates.TemplateResponse(request, "_inschrijving_detail.html", ctx)


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
    from app.schemas.activity import RegistrationRemarksUpdate

    reg = _reg_or_404(db, registration_id)
    update_registration_remarks(reg.activity_id, registration_id,
                                RegistrationRemarksUpdate(remarks=remarks),
                                db=db, admin=admin_user_by_email(db, email))
    return _render_detail(request, db, registration_id)


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
    return _render_detail(request, db, registration_id)


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
    return _render_detail(request, db, registration_id)


@router.post("/admin/inschrijvingen/{registration_id}/regels/{item_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def inschrijving_regel_verwijderen(registration_id: int, item_id: int, request: Request,
                                   db: Session = Depends(get_db),
                                   email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import delete_order_line

    reg = _reg_or_404(db, registration_id)
    delete_order_line(reg.activity_id, registration_id, item_id,
                      db=db, admin=admin_user_by_email(db, email))
    return _render_detail(request, db, registration_id)


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
