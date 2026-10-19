"""Server-rendered gebruikersbeheer (React-exit 405-d, #405 — §21).

Backoffice-accounts + rollen. Sinds #2114 (CR-11 fase 5, spoor 2) is een gebruiker
een eigen recordpagina, zoals Organisatie en Tenant: de lijst is een `list_page` op
de tabel van de kit, een rij opent het record, en het record leest eerst
(`?bewerken=1` is de bewerkmodus met ÉÉN "Opslaan"). Het inline bewerken per rij
is weg. Wie een gebruiker mag zien en wijzigen, en welke rollen hij mag toekennen,
is ongewijzigd (`docs/rollen-en-rechten.md`): de services zijn dezelfde, alleen het
scherm eromheen is nieuw.

Hergebruikt de users-routerfuncties als servicelaag.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    Right,
    Role,
    admin_user_by_email,
    csrf_from_request,
    get_user_roles,
    may,
    require_csrf,
    require_platform_right,
    require_right,
)
from app.i18n import _
from app.kernel.refusals import FieldError
from app.ui import (
    PER_PAGE_DEFAULT,
    PER_PAGE_OPTIONS,
    admin_nav,
    filterparams,
    is_fragment_request,
    list_return,
    per_page_from,
    record_frame,
    refusal_response,
    templates,
)

router = APIRouter(include_in_schema=False)

NAV = "/admin/gebruikers"
RECORD_MESSAGE = "#gu-melding"

SORTS = ("email", "-email")
SORT_DEFAULT = SORTS[0]


def _werkruimtes(db) -> list:
    """(id, naam) van elke werkruimte — platform eerst, dan de afdelingen;
    dezelfde bron als /admin/tenants."""
    from app.domains.mdm.api import list_manageable_tenants

    return [(org.id, org.name) for org in list_manageable_tenants(db)]


def _platform_rollen_uit(form, db) -> tuple:
    """({tenant_id: [codes]}, operator?) uit de platform-rolvelden. Alleen
    bekende werkruimtes worden gelezen — een verzonnen `rollen_999` bestaat
    niet als veld en wordt dus nooit een rij."""
    per_werkruimte = {
        wid: [str(c) for c in form.getlist(f"rollen_{wid}")] for wid, _naam in _werkruimtes(db)
    }
    return per_werkruimte, bool(form.get("operator"))


def _scope(db: Session, viewer_email: str) -> dict[str, Any]:
    """What every screen of Gebruikers needs to know about the workspace and the one
    who looks: where the roles are kept, which can be given, and what the viewer may
    see of the platform.

    Sinds #963 werkruimte-bewust: de rollen in de ACTIEVE werkruimte (plus de
    platformbrede NULL-rijen), en het OPERATOR-vinkje bestaat alleen voor wie zelf
    OPERATOR is — een ADMIN kent rollen toe binnen zijn werkruimte, niet daarboven.
    OPERATOR zit nooit tussen de toekenbare rollen: die is platformbreed en heeft op
    het platform zijn eigen vinkje (aanscherping 16 sep — nergens anders).
    """
    from app.domains.auth.api import list_assignable_roles, role_options
    from app.domains.auth.users import is_platform_workspace
    from app.kernel.codes import code_label

    platform_wide = Role.OPERATOR.value
    op_platform = is_platform_workspace(db)
    is_operator = platform_wide in get_user_roles(db, viewer_email)
    pairs = role_options([r for r in list_assignable_roles(db) if r.code != platform_wide])
    return {
        "op_platform": op_platform,
        "werkruimtes": _werkruimtes(db) if op_platform else [],
        "toon_operator": op_platform and is_operator,
        # #1500: the way to the overview of every workspace, for an operator;
        # #1535: in the platform workspace only, where the overview lives.
        "toon_overzicht": is_operator and op_platform,
        # CR-24: a role is shown by its label from the code list, never by its code.
        "role_pairs": pairs,
        "role_labels": dict(pairs),
        "operator_label": code_label("role", platform_wide),
    }


def _accounts(db: Session, scope: dict[str, Any]) -> list:
    """The accounts this workspace's Gebruikers shows (#1500): on the platform every
    account, since there the screen manages them all (a new tenant's first users are
    made from there); in a workspace only who has a role here or a platform-wide one."""
    from app.domains.auth.users import list_users, users_of_workspace
    from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id

    if scope["op_platform"]:
        return list_users(db=db, _admin=None)
    return users_of_workspace(db, current_tenant_id.get() or DEFAULT_TENANT_ID)


def _held(user, scope: dict[str, Any]) -> dict[str, Any]:
    """What one account holds, as the screen reads it: the codes per workspace, the
    platform-wide OPERATOR, and the codes that count here (on the platform: in any
    workspace; in a workspace: in this one)."""
    from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id

    per_workspace: dict[int, set] = {}
    operator = False
    for role in user.roles:
        if role.tenant_id is None:
            operator = operator or role.role_code is Role.OPERATOR
        else:
            per_workspace.setdefault(role.tenant_id, set()).add(role.role_code.value)
    if scope["op_platform"]:
        here = set().union(*per_workspace.values()) if per_workspace else set()
    else:
        here = per_workspace.get(current_tenant_id.get() or DEFAULT_TENANT_ID, set())
    here = set(here) | ({Role.OPERATOR.value} if operator else set())
    return {"per_workspace": per_workspace, "operator": operator, "here": here}


def _roles_text(held: dict[str, Any], scope: dict[str, Any]) -> str:
    """The roles an account holds, as words, in the order of the role list; the
    platform-wide one first."""
    words = [scope["operator_label"]] if held["operator"] else []
    words += [label for code, label in scope["role_pairs"] if code in held["here"]]
    return ", ".join(words)


# ── The list ──────────────────────────────────────────────────────────────────


def _list_ctx(request: Request, db: Session, viewer_email: str, *, oob: bool = False) -> dict:
    """The list Gebruikers (#2114, CR-11 fase 5): the search on e-mail, the status as
    segments with their counts, the role in the toolbar's filters, the sort by e-mail.
    Accounts are dozens, not thousands, so the filtering happens on the fetched
    list. The state is in the URL; the toolbar asks this same address for the
    fragment."""
    scope = _scope(db, viewer_email)
    state = filterparams(request)
    q = (state.get("q") or "").strip()
    rol = (state.get("rol") or "").strip()
    if rol not in {code for code, _label in scope["role_pairs"]}:
        rol = ""
    actief = (state.get("actief") or "").strip()
    if actief not in ("ja", "nee"):
        actief = ""
    sort = (state.get("sort") or "").strip()
    if sort not in SORTS:
        sort = SORT_DEFAULT
    per_page = per_page_from(state.get("per_page"))
    try:
        page = max(1, int(state.get("page") or 1))
    except ValueError:
        page = 1

    everyone = [(u, _held(u, scope)) for u in _accounts(db, scope)]
    term = q.lower()
    shown = [
        (u, held)
        for u, held in everyone
        if (not term or term in (u.email or "").lower())
        and (not rol or rol in held["here"])
        and (actief != "ja" or u.is_active)
        and (actief != "nee" or not u.is_active)
    ]
    shown.sort(key=lambda pair: (pair[0].email or "").casefold(), reverse=sort[0] == "-")
    total = len(shown)
    page = min(page, max(1, -(-total // per_page)))
    shown = shown[(page - 1) * per_page : page * per_page]

    way_back = list_return(
        NAV,
        q=q,
        rol=rol,
        actief=actief,
        sort=sort if sort != SORT_DEFAULT else "",
        page=page if page > 1 else "",
        per_page=per_page if per_page != PER_PAGE_DEFAULT else "",
    )
    rows = [
        {
            "id": u.id,
            "email": u.email,
            "href": f"{NAV}/{u.id}?terug={quote(way_back, safe='/')}",
            "roles": _roles_text(held, scope),
            "inactive": not u.is_active,
        }
        for u, held in shown
    ]

    link_state = {"q": q, "rol": rol, "actief": actief}

    def _query(**more: Any) -> str:
        return urlencode(
            {k: v for k, v in {**link_state, "per_page": per_page, **more}.items() if v != ""}
        )

    turned = "-email" if sort == "email" else "email"
    email_head: dict[str, Any] = {
        "key": "email",
        "label": _("E-mail"),
        "cell": "name",
        "sort_url": f"{NAV}?{_query(sort=turned)}",
        "sort_page_url": f"{NAV}?{_query(sort=turned)}",
        "sorted": "asc" if sort == "email" else "desc",
    }
    active_count = sum(1 for u, _held_ in everyone if u.is_active)
    segments = [
        {"value": "", "label": _("Alle"), "count": len(everyone)},
        {"value": "ja", "label": _("Actief"), "count": active_count},
        {"value": "nee", "label": _("Inactief"), "count": len(everyone) - active_count},
    ]
    gefilterd = bool(q or rol or actief)
    return {
        "rows": rows,
        "columns": [
            email_head,
            {"key": "rollen", "label": _("Rollen"), "cell": "context"},
            {"key": "status", "label": _("Status"), "cell": "status"},
        ],
        "segments": segments,
        "actief": actief,
        "rol": rol,
        "rol_options": [("", _("Alle rollen"))] + list(scope["role_pairs"]),
        "q": q,
        "sort": sort,
        "sort_options": [("email", _("E-mail"))],
        "page": page,
        "per_page": per_page,
        "total": total,
        "page_sizes": list(PER_PAGE_OPTIONS),
        "pager_url": f"{NAV}?{_query(sort=sort)}",
        "empty_reason": (
            _("Geen gebruikers gevonden.") if gefilterd else _("Nog geen gebruikers.")
        ),
        "menu": (
            [
                {
                    "label": _("Alle werkruimtes"),
                    "href": f"{NAV}/alle-werkruimtes",
                    "icon": "users",
                }
            ]
            if scope["toon_overzicht"]
            else []
        ),
        "csrf_token": csrf_from_request(request),
        "nav_items": [] if oob else admin_nav(NAV, request),
        "oob": oob,
    }


@router.get("/admin/gebruikers", response_class=HTMLResponse)
def admin_gebruikers(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.USER_VIEW)),
):
    fragment = is_fragment_request(request)
    template = "_gu_tabel.html" if fragment else "admin_gebruikers.html"
    return templates.TemplateResponse(
        request, template, _list_ctx(request, db, email, oob=fragment)
    )


@router.get("/admin/gebruikers/alle-werkruimtes", response_class=HTMLResponse)
def access_overview_page(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_platform_right(Right.PLATFORM_VIEW)),
):
    """Every account, every workspace, every role — read-only, OPERATOR only (#1500),
    in the platform workspace only (#1535)."""
    from app.domains.auth.users import access_overview

    # #2015: the kit's list table, so the overview behaves on a phone as every
    # other list does. A row opens nothing — roles are changed in Gebruikers of
    # the workspace — so the account is the row's name without a link.
    columns = [
        {"key": "account", "label": _("Account"), "cell": "name"},
        {"key": "workspace", "label": _("Werkruimte"), "cell": "context"},
        {"key": "role", "label": _("Rol"), "cell": "more"},
        {"key": "status", "label": _("Status"), "cell": "status"},
    ]
    return templates.TemplateResponse(
        request,
        "admin_gebruikers_overzicht.html",
        {"nav_items": admin_nav(NAV, request), "rows": access_overview(db), "columns": columns},
    )


# ── A new account ─────────────────────────────────────────────────────────────


def _create_ctx(request: Request, db: Session, viewer_email: str, *, error=None, email="") -> dict:
    return {
        "nav_items": admin_nav(NAV, request),
        "csrf_token": csrf_from_request(request),
        "error": error,
        "email": email,
        "edit": True,
        "sel": {},
        "operator_aan": False,
        **_scope(db, viewer_email),
    }


@router.get("/admin/gebruikers/nieuw", response_class=HTMLResponse)
def gebruiker_nieuw(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.USER_VIEW)),
):
    """Aanmaken als volledige pagina (#627, §2.8) i.p.v. een modal."""
    return templates.TemplateResponse(
        request, "admin_gebruiker_nieuw.html", _create_ctx(request, db, email)
    )


@router.post("/admin/gebruikers", response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
async def gebruiker_aanmaken(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.USER_MANAGE)),
):
    from app.domains.auth.api import get_user_roles as _rollen_van
    from app.domains.auth.users import (
        UserCreate,
        create_user,
        is_platform_workspace,
        set_roles_for_workspaces,
    )

    form = await request.form()
    nieuw_email = str(form.get("email") or "").strip().lower()
    try:
        if is_platform_workspace(db):
            # Aanscherping 16 sep: vanaf het platform krijgt een nieuwe
            # gebruiker zijn rollen per werkruimte — zo ontstaan de eerste
            # accounts van een nieuwe tenant.
            per_werkruimte, operator = _platform_rollen_uit(form, db)
            user = create_user(
                UserCreate(email=nieuw_email, role_codes=[]),
                db=db,
                _admin=admin_user_by_email(db, email),
            )
            set_roles_for_workspaces(db, user.id, per_werkruimte, operator, _rollen_van(db, email))
        else:
            create_user(
                UserCreate(
                    email=nieuw_email, role_codes=[str(c) for c in form.getlist("role_codes")]
                ),
                db=db,
                _admin=admin_user_by_email(db, email),
            )
    except HTTPException as exc:
        # Op het aanmaakscherm blijven mét de fout (#627).
        return templates.TemplateResponse(
            request,
            "admin_gebruiker_nieuw.html",
            _create_ctx(request, db, email, error=str(exc.detail), email=nieuw_email),
        )
    # Een gebruiker is met één handeling compleet, dus terug naar de lijst (#627).
    return Response(status_code=204, headers={"HX-Redirect": NAV})


