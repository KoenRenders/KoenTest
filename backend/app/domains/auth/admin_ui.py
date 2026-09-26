"""Server-rendered gebruikersbeheer (React-exit 405-d, #405 — §21).

Backoffice-accounts + rollen: lijst, aanmaken, bijwerken (actief/rollen),
verwijderen. Hergebruikt de users-routerfuncties als servicelaag.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    Role,
    admin_user_by_email, csrf_from_request, get_user_roles,
    SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf,
)
from app.ui import admin_nav, is_fragment_request, templates
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
    # OPERATOR telt overal mee (rollen-matrix #544: gebruikersbeheer =
    # ADMIN/OPERATOR) — vóór 16 sep verstopte deze check dat, wat op het
    # platform meteen opviel: een OPERATOR heeft daar geen eigen ADMIN-rij.
    if not ({"ADMIN", "OPERATOR"} & get_user_roles(db, email)):
        raise HTTPException(
            status_code=403,
            detail=_("Alleen een beheerder (ADMIN) mag gebruikers en rollen beheren."))


def _werkruimtes(db) -> list:
    """(id, naam) van elke werkruimte — platform eerst, dan de afdelingen;
    dezelfde bron als /admin/tenants."""
    from app.domains.mdm.api import list_manageable_tenants

    return [(org.id, org.name) for org in list_manageable_tenants(db)]


def _platform_rollen_uit(form, db) -> tuple:
    """({tenant_id: [codes]}, operator?) uit de platform-rolvelden. Alleen
    bekende werkruimtes worden gelezen — een verzonnen `rollen_999` bestaat
    niet als veld en wordt dus nooit een rij."""
    per_werkruimte = {wid: [str(c) for c in form.getlist(f"rollen_{wid}")]
                      for wid, _naam in _werkruimtes(db)}
    return per_werkruimte, bool(form.get("operator"))


def _filters_uit(form) -> dict:
    """De actieve filters die een kaart als verborgen velden meestuurt, zodat een
    opslaan of verwijderen de lijst niet terugzet naar 'alles'."""
    return {"q": str(form.get("q") or ""), "rol": str(form.get("rol") or ""),
            "actief": str(form.get("actief") or "")}


def _lijst_ctx(request: Request, db: Session, q: str = "", rol: str = "",
               actief: str = "", viewer_email: str = "") -> dict:
    """Records-lijst (C1, #589): zoeken op e-mail + filter op rol en actief-status.

    Backoffice-accounts zijn er tientallen, geen duizenden — filteren gebeurt op
    de opgehaalde lijst, in dezelfde stijl als de andere lijstschermen.

    Sinds #963 werkruimte-bewust: getoond en gefilterd worden de rollen in de
    ACTIEVE werkruimte (plus de platformbrede NULL-rijen), en het
    OPERATOR-vinkje bestaat alleen voor wie zelf OPERATOR is — een ADMIN kent
    rollen toe binnen zijn werkruimte, niet daarboven.
    """
    from app.domains.auth.api import list_assignable_roles, role_options
    from app.domains.auth.users import is_platform_workspace, list_users
    from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id

    actieve_werkruimte = current_tenant_id.get() or DEFAULT_TENANT_ID
    op_platform = is_platform_workspace(db)
    werkruimtes = _werkruimtes(db) if op_platform else []
    users = list_users(db=db, _admin=None)
    # Aanscherping 16 sep: op het platform beheert de kaart álle werkruimtes
    # (zo maakt een OPERATOR de eerste gebruikers van een nieuwe tenant aan);
    # in een gewone werkruimte alleen de eigen rijen.
    rollen_matrix: dict[int, dict[int, set]] = {u.id: {} for u in users}
    operator_van = {u.id: False for u in users}
    for u in users:
        for r in u.roles:
            if r.tenant_id is None:
                if r.role_code is Role.OPERATOR:
                    operator_van[u.id] = True
            else:
                rollen_matrix[u.id].setdefault(r.tenant_id, set()).add(
                    r.role_code.value)
    rollen_hier = {u.id: (set().union(*rollen_matrix[u.id].values())
                          if op_platform and rollen_matrix[u.id]
                          else rollen_matrix[u.id].get(actieve_werkruimte, set()))
                   | ({"OPERATOR"} if operator_van[u.id] else set())
                   for u in users}
    term = q.strip().lower()
    if term:
        users = [u for u in users if term in (u.email or "").lower()]
    if rol:
        users = [u for u in users if rol in rollen_hier[u.id]]
    if actief == "ja":
        users = [u for u in users if u.is_active]
    elif actief == "nee":
        users = [u for u in users if not u.is_active]

    # Welke rollen toekenbaar zijn (en waarom USER/MEMBER niet) staat in de
    # service — het scherm hoeft die regel niet te kennen (#635 regel 2).
    # OPERATOR zit hier nooit tussen: die is platformbreed en heeft op het
    # platform zijn eigen vinkje (aanscherping 16 sep — nergens anders).
    is_operator = "OPERATOR" in get_user_roles(db, viewer_email)
    rollen = [r for r in list_assignable_roles(db) if r.code != "OPERATOR"]
    return {"users": users, "q": q, "rol": rol, "actief": actief,
            "gefilterd": bool(term or rol or actief),
            "rollen_hier": rollen_hier, "rollen_matrix": rollen_matrix,
            "operator_van": operator_van,
            "op_platform": op_platform, "werkruimtes": werkruimtes,
            "toon_operator": op_platform and is_operator,
            # Filteropties per request: _() volgt de taal van de tenant.
            # Sinds #1079 één keuzelijst i.p.v. knoppen: het aantal rollen is
            # data-gedreven en groeit mee met de codetabel, dus een rij knoppen
            # groeit mee met de breedte van het scherm.
            "rol_options": [("", _("Alle rollen"))] + role_options(rollen),
            "actief_options": [("", _("Alle accounts")), ("ja", _("Actief")),
                               ("nee", _("Inactief"))],
            "role_codes": rollen,
            "csrf_token": csrf_from_request(request)}


def _lijst_response(request: Request, db: Session, error: str | None = None,
                    q: str = "", rol: str = "", actief: str = "",
                    viewer_email: str = ""):
    """Enkel de kaarten (C1, #589): kop, knop en filterbalk staan op de pagina."""
    ctx = _lijst_ctx(request, db, q, rol, actief, viewer_email)
    ctx["error"] = error
    return templates.TemplateResponse(request, "_gu_lijst.html", ctx)


@router.get("/admin/gebruikers", response_class=HTMLResponse)
def admin_gebruikers(request: Request, db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui),
                     q: str = "", rol: str = "", actief: str = ""):
    _require_admin(db, email)
    if is_fragment_request(request):
        return _lijst_response(request, db, q=q, rol=rol, actief=actief,
                               viewer_email=email)
    return templates.TemplateResponse(request, "admin_gebruikers.html", {
        "nav_items": NAV, "error": None,
        **_lijst_ctx(request, db, q, rol, actief, viewer_email=email)})


@router.get("/admin/gebruikers/nieuw", response_class=HTMLResponse)
def gebruiker_nieuw(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui)):
    """Aanmaken als volledige pagina (#627, §2.8) i.p.v. een modal.

    Het scherm draagt de lijstfilters als verborgen velden mee, zodat je na het
    aanmaken terugkeert in de lijst zoals je hem had staan. Bij een verse GET zijn
    die leeg — maar wel meegegeven (#643): de route belooft wat de template
    vraagt. Voorheen leunde dit op Jinja's stille lege string, waardoor ook
    `role_codes` er onopgemerkt niet was en de rolvinkjes zwijgend ontbraken.
    """
    return templates.TemplateResponse(request, "admin_gebruiker_nieuw.html", {
        "nav_items": NAV,
        "csrf_token": csrf_from_request(request),
        "error": None,
        **_lijst_ctx(request, db, viewer_email=email),
    })


