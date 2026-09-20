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
from app.domains.activities.totals import has_payable_products, quote_lines
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


def _lijst_ctx(db: Session, scope: str, request: Request | None = None) -> dict:
    from app.domains.activities.api import list_activities

    ctx = {"activities": list_activities(db, scope=scope), "scope": scope}
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
    from app.domains.activities.api import public_registrations

    deelnemers = public_registrations(db, activity_id, component_id)
    return templates.TemplateResponse(request, "_deelnemers.html",
                                      {"deelnemers": deelnemers})


def _component_or_404(db: Session, activity_id: int, component_id: int):
    """Activiteit + onderdeel, of 404. `get_component` controleert meteen dat het
    onderdeel bij díe activiteit hoort (#635 I)."""
    from app.domains.activities.api import get_activity, get_component

    activity = get_activity(db, activity_id)
    component = get_component(db, component_id, activity_id=activity_id)
    if activity is None or component is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    return activity, component


def _is_member(person) -> bool:
    """Is deze bezoeker vandaag lid? (bepaalt de ledenprijs op het scherm)

    Peildatum "vandaag" is hier juist: het inschrijfscherm toont wat je nú zou
    betalen. `compute_registration_total` gebruikt na het opslaan de
    inschrijfdatum, zodat de prijs vanaf dan vastligt (#635 punt 1).
    """
    from app.domains.membership.api import has_valid_membership

    return has_valid_membership(person)


def _quantities(form) -> dict[int, int]:
    out: dict[int, int] = {}
    for key, value in form.items():
        if key.startswith("product_"):
            try:
                out[int(key.removeprefix("product_"))] = max(0, int(value or 0))
            except ValueError:
                continue
    return out


def _person_contacts(person) -> tuple[str, str]:
    """(e-mail, mobiel) van een person uit zijn ContactDetails, of lege strings."""
    email = mobile = ""
    if person is not None:
        for c in getattr(person, "contact_details", []) or []:
            if c.contact_type_code == "EMAIL" and not email:
                email = c.value or ""
            elif c.contact_type_code == "MOBILE" and not mobile:
                mobile = c.value or ""
    return email, mobile


def _form_ctx(request: Request, db: Session, activity, component, **extra) -> dict:
    person = _session_person(request, db)
    is_member = _is_member(person)
    # Voorinvullen voor een ingelogd lid (#476): naam vult de template al vanuit
    # person; e-mail + mobiel komen uit de ContactDetails. Op submit overschrijft
    # extra["values"] deze defaults.
    email, mobile = _person_contacts(person)
    prefill: dict = {}
    if email:
        prefill["contact_email"] = email
    if mobile:
        prefill["phone"] = mobile
    ctx = {
        "activity": activity, "component": component, "is_member": is_member,
        "person": person, "error": None, "totaal": Decimal("0"), "values": prefill,
        "heeft_prijs": has_payable_products(component, is_member),
    }
    ctx.update(extra)
    return ctx


@router.get("/activiteiten/{activity_id}/inschrijven/{component_id}",
            response_class=HTMLResponse)
def inschrijf_form(activity_id: int, component_id: int, request: Request,
                   db: Session = Depends(get_db)):
    from app.domains.activities.api import registration_refusal

    activity, component = _component_or_404(db, activity_id, component_id)
    ctx = _form_ctx(request, db, activity, component)
    # #974: een modal die geopend wordt nadat de inschrijvingen dicht zijn (een oude
    # link, een tabblad dat bleef openstaan) toont meteen waarom — met dezelfde
    # woorden als de route bij het verzenden, want ze komen uit dezelfde functie.
    ctx["error"] = registration_refusal(activity, component=component)
    return templates.TemplateResponse(request, "_inschrijf_form.html", ctx)


@router.post("/activiteiten/{activity_id}/inschrijven/{component_id}/totaal",
             response_class=HTMLResponse)
async def inschrijf_totaal(activity_id: int, component_id: int, request: Request,
                           db: Session = Depends(get_db)):
    """Server-side herberekening bij elke wijziging (§19.3 — geen drift)."""
    _activity, component = _component_or_404(db, activity_id, component_id)
    form = await request.form()
    person = _session_person(request, db)
    is_member = _is_member(person)
    totaal, _regels = quote_lines(component, _quantities(form), is_member)
    return templates.TemplateResponse(request, "_inschrijf_totaal.html", {
        "totaal": totaal, "is_member": is_member,
        "heeft_prijs": has_payable_products(component, is_member)})


@router.post("/activiteiten/{activity_id}/inschrijven/{component_id}",
             response_class=HTMLResponse, dependencies=[Depends(registration_limiter)])