# ── The record ────────────────────────────────────────────────────────────────


def _record_ctx(
    request: Request,
    db: Session,
    viewer_email: str,
    user_id: int,
    *,
    edit: bool | None = None,
    saved: bool = False,
) -> dict:
    """The record of an account (#2114; end state §2.2, §5.2): the head with Bewerken
    and Acties, the summary beside the form column, the card Account and the roles
    — one card per workspace on the platform, one card in a workspace — read first,
    `?bewerken=1` the editor with ONE save. Who may see an account is what the list
    shows; who may change one is `Right.USER_MANAGE`, as before."""
    from app.domains.auth.users import user_of_workspace

    scope = _scope(db, viewer_email)
    user = user_of_workspace(db, user_id)
    held = _held(user, scope)
    can_manage = may(db, viewer_email, Right.USER_MANAGE)
    me = admin_user_by_email(db, viewer_email)
    frame = record_frame(request, db, NAV)
    way_back = frame["way_back"]
    keep = way_back["keep"] if way_back else ""
    editing = (frame["head_editing"] if edit is None else edit) and can_manage

    base = f"{NAV}/{user_id}"
    roles_text = _roles_text(held, scope)
    state = {
        "label": _("Actief") if user.is_active else _("Inactief"),
        "tone": "green" if user.is_active else "red",
    }
    deletable = can_manage and (me is None or me.id != user_id)
    delete = {
        "kind": "delete",
        "label": _("Verwijderen"),
        "attrs": f'hx-post="{base}/verwijderen"',
        "confirm": _("Dit account kan daarna niet meer aanmelden."),
        "confirm_ok": _("Definitief verwijderen"),
    }
    record_head = {
        "title": user.email,
        "badges": [state],
        "facts": [{"text": roles_text}] if roles_text else [],
        "primary": {
            "label": _("Bewerken"),
            "href": f"{base}?bewerken=1" + (f"&{keep}" if keep else ""),
        }
        if can_manage
        else None,
        "actions": [delete] if deletable else [],
    }
    role_count = (
        sum(len(codes) for codes in held["per_workspace"].values())
        if scope["op_platform"]
        else len(held["here"])
    ) + (1 if held["operator"] and scope["op_platform"] else 0)
    return {
        "user": user,
        "user_id": user_id,
        "edit": editing,
        "saved": saved,
        "record_head": record_head,
        "way_back": way_back,
        "summary": {
            "state": state,
            "figures": [{"label": _("Rollen"), "value": role_count}],
        },
        "sel": held["per_workspace"] if scope["op_platform"] else held["here"],
        "operator_aan": held["operator"],
        "delete_attrs": delete["attrs"] if deletable else "",
        "delete_confirm": delete["confirm"],
        "cancel_href": base + (f"?{keep}" if keep else ""),
        "csrf_token": csrf_from_request(request),
        "nav_items": admin_nav(NAV, request),
        **scope,
    }


