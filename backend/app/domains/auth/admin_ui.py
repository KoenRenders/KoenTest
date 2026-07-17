"""Server-rendered gebruikersbeheer (React-exit 405-d, #405 — §21).

Backoffice-accounts + rollen: lijst, aanmaken, bijwerken (actief/rollen),
verwijderen. Hergebruikt de users-routerfuncties als servicelaag.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    admin_user_by_email, csrf_from_request, get_user_roles,
    SESSION_COOKIE, User, csrf_token_for, require_admin_ui, require_csrf,
)
from app.ui import admin_nav, templates
from app.i18n import _

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/gebruikers")


def _require_admin(db: Session, email: str) -> None:
    """Gebruikersbeheer is ADMIN-only (#530). `require_admin_ui` laat de bredere
    backoffice-set (ADMIN/FINANCE/ACCOUNT_ADMIN/OPERATOR) toe zodat die rollen de
    admin-schil kunnen gebruiken — maar accounts/rollen beheren (incl. de ADMIN-rol
    toekennen) mag enkel een ADMIN, anders escaleert bv. een FINANCE-account zichzelf
    naar ADMIN via dit scherm. De JSON-API dwingt dit al af via get_current_admin;
    deze check sluit het server-rendered UI-pad dat die dependency omzeilt."""
    if "ADMIN" not in get_user_roles(db, email):
        raise HTTPException(
            status_code=403,
            detail=_("Alleen een beheerder (ADMIN) mag gebruikers en rollen beheren."))


def _lijst_ctx(request: Request, db: Session) -> dict:
    from app.domains.auth.users import list_users
    from app.domains.auth.models import RoleCode

    return {"users": list_users(db=db, _admin=None),
            # USER én MEMBER zijn dode rollen in gebruikersbeheer (#458/#521): geen
            # enkele autorisatie hangt eraan (backoffice draait op ADMIN/FINANCE/
            # OPERATOR; lidmaatschap is data-gedreven via Membership). Uit de
            # keuzelijst filteren voorkomt zinloze, verwarrende vinkjes.
            "role_codes": db.query(RoleCode).filter(RoleCode.code.notin_(["USER", "MEMBER"]))
                            .order_by(RoleCode.code).all(),
            "csrf_token": csrf_from_request(request)}


def _lijst_response(request: Request, db: Session, error: str | None = None):
    ctx = _lijst_ctx(request, db)
    ctx["error"] = error
    return templates.TemplateResponse(request, "_gu_lijst.html", ctx)


@router.get("/admin/gebruikers", response_class=HTMLResponse)
def admin_gebruikers(request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui)):
    _require_admin(db, email)
    return templates.TemplateResponse(request, "admin_gebruikers.html", {
        "nav_items": NAV, "error": None, **_lijst_ctx(request, db)})


@router.post("/admin/gebruikers", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def gebruiker_aanmaken(request: Request, db: Session = Depends(get_db),
                             email: str = Depends(require_admin_ui)):
    from app.domains.auth.users import UserCreate, create_user

    _require_admin(db, email)
    form = await request.form()
    nieuw_email = str(form.get("email") or "").strip().lower()
    if not nieuw_email:
        return _lijst_response(request, db, "E-mailadres is verplicht.")
    try:
        create_user(UserCreate(email=nieuw_email,
                               role_codes=[str(c) for c in form.getlist("role_codes")]),
                    db=db, _admin=None)
    except HTTPException as exc:
        return _lijst_response(request, db, str(exc.detail))
    return _lijst_response(request, db)


@router.post("/admin/gebruikers/{user_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def gebruiker_bijwerken(user_id: int, request: Request,
                              db: Session = Depends(get_db),
                              email: str = Depends(require_admin_ui)):
    from app.domains.auth.users import UserUpdate, update_user

    _require_admin(db, email)
    form = await request.form()
    try:
        _email_raw = form.get("email")
        _email = _email_raw.strip() if isinstance(_email_raw, str) else ""
        update_user(user_id, UserUpdate(
            email=_email or None,
            is_active=bool(form.get("is_active")),
            role_codes=[str(c) for c in form.getlist("role_codes")],
        ), db=db, _admin=None)
    except HTTPException as exc:
        return _lijst_response(request, db, str(exc.detail))
    return _lijst_response(request, db)


@router.post("/admin/gebruikers/{user_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def gebruiker_verwijderen(user_id: int, request: Request,
                          db: Session = Depends(get_db),
                          email: str = Depends(require_admin_ui)):
    from app.domains.auth.users import delete_user

    _require_admin(db, email)
    try:
        delete_user(user_id, db=db, current_admin=admin_user_by_email(db, email))
    except HTTPException as exc:
        return _lijst_response(request, db, str(exc.detail))
    return _lijst_response(request, db)
