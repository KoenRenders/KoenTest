"""Server-rendered "Word lid"-formulier (React-exit #405, §21).

Meerdere gezinsleden via htmx (rij-fragment per index — geen client-side
state), postcode altijd een dropdown (vaste UI-beslissing), betaalwijze met
Mollie-redirect via HX-Redirect. Hergebruikt register_family integraal
(dedup, prijsregels, mail, audit).
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import registration_limiter
from app.ui import site_context, templates
from app.i18n import _

router = APIRouter(include_in_schema=False)


def _codes(db: Session) -> dict:
    from app.domains.mdm.api import GenderCode, PostalCode, RelationTypeCode

    def _uniq(rows):
        seen, out = set(), []
        for r in rows:
            if r.code not in seen:
                seen.add(r.code)
                out.append(r)
        return out

    return {
        "gender_codes": _uniq(db.query(GenderCode).order_by(GenderCode.code).all()),
        "relation_types": _uniq(db.query(RelationTypeCode).order_by(RelationTypeCode.code).all()),
        "postal_codes": db.query(PostalCode).order_by(PostalCode.postal_code).all(),
    }


@router.get("/lid-worden", response_class=HTMLResponse)
def lid_worden(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "lid_worden.html", {
        **site_context(db, request), **_codes(db), "error": None, "values": {}})


@router.get("/lid-worden/persoon-rij", response_class=HTMLResponse)
def persoon_rij(request: Request, db: Session = Depends(get_db)):
    try:
        index = max(1, int(request.query_params.get("index", "1")))
    except ValueError:
        index = 1
    return templates.TemplateResponse(request, "_lid_persoon_rij.html", {
        **_codes(db), "i": index, "values": {}})


def _parse_members(form) -> list[dict]:
    import re

    # Gat-bestendig (#456): een verwijderd gezinslid laat een gat in de m<i>-
    # nummering; scan dus álle aanwezige indices i.p.v. te stoppen bij het eerste
    # ontbrekende.
    indices = sorted({int(mo.group(1)) for k in form.keys()
                      if (mo := re.match(r"m(\d+)_", str(k)))})
    members: list[dict] = []
    for index in indices:
        m = {k: (form.get(f"m{index}_{k}") or "").strip() for k in
             ("first_name", "last_name", "date_of_birth", "gender_code",
              "email", "phone", "mobile", "relation_type")}
        if m["first_name"] or m["last_name"]:
            members.append(m)
    return members


@router.post("/lid-worden", response_class=HTMLResponse,
             dependencies=[Depends(registration_limiter)])
async def lid_worden_submit(request: Request, background_tasks: BackgroundTasks,
                            db: Session = Depends(get_db)):
    from pydantic import ValidationError

    from app.domains.membership.register_router import register_family
    from app.domains.membership.schemas_family import FamilyCreate, FamilyMemberCreate

    form = await request.form()
    values = {k: (v if isinstance(v, str) else "") for k, v in form.items()}
    ctx = {**site_context(db, request), **_codes(db), "values": values}

    members = _parse_members(form)
    if not members:
        ctx["error"] = "Vul minstens het hoofdlid in."
        return templates.TemplateResponse(request, "lid_worden.html", ctx)
    if not (values.get("postal_code") or "").strip():
        ctx["error"] = "Selecteer een geldige postcode uit de lijst."
        return templates.TemplateResponse(request, "lid_worden.html", ctx)

    try:
        data = FamilyCreate(
            street=(values.get("street") or "").strip(),
            house_number=(values.get("house_number") or "").strip(),
            bus_number=(values.get("bus_number") or "").strip() or None,
            postal_code=(values.get("postal_code") or "").strip(),
            payment_method=(values.get("payment_method") or "online").strip(),
            members=[FamilyMemberCreate(
                first_name=m["first_name"], last_name=m["last_name"],
                date_of_birth=m["date_of_birth"] or None,
                gender_code=m["gender_code"] or None,
                email=m["email"] or None, phone=m["phone"] or None,
                mobile=m["mobile"] or None,
                relation_type=m["relation_type"] or ("HOOFDLID" if not members.index(m) else "PARTNER"),
            ) for m in members],
        )
    except ValidationError as exc:
        eerste = exc.errors()[0]
        ctx["error"] = str(eerste.get("msg", "Ongeldige invoer."))
        return templates.TemplateResponse(request, "lid_worden.html", ctx)

    try:
        result = register_family(data, background_tasks, db=db)
    except HTTPException as exc:
        ctx["error"] = str(exc.detail)
        return templates.TemplateResponse(request, "lid_worden.html", ctx)

    checkout_url = getattr(result, "checkout_url", None)
    response = templates.TemplateResponse(request, "lid_worden_klaar.html", {
        **site_context(db, request), "checkout": bool(checkout_url),
        "amount": getattr(result, "amount", None)})
    if checkout_url:
        response.headers["HX-Redirect"] = checkout_url
    return response


# ── Ledenportaal (React-exit 405-b): /leden/gezin + login-pariteit ─────────────

def _session_member(request: Request, db: Session):
    """Ingelogd lid via de HttpOnly-sessie, of None."""
    from app.domains.auth.api import SESSION_COOKIE, login_person_for_email, read_session_value

    email = read_session_value(request.cookies.get(SESSION_COOKIE))
    if not email:
        return None
    return login_person_for_email(db, email)


def _portal_ctx(request: Request, db: Session, person) -> dict:
    from datetime import date

    from app.domains.auth.api import SESSION_COOKIE, csrf_token_for
    from app.domains.membership.api import renewal_available, membership_coverage_until
    from app.domains.membership.household_router import get_household

    household = get_household(person=person, db=db)
    # Dekking t/m (incl. een al betaald volgend jaar) i.p.v. enkel 'geldig vandaag' (#496).
    valid_until = membership_coverage_until(person)
    return {
        **site_context(db, request), **_codes(db),
        "household": household,
        "person_id": person.id,
        "valid_until": valid_until,
        "renewal_available": renewal_available(valid_until, date.today()),
        "csrf_token": csrf_token_for(request.cookies.get(SESSION_COOKIE) or ""),
    }


@router.get("/leden/gezin", response_class=HTMLResponse)
def gezin_portaal(request: Request, db: Session = Depends(get_db)):
    person = _session_member(request, db)
    if person is None:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/aanmelden", status_code=302)
    return templates.TemplateResponse(request, "gezin_portaal.html",
                                      _portal_ctx(request, db, person))


def _require_member_csrf(request: Request, db: Session):
    from app.domains.auth.api import require_csrf

    person = _session_member(request, db)
    if person is None:
        raise HTTPException(status_code=401, detail=_("Niet aangemeld"))
    require_csrf(request)
    return person


@router.post("/leden/gezin/personen/{person_id}", response_class=HTMLResponse)
async def gezin_persoon_opslaan(person_id: int, request: Request,
                                db: Session = Depends(get_db)):
    from app.domains.membership.household_router import update_person

    person = _require_member_csrf(request, db)
    form = await request.form()

    def _v(key: str) -> str:
        value = form.get(key)
        return value.strip() if isinstance(value, str) else ""

    from typing import Any

    data: dict[str, Any] = {
        "first_name": _v("first_name"),
        "last_name": _v("last_name"),
        "date_of_birth": _v("date_of_birth") or None,
        "gender_code": _v("gender_code") or None,
        "email": _v("email") or None,
        "phone": _v("phone") or None,
        "mobile": _v("mobile") or None,
    }
    if form.get("street") is not None:
        data["address"] = {
            "street": _v("street"),
            "house_number": _v("house_number"),
            "bus_number": _v("bus_number") or None,
            "postal_code": _v("postal_code"),
        }
    update_person(person_id, data, person=person, db=db)
    return templates.TemplateResponse(request, "gezin_portaal.html",
                                      _portal_ctx(request, db, person))


@router.post("/leden/gezin/personen", response_class=HTMLResponse)
async def gezin_persoon_toevoegen(request: Request, db: Session = Depends(get_db)):
    from app.domains.membership.household_router import add_person

    person = _require_member_csrf(request, db)
    form = await request.form()

    def _v(key: str) -> str:
        value = form.get(key)
        return value.strip() if isinstance(value, str) else ""

    add_person({
        "first_name": _v("first_name"),
        "last_name": _v("last_name"),
        "date_of_birth": _v("date_of_birth") or None,
        "gender_code": _v("gender_code") or None,
        "email": _v("email") or None,
        "phone": _v("phone") or None,
        "mobile": _v("mobile") or None,
    }, person=person, db=db)
    return templates.TemplateResponse(request, "gezin_portaal.html",
                                      _portal_ctx(request, db, person))


@router.post("/leden/gezin/personen/{person_id}/verwijderen", response_class=HTMLResponse)
def gezin_persoon_verwijderen(person_id: int, request: Request,
                              db: Session = Depends(get_db)):
    from app.domains.membership.household_router import remove_person

    person = _require_member_csrf(request, db)
    remove_person(person_id, person=person, db=db)
    return templates.TemplateResponse(request, "gezin_portaal.html",
                                      _portal_ctx(request, db, person))


@router.post("/leden/gezin/vernieuwen", response_class=HTMLResponse)
def gezin_vernieuwen(request: Request, db: Session = Depends(get_db),
                     payment_method: str = Form("online")):
    from app.domains.membership.household_router import renew_membership

    person = _require_member_csrf(request, db)
    method = payment_method if payment_method in ("online", "transfer") else "online"
    try:
        result = renew_membership(person=person, db=db, payment_method=method)
    except HTTPException as exc:
        ctx = _portal_ctx(request, db, person)
        ctx["error"] = str(exc.detail)
        return templates.TemplateResponse(request, "gezin_portaal.html", ctx)
    ctx = _portal_ctx(request, db, person)
    checkout_url = result.get("checkout_url") if isinstance(result, dict) else None
    if checkout_url:
        response = templates.TemplateResponse(request, "gezin_portaal.html", ctx)
        response.headers["HX-Redirect"] = checkout_url
        return response
    # Overschrijving (#497): toon de betaalinstructies (bedrag + OGM + IBAN) op het scherm.
    from app.kernel.tenant_config import tenant_payment_iban, tenant_payment_beneficiary

    ctx["renew_transfer"] = {
        "amount": result.get("amount"),
        "ogm": result.get("structured_communication"),
        "iban": tenant_payment_iban(db),
        "beneficiary": tenant_payment_beneficiary(db),
    }
    return templates.TemplateResponse(request, "gezin_portaal.html", ctx)


# Login-pariteit (#405): /login = de htmx-aanmeldflow; /login/verify blijft het
# magic-link-doel uit de e-mails en zet de sessie + stuurt door.

@router.get("/login", response_class=HTMLResponse)
def login_redirect(request: Request):
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/aanmelden", status_code=302)


@router.get("/leden/login", response_class=HTMLResponse)
def leden_login_redirect(request: Request):
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/aanmelden", status_code=302)


@router.get("/login/verify", response_class=HTMLResponse)
def login_verify(request: Request, token: str = "", db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse

    from app.domains.auth.api import LoginToken, get_user_roles, set_session_cookie
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    login_token = (db.query(LoginToken)
                   .filter(LoginToken.token == token, LoginToken.used == False,  # noqa: E712
                           LoginToken.email.isnot(None)).first())
    if not login_token or login_token.expires_at.replace(tzinfo=timezone.utc) < now:
        return templates.TemplateResponse(request, "login_verlopen.html",
                                          site_context(db, request), status_code=401)
    login_token.used = True
    db.commit()
    # Landing naar wat de rol mag openen (#530), gelijk aan de OTP-flow: ADMIN/
    # OPERATOR → werkbank; FINANCE-only → betalingen (werkbank is nu ADMIN/OPERATOR-
    # only en zou 403'en); overige (gewoon lid) → gezin.
    roles = set(get_user_roles(db, login_token.email))
    if {"ADMIN", "OPERATOR"} & roles:
        doel = "/admin/werkbank"
    elif "FINANCE" in roles:
        doel = "/admin/betalingen"
    else:
        doel = "/leden/gezin"
    response = RedirectResponse(doel, status_code=302)
    set_session_cookie(response, login_token.email)
    return response


@router.get("/leden/login/verify", response_class=HTMLResponse)
def leden_login_verify_redirect(request: Request, token: str = ""):
    """URL-pariteit (React-exit 405-e): oud React-pad → het magic-link-doel."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(f"/login/verify?token={token}", status_code=302)