def _record_page(request: Request, db: Session, viewer_email: str, user_id: int, **kwargs):
    return templates.TemplateResponse(
        request, "admin_gebruiker.html", _record_ctx(request, db, viewer_email, user_id, **kwargs)
    )


def _redirect(request: Request, url: str) -> Response:
    """The shell carries hx-boost: `HX-Redirect` lets the browser really navigate, so a
    refresh stays on the right page."""
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


@router.get("/admin/gebruikers/{user_id}", response_class=HTMLResponse)
def user_record(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.USER_VIEW)),
):
    return _record_page(request, db, email, user_id)


@router.post(
    "/admin/gebruikers/{user_id}", response_class=HTMLResponse, dependencies=[Depends(require_csrf)]
)
async def gebruiker_bijwerken(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.USER_MANAGE)),
):
    """One save for the whole record (#2114): the e-mail address, active, and the
    roles — in one request, as the inline row sent them. A refusal writes nothing
    the form keeps and leaves it as it was typed: the banner names the field."""
    from app.domains.auth.api import get_user_roles as _rollen_van
    from app.domains.auth.users import (
        UserUpdate,
        is_platform_workspace,
        set_roles_for_workspaces,
        update_user,
    )

    form = await request.form()
    try:
        _email_raw = form.get("email")
        _email = _email_raw.strip() if isinstance(_email_raw, str) else ""
        if is_platform_workspace(db):
            per_werkruimte, operator = _platform_rollen_uit(form, db)
            update_user(
                user_id,
                UserUpdate(
                    email=_email or None,
                    is_active=bool(form.get("is_active")),
                    role_codes=None,
                ),
                db=db,
                _admin=admin_user_by_email(db, email),
            )
            set_roles_for_workspaces(db, user_id, per_werkruimte, operator, _rollen_van(db, email))
        else:
            update_user(
                user_id,
                UserUpdate(
                    email=_email or None,
                    is_active=bool(form.get("is_active")),
                    role_codes=[str(c) for c in form.getlist("role_codes")],
                ),
                db=db,
                _admin=admin_user_by_email(db, email),
            )
    except HTTPException as exc:
        if exc.status_code == 404:
            raise  # not this workspace's account (#2162): as the GET answers
        return refusal_response(
            request, [FieldError(getattr(exc, "field", ""), str(exc.detail))], RECORD_MESSAGE
        )
    try:
        response = _record_page(request, db, email, user_id, edit=False, saved=True)
    except HTTPException:
        # Every role of the workspace was taken away: the account no longer belongs
        # in this workspace's list, so the record is no longer this workspace's to show.
        return _redirect(request, NAV)
    response.headers["HX-Push-Url"] = f"{NAV}/{user_id}"
    return response


@router.post(
    "/admin/gebruikers/{user_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def gebruiker_verwijderen(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.USER_MANAGE)),
):
    from app.domains.auth.users import delete_user

    try:
        delete_user(user_id, db=db, current_admin=admin_user_by_email(db, email))
    except HTTPException as exc:
        if exc.status_code == 404:
            raise  # not this workspace's account (#2162): as the GET answers
        return refusal_response(request, [FieldError("", str(exc.detail))], RECORD_MESSAGE)
    return _redirect(request, NAV)