async def inschrijf_submit(activity_id: int, component_id: int, request: Request,
                           background_tasks: BackgroundTasks,
                           db: Session = Depends(get_db)):
    from app.domains.activities.api import register_for_activity
    from app.schemas.activity import RegistrationCreate, RegistrationItemCreate

    activity, component = _component_or_404(db, activity_id, component_id)
    form = await request.form()
    quantities = _quantities(form)
    person = _session_person(request, db)
    is_member = _is_member(person)

    values = {k: (v if isinstance(v, str) else "") for k, v in form.items()}
    totaal, _regels = quote_lines(component, quantities, is_member)
    ctx = _form_ctx(request, db, activity, component, values=values, totaal=totaal)

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
        result = register_for_activity(db, activity.id, data, background_tasks,
                                       current_member=person)
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


@router.get("/activiteiten/{sleutel}")
def activiteit_deeplink(sleutel: str, request: Request,
                        db: Session = Depends(get_db)):
    """Het kanonieke deeladres van één activiteit (golf 8, 15 sep 2026).

    Een vooraf gecommuniceerde link moet ook ná het evenement blijven werken,
    maar de kaart verhuist dan van /activiteiten naar het archief. Deze route
    zoekt de activiteit (slug of nummer, zoals de fotoalbums #884/#890) en
    stuurt door naar de juiste lijst mét het kaart-anker. Komt er ooit een
    volwaardige publieke activiteitspagina, dan neemt die dit adres over en
    breekt geen enkele oude link.

    Staat ná /activiteiten/archief geregistreerd, dus "archief" wint als pad.
    """
    from datetime import date

    from fastapi.responses import RedirectResponse

    from app.domains.activities.api import activity_by_key
    from app.ui import path_for

    activiteit = activity_by_key(db, sleutel)
    if activiteit is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    # Voorbij = de laatste (eind)datum ligt vóór vandaag — dezelfde blik als de
    # lijstscopes: zonder datums blijft ze op de komende lijst staan.
    laatste = max((d.end_date or d.start_date for d in activiteit.dates),
                  default=None)
    # #977: de Belgische datum, zoals de lijst zelf — anders stuurt een link rond
    # middernacht door naar een lijst waar de kaart (nog) niet op staat.
    from app.kernel.clock import belgian_today

    voorbij = bool(laatste and laatste < belgian_today())
    # Golf 12 (#913): de pagina neemt het adres over, zoals deze docstring sinds
    # golf 8 aankondigde — geen enkele gedeelde link breekt. Het view-model komt
    # uit list_activities, dezelfde bron als de kaart, dus status, volzet en
    # deadline kunnen nooit uiteenlopen met de lijst.
    from app.domains.activities.api import list_activities

    scope = "archived" if voorbij else "upcoming"
    vm = next((x for x in list_activities(db, scope=scope)
               if x.id == activiteit.id), None)
    if vm is None:
        # Vangnet voor een record dat (nog) in geen van beide lijstscopes valt:
        # de oude redirect, zodat de link nooit doodloopt.
        anker = activiteit.slug or f"act-{activiteit.id}"
        lijst = "/activiteiten/archief" if voorbij else "/activiteiten"
        return RedirectResponse(path_for(f"{lijst}#{anker}"), status_code=302)
    poster_url = None
    poster_link = None
    if activiteit.poster_asset_url:
        # Een PDF-affiche toont haar voorblad (#1019); het beeld linkt altijd
        # naar het volledige bestand.
        poster_link = activiteit.poster_asset_url
        poster_url = (activiteit.poster_asset_url + "/thumb"
                      if activiteit.poster_asset_is_pdf else activiteit.poster_asset_url)
    elif activiteit.poster_url:
        poster_link = activiteit.poster_url
    # De klokregel bovenaan (#1051-copy: zonder jaartal, oranje in de laatste
    # week). De datum is vandaag nog activiteitsbreed en dus per definitie "alle
    # onderdelen dezelfde" — de kopregel-tak van de #1053-weergaveregels. Zodra
    # #1053 het veld per onderdeel legt, vult `deadline_per` de andere tak.
    from app.i18n import long_date

    deadline_kop = None
    if (scope == "upcoming" and vm.registration_state == "open"
            and vm.registration_closes_on):
        deadline_kop = {
            "label": long_date(vm.registration_closes_on).rsplit(" ", 1)[0],
            "urgent": (vm.registration_closes_on - belgian_today()).days <= 7}
    return templates.TemplateResponse(request, "activiteit.html", {
        **site_context(db, request), "a": vm, "scope": scope,
        "terug": "/activiteiten/archief" if voorbij else "/activiteiten",
        "poster_url": poster_url, "poster_link": poster_link,
        "deadline_kop": deadline_kop, "deadline_per": {},
    })
