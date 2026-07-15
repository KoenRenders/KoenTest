"""Server-rendered publieke activiteiten (fase 4a-3, #402 — §21): de lijst,
het archief en de registratieflow (alle vormtypes via product-regels) met
Mollie-redirect. De totaalberekening is uitsluitend server-side (§19.3): het
totaal-fragment wordt bij elke wijziging via htmx opnieuw berekend met de
prijzen uit de databank — geen client-side duplicaat meer.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.activities.models import Activity, ActivityProduct, ActivitySubRegistration
from app.limiter import registration_limiter
from app.ui import site_context, templates
from app.i18n import _

router = APIRouter(include_in_schema=False)


def _session_person(request: Request, db: Session):
    """Ingelogd lid (HttpOnly-sessie) of None — bepaalt ledenprijs en person_id.
    De backend blijft de bron van waarheid voor het effectieve bedrag."""
    from app.domains.auth.api import SESSION_COOKIE, login_person_for_email, read_session_value

    email = read_session_value(request.cookies.get(SESSION_COOKIE))
    if not email:
        return None
    return login_person_for_email(db, email)


def _is_member(db, person) -> bool:
    from app.domains.membership.api import has_valid_membership

    return has_valid_membership(person)


def _lijst_ctx(db: Session, scope: str, request: Request | None = None) -> dict:
    from app.domains.activities.router import list_activities

    ctx = {"activities": list_activities(scope=scope, db=db), "scope": scope}
    if request is not None:
        # De volledige SiteShell (header/nav/footer) heeft site_context nodig (#475).
        ctx = {**site_context(db, request), **ctx}
    return ctx


@router.get("/activiteiten", response_class=HTMLResponse)
def activiteiten_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "activiteiten.html", _lijst_ctx(db, "upcoming", request))


@router.get("/archief", response_class=HTMLResponse)
def archief_redirect(request: Request):
    """URL-pariteit (React-exit 405-e): oud React-pad -> /activiteiten/archief."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/activiteiten/archief", status_code=302)


@router.get("/activiteiten/archief", response_class=HTMLResponse)
def archief_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "activiteiten.html", _lijst_ctx(db, "archived", request))


@router.get("/activiteiten/{activity_id}/deelnemers/{component_id}",
            response_class=HTMLResponse)
def deelnemers_fragment(activity_id: int, component_id: int, request: Request,
                        db: Session = Depends(get_db)):
    """Publieke deelnemerslijst per onderdeel ('Wie doet er mee?') als htmx-
    fragment — herstelt de v1.14-functie voor portal-beheerde inschrijvingen
    (#451). Hergebruikt het bestaande publieke registraties-endpoint."""
    from app.domains.activities.router import get_public_registrations

    deelnemers = get_public_registrations(activity_id, component_id=component_id, db=db)
    return templates.TemplateResponse(request, "_deelnemers.html",
                                      {"deelnemers": deelnemers})


def _component_or_404(db: Session, activity_id: int, component_id: int):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    component = (db.query(ActivitySubRegistration)
                 .filter(ActivitySubRegistration.id == component_id,
                         ActivitySubRegistration.activity_id == activity_id).first())
    if activity is None or component is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    return activity, component


def _unit_price(product: ActivityProduct, is_member: bool) -> Decimal:
    if product.is_free or product.pay_on_site:
        return Decimal("0")
    if is_member and product.member_price is not None and product.member_price >= 0:
        return Decimal(product.member_price)
    return Decimal(product.price)


def _quantities(form) -> dict[int, int]:
    out: dict[int, int] = {}
    for key, value in form.items():
        if key.startswith("product_"):
            try:
                out[int(key.removeprefix("product_"))] = max(0, int(value or 0))
            except ValueError:
                continue
    return out


def _totaal(db: Session, component, quantities: dict[int, int], is_member: bool) -> Decimal:
    total = Decimal("0")
    for product in component.products:
        qty = quantities.get(product.id, 0)
        total += _unit_price(product, is_member) * qty
    return total