@router.post("/admin/gebruikers", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def gebruiker_aanmaken(request: Request, db: Session = Depends(get_db),
                             email: str = Depends(require_admin_ui)):
    from app.domains.auth.users import (
        UserCreate, is_platform_workspace, create_user, set_roles_for_workspaces,
    )
    from app.domains.auth.api import get_user_roles as _rollen_van

    _require_admin(db, email)
    form = await request.form()
    filters = _filters_uit(form)
    nieuw_email = str(form.get("email") or "").strip().lower()
    if not nieuw_email:
        return _lijst_response(request, db, "E-mailadres is verplicht.", **filters)
    try:
        if is_platform_workspace(db):
            # Aanscherping 16 sep: vanaf het platform krijgt een nieuwe
            # gebruiker zijn rollen per werkruimte — zo ontstaan de eerste
            # accounts van een nieuwe tenant.
            per_werkruimte, operator = _platform_rollen_uit(form, db)
            user = create_user(UserCreate(email=nieuw_email, role_codes=[]),
                               db=db, _admin=admin_user_by_email(db, email))
            set_roles_for_workspaces(db, user.id, per_werkruimte, operator,
                                     _rollen_van(db, email))
        else:
            create_user(UserCreate(email=nieuw_email,
                                   role_codes=[str(c) for c in form.getlist("role_codes")]),
                        db=db, _admin=admin_user_by_email(db, email))
    except HTTPException as exc:
        # Op het aanmaakscherm blijven mét de fout (#627).
        ctx = _lijst_ctx(request, db, **filters, viewer_email=email)
        ctx["nav_items"] = NAV
        ctx["error"] = str(exc.detail)
        return templates.TemplateResponse(request, "admin_gebruiker_nieuw.html", ctx)
    # Een gebruiker is met één handeling compleet, dus terug naar de lijst (#627).
    return Response(status_code=204, headers={"HX-Redirect": "/admin/gebruikers"})


@router.post("/admin/gebruikers/{user_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def gebruiker_bijwerken(user_id: int, request: Request,
                              db: Session = Depends(get_db),
                              email: str = Depends(require_admin_ui)):
    from app.domains.auth.users import (
        UserUpdate, is_platform_workspace, set_roles_for_workspaces, update_user,
    )
    from app.domains.auth.api import get_user_roles as _rollen_van

    _require_admin(db, email)
    form = await request.form()
    filters = _filters_uit(form)
    try:
        _email_raw = form.get("email")
        _email = _email_raw.strip() if isinstance(_email_raw, str) else ""
        if is_platform_workspace(db):
            per_werkruimte, operator = _platform_rollen_uit(form, db)
            update_user(user_id, UserUpdate(
                email=_email or None,
                is_active=bool(form.get("is_active")),
                role_codes=None,
            ), db=db, _admin=admin_user_by_email(db, email))
            set_roles_for_workspaces(db, user_id, per_werkruimte, operator,
                                     _rollen_van(db, email))
        else:
            update_user(user_id, UserUpdate(
                email=_email or None,
                is_active=bool(form.get("is_active")),
                role_codes=[str(c) for c in form.getlist("role_codes")],
            ), db=db, _admin=admin_user_by_email(db, email))
    except HTTPException as exc:
        return _lijst_response(request, db, str(exc.detail), **filters,
                               viewer_email=email)
    return _lijst_response(request, db, **filters, viewer_email=email)


@router.post("/admin/gebruikers/{user_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def gebruiker_verwijderen(user_id: int, request: Request,
                                db: Session = Depends(get_db),
                                email: str = Depends(require_admin_ui)):
    from app.domains.auth.users import delete_user

    _require_admin(db, email)
    # async om de meegestuurde filters (hx-vals) te kunnen lezen: na het
    # verwijderen hoort de lijst nog steeds gefilterd te zijn.
    filters = _filters_uit(await request.form())
    try:
        delete_user(user_id, db=db, current_admin=admin_user_by_email(db, email))
    except HTTPException as exc:
        return _lijst_response(request, db, str(exc.detail), **filters,
                               viewer_email=email)
    return _lijst_response(request, db, **filters, viewer_email=email)
