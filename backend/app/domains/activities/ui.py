"""Server-rendered publieke activiteiten (fase 4a-3, #402 — §21): de lijst,
het archief en de registratieflow (alle vormtypes via product-regels) met
Mollie-redirect. De totaalberekening is uitsluitend server-side (§19.3): het
totaal-fragment wordt bij elke wijziging via htmx opnieuw berekend met de
prijzen uit de databank — geen client-side duplicaat meer.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.activities.api import REGISTRATION_STATE, RegistrationState
from app.domains.mdm.api import CONTACT
from app.i18n import _
from app.kernel.codes import register_tones
from app.limiter import registration_limiter
from app.ui import site_context, templates

router = APIRouter(include_in_schema=False)

# The badge tone of a registration state, next to the screen that draws it
# (§B4.5). These were a dictionary keyed on the DUTCH LABEL inside two templates
# ("Afgesloten": "gray", …), which would have lost every colour the day a unit
# read the page in English. Keyed on the code now; the colours are the same.
register_tones(
    REGISTRATION_STATE.name,
    {
        RegistrationState.OPEN: "green",
        RegistrationState.CLOSED: "gray",
        RegistrationState.PAST: "gray",
        RegistrationState.CANCELLED: "red",
    },
)


def _lijst_ctx(db: Session, scope: str, request: Request | None = None) -> dict:
    from app.domains.activities.api import list_activities

    ctx = {"activities": list_activities(db, scope=scope), "scope": scope}
    if request is not None:
        # De volledige SiteShell (header/nav/footer) heeft site_context nodig (#475).
        ctx = {**site_context(db, request), **ctx}
    return ctx


@router.get("/activiteiten", response_class=HTMLResponse)
def activiteiten_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "activiteiten.html", _lijst_ctx(db, "upcoming", request)
    )


@router.get("/archief", response_class=HTMLResponse)
def archief_redirect(request: Request):
    """URL-pariteit (React-exit 405-e): oud React-pad -> /activiteiten/archief."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/activiteiten/archief", status_code=302)


@router.get("/activiteiten/archief", response_class=HTMLResponse)
def archief_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "activiteiten.html", _lijst_ctx(db, "archived", request)
    )


@router.get("/activiteiten/{activity_id}/deelnemers/{component_id}", response_class=HTMLResponse)
def deelnemers_fragment(
    activity_id: int, component_id: int, request: Request, db: Session = Depends(get_db)
):
    """Publieke deelnemerslijst per onderdeel ('Wie doet er mee?') als htmx-
    fragment — herstelt de v1.14-functie voor portal-beheerde inschrijvingen
    (#451). Hergebruikt het bestaande publieke registraties-endpoint."""
    from app.domains.activities.api import public_registrations

    deelnemers = public_registrations(db, activity_id, component_id)
    return templates.TemplateResponse(request, "_deelnemers.html", {"deelnemers": deelnemers})


def _component_or_404(db: Session, activity_id: int, component_id: int):
    """Activiteit + onderdeel, of 404. `get_component` controleert meteen dat het
    onderdeel bij díe activiteit hoort (#635 I)."""
    from app.domains.activities.api import get_activity, get_component

    activity = get_activity(db, activity_id)
    component = get_component(db, component_id, activity_id=activity_id)
    if activity is None or component is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    return activity, component


def _aanmeldadres(request: Request) -> str:
    """Het e-mailadres waarmee deze bezoeker aangemeld is, of "".

    Uit de sessie en niet uit de contactgegevens van de persoon (#1174). Een lid
    mag meerdere adressen hebben, en dan is "het eerste e-mailadres van deze
    persoon" een willekeurige keuze — terwijl er precies één adres is waarvan we
    zeker weten dat de bezoeker het gebruikt: dat waarmee hij zich net aanmeldde.

    Koen, 26 september 2026: de bevestiging gaat naar het adres op het formulier,
    en bij een aangemeld lid staat daar het aanmeldadres, *"ook al is dat niet
    hoofdadres"*. Het hoofdadres stuurt geen enkele verzending aan; het is het
    adres dat Raak Nationaal kent.
    """
    from app.domains.auth.api import SESSION_COOKIE, read_session_value

    return read_session_value(request.cookies.get(SESSION_COOKIE)) or ""


def _person_mobile(person) -> str:
    """Het mobiele nummer van een person uit zijn ContactDetails, of "".

    Was tot #1174 `_person_contacts`, dat ook een e-mailadres teruggaf — "de
    eerste EMAIL-rij". Die helft is vervallen: het formulier vult nu het
    aanmeldadres in. Eén nummer overhouden is eerlijker dan een tuple waarvan de
    ene helft niet meer gebruikt wordt.
    """
    if person is None:
        return ""
    for c in getattr(person, "contact_details", []) or []:
        if c.contact_type_code == CONTACT.MOBILE and c.value:
            return c.value
    return ""


def _channel(request: Request, db: Session, activity, component):
    """The public channel of the one registration form (#1284): who registers is
    whoever is signed in — never the address typed into the form."""
    from app.domains.activities.api import public_channel

    return public_channel(db, activity, component, _aanmeldadres(request))


def _prefill(request: Request, person) -> dict:
    """Prefill for a signed-in member (#476): the name comes from `person` in
    the template, the mobile number from the ContactDetails, and the e-mail
    address from the SESSION (#1174) — the address he just signed in with,
    because a member may have several and the confirmation goes to what stands
    here. On a submit, the typed values replace these."""
    email, mobile = _aanmeldadres(request), _person_mobile(person)
    prefill: dict = {}
    if email:
        prefill["contact_email"] = email
    if mobile:
        prefill["phone"] = mobile
    return prefill


