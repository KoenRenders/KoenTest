"""Server-rendered admin-activiteitenbeheer (fase 4a-4, #402 — §21).

Volledige CRUD op activiteiten, datums, onderdelen en producten, plus de
inschrijvingenlijst en de .ods-export per onderdeel. Hergebruikt de bestaande
router-functies als servicelaag; sessie-auth + CSRF zoals de andere schermen.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    SESSION_COOKIE, User, csrf_token_for, require_admin_ui, require_csrf,
)
from app.ui import admin_nav, templates
from app.i18n import _

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/activiteiten")


def _csrf(request: Request) -> str:
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


def _admin_user(db: Session, email: str) -> User:
    user = (db.query(User)
            .filter(func.lower(User.email) == email.lower(), User.is_active == True)
            .first())
    if user is None:
        raise HTTPException(status_code=401, detail=_("Niet aangemeld"))
    return user


def _decimal(value: str, default: str = "0") -> Decimal:
    try:
        return Decimal((value or default).replace(",", "."))
    except InvalidOperation:
        raise HTTPException(status_code=400, detail=_("Ongeldig bedrag."))


def _opt_int(value: str) -> Optional[int]:
    value = (value or "").strip()
    return int(value) if value else None


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
        "a": activiteit, "csrf_token": _csrf(request)})


@router.get("/admin/activiteiten", response_class=HTMLResponse)
def admin_activiteiten(request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "admin_activiteiten.html", {
        "nav_items": NAV, "csrf_token": _csrf(request), **_lijst_ctx(db)})


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
    ), db=db, admin=_admin_user(db, email))
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
    ), db=db, admin=_admin_user(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def activiteit_verwijderen(activity_id: int, request: Request,
                           db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import delete_activity

    delete_activity(activity_id, db=db, admin=_admin_user(db, email))
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
    ), db=db, admin=_admin_user(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/datums/{date_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def datum_verwijderen(activity_id: int, date_id: int, request: Request,
                      db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import delete_activity_date

    delete_activity_date(activity_id, date_id, db=db, admin=_admin_user(db, email))
    return _detail_response(request, db, activity_id)


# ── Onderdelen ─────────────────────────────────────────────────────────────────

@router.post("/admin/activiteiten/{activity_id}/onderdelen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def onderdeel_toevoegen(activity_id: int, request: Request,
                        db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui),
                        name: str = Form(...), team_name_required: str = Form(""),
                        max_participants: str = Form("")):
    from app.domains.activities.router import add_component
    from app.schemas.activity import ComponentCreate

    add_component(activity_id, ComponentCreate(
        name=name.strip(), team_name_required=bool(team_name_required),
        max_participants=_opt_int(max_participants),
    ), db=db, admin=_admin_user(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def onderdeel_bijwerken(activity_id: int, component_id: int, request: Request,
                        db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui),
                        name: str = Form(...), team_name_required: str = Form(""),
                        max_participants: str = Form("")):
    from app.domains.activities.router import update_component
    from app.schemas.activity import ComponentUpdate

    update_component(activity_id, component_id, ComponentUpdate(
        name=name.strip(), team_name_required=bool(team_name_required),
        max_participants=_opt_int(max_participants),
    ), db=db, admin=_admin_user(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def onderdeel_verwijderen(activity_id: int, component_id: int, request: Request,
                          db: Session = Depends(get_db),
                          email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import delete_component

    delete_component(activity_id, component_id, db=db, admin=_admin_user(db, email))
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
    ), db=db, admin=_admin_user(db, email))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/producten/{product_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def product_verwijderen(activity_id: int, component_id: int, product_id: int,
                        request: Request, db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import delete_product

    delete_product(activity_id, component_id, product_id,
                   db=db, admin=_admin_user(db, email))
    return _detail_response(request, db, activity_id)


# ── Inschrijvingen + export ────────────────────────────────────────────────────

@router.get("/admin/activiteiten/{activity_id}/inschrijvingen", response_class=HTMLResponse)
def inschrijvingen_lijst(activity_id: int, request: Request,
                         db: Session = Depends(get_db),
                         email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import get_registrations

    regs = get_registrations(activity_id, db=db, admin=_admin_user(db, email))
    return templates.TemplateResponse(request, "_aa_inschrijvingen.html", {
        "registrations": regs, "activity_id": activity_id,
        "csrf_token": _csrf(request)})


@router.post("/admin/activiteiten/{activity_id}/inschrijvingen/{registration_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def inschrijving_verwijderen(activity_id: int, registration_id: int, request: Request,
                             db: Session = Depends(get_db),
                             email: str = Depends(require_admin_ui)):
    from app.domains.activities.router import delete_registration, get_registrations

    delete_registration(activity_id, registration_id, db=db,
                        admin=_admin_user(db, email))
    regs = get_registrations(activity_id, db=db, admin=_admin_user(db, email))
    return templates.TemplateResponse(request, "_aa_inschrijvingen.html", {
        "registrations": regs, "activity_id": activity_id,
        "csrf_token": _csrf(request)})


@router.get("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/export")
def onderdeel_export(activity_id: int, component_id: int, request: Request,
                     db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui)) -> Response:
    from app.domains.activities.router import export_component_ods

    return export_component_ods(activity_id, component_id, db=db,
                                admin=_admin_user(db, email))