def _form_ctx(request: Request, db: Session, activity, component, **extra) -> dict:
    person = _session_person(request, db)
    is_member = _is_member(db, person)
    ctx = {
        "activity": activity, "component": component, "is_member": is_member,
        "person": person, "error": None, "totaal": Decimal("0"), "values": {},
    }
    ctx.update(extra)
    return ctx


@router.get("/activiteiten/{activity_id}/inschrijven/{component_id}",
            response_class=HTMLResponse)
def inschrijf_form(activity_id: int, component_id: int, request: Request,
                   db: Session = Depends(get_db)):
    activity, component = _component_or_404(db, activity_id, component_id)
    return templates.TemplateResponse(request, "_inschrijf_form.html",
                                      _form_ctx(request, db, activity, component))


@router.post("/activiteiten/{activity_id}/inschrijven/{component_id}/totaal",
             response_class=HTMLResponse)
async def inschrijf_totaal(activity_id: int, component_id: int, request: Request,
                           db: Session = Depends(get_db)):
    """Server-side herberekening bij elke wijziging (§19.3 — geen drift)."""
    _activity, component = _component_or_404(db, activity_id, component_id)
    form = await request.form()
    person = _session_person(request, db)
    is_member = _is_member(db, person)
    totaal = _totaal(db, component, _quantities(form), is_member)
    return templates.TemplateResponse(request, "_inschrijf_totaal.html", {
        "totaal": totaal, "is_member": is_member})


@router.post("/activiteiten/{activity_id}/inschrijven/{component_id}",
             response_class=HTMLResponse, dependencies=[Depends(registration_limiter)])
async def inschrijf_submit(activity_id: int, component_id: int, request: Request,
                           background_tasks: BackgroundTasks,
                           db: Session = Depends(get_db)):
    from app.domains.activities.router import register_for_activity
    from app.schemas.activity import RegistrationCreate, RegistrationItemCreate

    activity, component = _component_or_404(db, activity_id, component_id)
    form = await request.form()
    quantities = _quantities(form)
    person = _session_person(request, db)
    is_member = _is_member(db, person)

    values = {k: (v if isinstance(v, str) else "") for k, v in form.items()}
    ctx = _form_ctx(request, db, activity, component,
                    values=values, totaal=_totaal(db, component, quantities, is_member))

    naam = (values.get("contact_name") or "").strip()
    email = (values.get("contact_email") or "").strip()
    gsm = (values.get("phone") or "").strip()
    if not naam or "@" not in email or not gsm:
        ctx["error"] = "Vul naam, e-mailadres en mobiel nummer in."
        return templates.TemplateResponse(request, "_inschrijf_form.html", ctx)
    if component.products and not any(q > 0 for q in quantities.values()):
        ctx["error"] = "Selecteer minstens één product."
        return templates.TemplateResponse(request, "_inschrijf_form.html", ctx)

    heeft_betaald_deel = ctx["totaal"] > 0
    data = RegistrationCreate(
        contact_name=naam, contact_email=email, phone=gsm,
        team_name=(values.get("team_name") or "").strip() or None,
        payment_method=(values.get("payment_method") or "ONLINE") if heeft_betaald_deel else None,
        component_id=component.id,
        items=[RegistrationItemCreate(product_id=pid, quantity=qty)
               for pid, qty in quantities.items() if qty > 0],
        remarks=(values.get("remarks") or "").strip() or None,
    )
    try:
        result = register_for_activity(activity.id, data, background_tasks,
                                       db=db, current_member=person)
    except HTTPException as exc:
        ctx["error"] = str(exc.detail)
        return templates.TemplateResponse(request, "_inschrijf_form.html", ctx)

    checkout_url = getattr(result, "checkout_url", None) or (
        result.get("checkout_url") if isinstance(result, dict) else None)
    if checkout_url:
        # Vaste UI-beslissing: harde redirect naar Mollie (nooit client-side route).
        response = templates.TemplateResponse(request, "_inschrijf_klaar.html",
                                              {"naam": naam, "checkout": True})
        response.headers["HX-Redirect"] = checkout_url
        return response
    return templates.TemplateResponse(request, "_inschrijf_klaar.html",
                                      {"naam": naam, "checkout": False})