@router.get("/activiteiten/{activity_id}/inschrijven/{component_id}", response_class=HTMLResponse)
def inschrijf_form(
    activity_id: int, component_id: int, request: Request, db: Session = Depends(get_db)
):
    from app.domains.activities.api import form_context, registration_refusal

    activity, component = _component_or_404(db, activity_id, component_id)
    channel = _channel(request, db, activity, component)
    # #974: een modal die geopend wordt nadat de inschrijvingen dicht zijn (een oude
    # link, een tabblad dat bleef openstaan) toont meteen waarom — met dezelfde
    # woorden als de route bij het verzenden, want ze komen uit dezelfde functie.
    ctx = form_context(
        channel,
        activity,
        component,
        values=_prefill(request, channel.person),
        error=registration_refusal(activity, component=component),
    )
    return templates.TemplateResponse(request, "_inschrijf_form.html", ctx)


@router.post(
    "/activiteiten/{activity_id}/inschrijven/{component_id}/totaal", response_class=HTMLResponse
)
async def inschrijf_totaal(
    activity_id: int, component_id: int, request: Request, db: Session = Depends(get_db)
):
    """Server-side herberekening bij elke wijziging (§19.3 — geen drift)."""
    from app.domains.activities.api import total_context

    activity, component = _component_or_404(db, activity_id, component_id)
    form = await request.form()
    return templates.TemplateResponse(
        request,
        "_inschrijf_totaal.html",
        total_context(_channel(request, db, activity, component), component, form),
    )


@router.post(
    "/activiteiten/{activity_id}/inschrijven/{component_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(registration_limiter)],
)
async def inschrijf_submit(
    activity_id: int,
    component_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """The public channel of the one form (#1284): the processing is shared with
    the board; what is decided here is only how the outcome is shown."""
    from app.domains.activities.api import OutcomeKind, public_registrations, submit

    activity, component = _component_or_404(db, activity_id, component_id)
    form = await request.form()
    outcome = submit(
        db, _channel(request, db, activity, component), activity, component, form, background_tasks
    )
    if outcome.kind is OutcomeKind.REFUSED:
        return templates.TemplateResponse(request, "_inschrijf_form.html", outcome.context)
    if outcome.kind is OutcomeKind.CHECKOUT:
        # Vaste UI-beslissing: harde redirect naar Mollie (nooit client-side route).
        response = templates.TemplateResponse(
            request, "_inschrijf_klaar.html", {"naam": outcome.name, "checkout": True}
        )
        response.headers["HX-Redirect"] = outcome.checkout_url
        return response
    # #1159: de deelnemerslijst staat BUITEN het swap-doel van dit formulier
    # (`closest .inschrijf-card`), dus ze bleef staan zoals ze bij het laden van
    # de pagina was — de verse inschrijving verscheen niet bij "Wie doet er mee?".
    # Zelfde vorm en zelfde antwoord als §8.4 van het design system: wat buiten
    # het doel staat, reist out-of-band mee met het antwoord (fragment-antwoord,
    # §8.2, #748). Alleen op dit pad: het betaalde pad verlaat de pagina.
    return templates.TemplateResponse(
        request,
        "_inschrijf_klaar.html",
        {
            "naam": outcome.name,
            "checkout": False,
            "activity_id": activity.id,
            "component_id": component.id,
            "deelnemers": public_registrations(db, activity.id, component.id),
        },
    )


@router.get("/activiteiten/{sleutel}")
def activiteit_deeplink(sleutel: str, request: Request, db: Session = Depends(get_db)):
    """Het kanonieke deeladres van één activiteit (golf 8, 15 sep 2026).

    Een vooraf gecommuniceerde link moet ook ná het evenement blijven werken,
    maar de kaart verhuist dan van /activiteiten naar het archief. Deze route
    zoekt de activiteit (slug of nummer, zoals de fotoalbums #884/#890) en
    stuurt door naar de juiste lijst mét het kaart-anker. Komt er ooit een
    volwaardige publieke activiteitspagina, dan neemt die dit adres over en
    breekt geen enkele oude link.

    Staat ná /activiteiten/archief geregistreerd, dus "archief" wint als pad.
    """

    from fastapi.responses import RedirectResponse

    from app.domains.activities.api import activity_by_key
    from app.ui import path_for

    activiteit = activity_by_key(db, sleutel)
    if activiteit is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    # Voorbij = de laatste (eind)datum ligt vóór vandaag — dezelfde blik als de
    # lijstscopes: zonder datums blijft ze op de komende lijst staan.
    laatste = max((d.end_date or d.start_date for d in activiteit.dates), default=None)
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
    vm = next((x for x in list_activities(db, scope=scope) if x.id == activiteit.id), None)
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
        poster_url = (
            activiteit.poster_asset_url + "/thumb"
            if activiteit.poster_asset_is_pdf
            else activiteit.poster_asset_url
        )
    elif activiteit.poster_url:
        poster_link = activiteit.poster_url
    # De klokregel bovenaan (#1051-copy: zonder jaartal, oranje in de laatste week)
    # rekende hier nog zelf uit welke datum en welke urgentie golden. Sinds #1053
    # staat dat in het view-model — `shared_deadline` en `shared_deadline_near`,
    # dezelfde velden die de kaart leest — en kan het sjabloon ze rechtstreeks
    # tonen. Eén bron: twee berekeningen van "de laatste week" lopen vroeg of laat
    # uiteen, en de datumopmaak zat hier bovendien met `rsplit` in plaats van via
    # de babel-filter.
    return templates.TemplateResponse(
        request,
        "activiteit.html",
        {
            **site_context(db, request),
            "a": vm,
            "scope": scope,
            "terug": "/activiteiten/archief" if voorbij else "/activiteiten",
            "poster_url": poster_url,
            "poster_link": poster_link,
        },
    )
