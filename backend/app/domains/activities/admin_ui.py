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
    csrf_from_request,
    SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf,
)
from app.ui import admin_nav, is_fragment_request, templates
from app.domains.activities.viewmodels import AdminActiviteitenView
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


def _upload_error(exc: Exception) -> str:
    """Toon de upload-fout aan de beheerder i.p.v. ze stil te laten mislukken (htmx
    swapt niet op een 4xx). Bij een niet-ondersteund type een concrete hint —
    o.a. iPhone-HEIC-foto's worden niet aanvaard.

    Neemt zowel een HTTPException (uit de router-laag) als een gewone
    service-fout: sinds #635 I gooit de mediaservice `MediaFout`/`LookupError`.
    """
    detail = str(getattr(exc, "detail", exc))
    if "bestandstype" in detail.lower():
        return detail + " — " + _("gebruik een PNG, JPG, WEBP, GIF of PDF "
                                  "(een iPhone-HEIC-foto werkt niet).")
    return detail


def _verplaats(db: Session, siblings, item_id: int, richting: str) -> None:
    """Herorden broers/zussen via ``sort_order`` (#635 E/I)."""
    from app.domains.activities.api import move_within

    move_within(db, siblings, item_id, richting)


SCOPES = ("upcoming", "archived", "all")


def _lijst_ctx(db: Session, scope: str = "all", q: str = "") -> dict:
    """Lijst-context voor de records-lijst (C1, #586): scope-chips + vrij zoeken.

    Zoeken gebeurt op de reeds opgehaalde lijst i.p.v. in een tweede query: het
    zijn tientallen activiteiten, geen duizenden, en list_activities levert al de
    view-modellen mét telling en volzet-status waar de kaarten op steunen.
    """
    from app.domains.activities.api import list_activities

    if scope not in SCOPES:
        scope = "all"
    activiteiten = list_activities(db, scope=scope)
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


def _aa_detail_ctx(request: Request, db: Session, activiteit, error: str | None = None):
    """De context van `_aa_detail.html`, op één plek.

    Dat fragment wordt vanuit twee routes gerenderd: als volledige pagina
    (admin_activiteit.html omhult het) en als htmx-fragment na elke bewerking.
    Beide bouwden hun eigen dict, en zo'n paar drift: #650 voegde één sleutel toe
    en de paginaroute rende meteen op StrictUndefined.
    """
    # De zonder-onderdeel-kaart (#650) verdween in feedbackronde 2 van golf 8:
    # de Inschrijvingen-tab toont die inschrijvingen als groep "Zonder onderdeel",
    # dus ze blijven bereikbaar — de reden achter #650 blijft gedekt.
    return {
        "a": activiteit, "csrf_token": csrf_from_request(request), "error": error,
    }


def _detail_response(request: Request, db: Session, activity_id: int,
                     error: str | None = None, *, toast: bool = False):
    from app.domains.activities.api import get_activity_detail

    # #651: was `list_activities(scope="all")` + in Python filteren op id. Het
    # detail van één activiteit kostte zo meer dan de lijst van alle 167 (483 ms
    # tegen 89 ms op HDEV), en élke mutatie op dit scherm betaalde dat opnieuw.
    activiteit = get_activity_detail(db, activity_id)
    if activiteit is None:
        return HTMLResponse('<div id="aa-detail" hx-swap-oob="true"></div>')
    ctx = _aa_detail_ctx(request, db, activiteit, error)
    ctx["toast_opgeslagen"] = toast
    # HDEV-melding 15 sep: kop en rail staan buiten #aa-detail en bleven na een
    # opslag op de oude stand. Het fragment stuurt ze nu out-of-band mee; de
    # e-mail (voor de tab-rollen) komt uit de sessie die require_admin_ui al
    # gevalideerd heeft.
    from app.domains.auth.api import SESSION_COOKIE, read_session_value
    from app.domains.activities.api import registration_count_for
    from app.kernel.tenant_config import tenant_base_url

    email = read_session_value(request.cookies.get(SESSION_COOKIE))
    if email:
        reg_count = registration_count_for(db, activity_id)
        ctx.update(_record_tabs(activiteit, reg_count, db, email, "overzicht"))
        ctx.update(_record_rail(db, activiteit))
        ctx["deellink"] = (f"{tenant_base_url(db)}/activiteiten/"
                           f"{activiteit.slug or activity_id}")
        # Alleen op het FRAGMENT-antwoord: de volledige pagina rendert de kop
        # zelf al — een oob-blok zou hem daar dubbel zetten.
        ctx["oob_kop"] = True
    return templates.TemplateResponse(request, "_aa_detail.html", ctx)


@router.get("/admin/activiteiten", response_class=HTMLResponse)
def admin_activiteiten(request: Request, db: Session = Depends(get_db),
                       email: str = Depends(require_admin_ui),
                       scope: str = "upcoming", q: str = ""):
    lijst = _lijst_ctx(db, scope, q)
    # De kengetallen tellen wat er openstaat, niet wat er toevallig gefilterd is:
    # een zoekterm mag "Open inschrijvingen" niet doen dalen. Zonder filter is de
    # getoonde lijst al de juiste bron en blijft het bij één query.
    kpi_bron = (lijst["activities"] if (scope == "upcoming" and not q.strip())
                else _lijst_ctx(db, "upcoming")["activities"])
    # De filterbalk vraagt enkel de kaarten op; zou ze de pagina vervangen, dan
    # sneuvelt het zoekveld (en de focus) bij elke aanslag.
    fragment = is_fragment_request(request)
    view = AdminActiviteitenView(
        **lijst, **_kpi(kpi_bron),
        csrf_token=csrf_from_request(request),
        nav_items=[] if fragment else NAV,
    )
    sjabloon = "_aa_kaarten.html" if fragment else "admin_activiteiten.html"
    return templates.TemplateResponse(request, sjabloon, view.as_context())


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


@router.get("/admin/activiteiten/{activity_id}", response_class=HTMLResponse)
def admin_activiteit_detail(activity_id: int, request: Request,
                            db: Session = Depends(get_db),
                            email: str = Depends(require_admin_ui)):
    """Een kaart opent de paginabrede editor (C1, #586); de bewerkingen daarin
    blijven htmx-fragmenten die in #aa-detail landen."""
    if is_fragment_request(request):
        return _detail_response(request, db, activity_id)
    from app.domains.activities.api import get_activity_detail

    activiteit = get_activity_detail(db, activity_id)
    if activiteit is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    from app.domains.activities.api import registration_count_for

    from app.kernel.tenant_config import tenant_base_url

    reg_count = registration_count_for(db, activity_id)
    return templates.TemplateResponse(
        request, "admin_activiteit.html",
        {"nav_items": NAV, **_aa_detail_ctx(request, db, activiteit),
         **_record_tabs(activiteit, reg_count, db, email, "overzicht"),
         **_record_rail(db, activiteit),
         # De deellink (ronde 6): het kanonieke adres /activiteiten/<slug|nr> —
         # tijdsbestendig: de route stuurt zelf door naar de komende lijst of
         # het archief, dus een vooraf gedeelde link blijft ná het evenement
         # werken.
         "deellink": (f"{tenant_base_url(db)}/activiteiten/"
                      f"{activiteit.slug or activity_id}")})


@router.post("/admin/activiteiten", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def activiteit_aanmaken(request: Request, db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui),
                        name: str = Form(""), start_date: str = Form(""),
                        end_date: str = Form(""), start_time: str = Form(""),
                        end_time: str = Form(""),
                        location: str = Form(""), poster_url: str = Form(""),
                        members_only: str = Form("")):
    from app.domains.activities import service
    from app.schemas.activity import ActivityDateCreate

    if not name.strip() or not start_date:
        raise HTTPException(status_code=400, detail=_("Naam en eerste datum zijn verplicht."))
    # #792: the complete first row, the same four fields as `datum_toevoegen`. They
    # were thrown away here while both the schema and the model already accepted them —
    # this was not a missing feature but a narrower form.
    first_row = ActivityDateCreate(
        start_date=start_date, end_date=end_date or None,
        start_time=start_time or None, end_time=end_time or None)
    try:
        nieuw = service.create_activity(
            db, name=name.strip(), location=location.strip() or None,
            poster_url=poster_url.strip() or None, members_only=bool(members_only),
            dates=[first_row], actor=email)
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=422, detail=str(fout))
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
                               poster_url: str = Form(""), slug: str = Form(""),
                               members_only: str = Form(""), is_cancelled: str = Form(""),
                               file: Optional[UploadFile] = File(None)):
    """Bewerkt de activiteit; één "Opslaan" bewaart tekstvelden én de affiche (#623).

    `poster_url` was uit het scherm verdwenen terwijl het veld op het model en in de
    schemas bleef bestaan — je kon alleen nog uploaden. Beide horen in dezelfde vorm,
    zoals in v1.14: een geüploade affiche primeert op de URL (#223).
    """
    from app.domains.activities import service
    from app.domains.media.api import replace_activity_poster
    from app.schemas.activity import ActivityUpdate

    velden = ActivityUpdate(
        name=name.strip() or None, location=location.strip() or None,
        poster_url=poster_url.strip() or None,
        members_only=bool(members_only), is_cancelled=bool(is_cancelled),
    ).model_dump(exclude_none=True)
    # #884: de slug staat BUITEN `exclude_none`, want leegmaken is een geldige keuze —
    # dan verdwijnt de vriendelijke URL en blijft alleen de nummer-URL over. Hij volgt
    # de naam niet: wie hem wijzigt, doet dat met de waarschuwing op het scherm.
    velden["slug"] = slug.strip() or None
    try:
        bijgewerkt = service.update_activity(db, activity_id, velden, actor=email)
    except service.ActiviteitFout as fout:
        return _detail_response(request, db, activity_id, error=str(fout))
    if bijgewerkt is None:
        raise HTTPException(status_code=404, detail=_("Activity not found"))

    if file is not None and file.filename:
        try:
            await replace_activity_poster(db, activity_id, file, background_tasks)
        except (LookupError, HTTPException) as exc:
            return _detail_response(request, db, activity_id, error=_upload_error(exc))
    # #742: alleen deze afsluitende "Opslaan" bevestigt. De andere mutaties op dit
    # scherm (een datum toevoegen, een onderdeel bijwerken, een affiche wissen) zijn
    # deelacties en krijgen géén toast — dezelfde grens als bij #717.
    return _detail_response(request, db, activity_id, toast=True)


@router.post("/admin/activiteiten/{activity_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def activiteit_verwijderen(activity_id: int, request: Request,
                           db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui)):
    from app.domains.activities import service

    if not service.delete_activity(db, activity_id, actor=email):
        raise HTTPException(status_code=404, detail=_("Activity not found"))
    # Verwijderen gebeurt vanuit de editor; die pagina bestaat daarna niet meer.
    return Response(status_code=204, headers={"HX-Redirect": "/admin/activiteiten"})


# ── Datums ─────────────────────────────────────────────────────────────────────

@router.post("/admin/activiteiten/{activity_id}/datums", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def datum_toevoegen(activity_id: int, request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui),
                    start_date: str = Form(...), end_date: str = Form(""),
                    start_time: str = Form(""), end_time: str = Form("")):
    from app.domains.activities import service
    from app.schemas.activity import ActivityDateCreate

    gegevens = ActivityDateCreate(
        start_date=start_date, end_date=end_date or None,
        start_time=start_time or None, end_time=end_time or None)
    # #792: the same coherence rule as on the create screen — it sits on the object, so
    # this screen inherits it. Only the translation into HTTP belongs to the entrance,
    # which is why that part lives here.
    try:
        added = service.add_activity_date(db, activity_id, gegevens, actor=email)
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=422, detail=str(fout))
    if added is None:
        raise HTTPException(status_code=404, detail=_("Activity not found"))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/datums/{date_id}",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def datum_bijwerken(activity_id: int, date_id: int, request: Request,
                    db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui),
                    start_date: str = Form(...), end_date: str = Form(""),
                    start_time: str = Form(""), end_time: str = Form("")):
    """Bestaande datum (incl. begin-/einduur) bewerken — v1.14-pariteit."""
    from app.domains.activities import service
    from app.schemas.activity import ActivityDateUpdate

    velden = ActivityDateUpdate(
        start_date=start_date, end_date=end_date or None,
        start_time=start_time or None, end_time=end_time or None,
    ).model_dump(exclude_unset=True)
    try:
        updated = service.update_activity_date(db, activity_id, date_id, velden,
                                               actor=email)
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=422, detail=str(fout))
    if updated is None:
        raise HTTPException(status_code=404, detail=_("Date not found"))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/datums/{date_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def datum_verwijderen(activity_id: int, date_id: int, request: Request,
                      db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui)):
    from app.domains.activities import service

    if not service.delete_activity_date(db, activity_id, date_id, actor=email):
        raise HTTPException(status_code=404, detail=_("Date not found"))
    return _detail_response(request, db, activity_id)


# ── Onderdelen ─────────────────────────────────────────────────────────────────

@router.post("/admin/activiteiten/{activity_id}/onderdelen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def onderdeel_toevoegen(activity_id: int, request: Request,
                              background_tasks: BackgroundTasks,
                              db: Session = Depends(get_db),
                              email: str = Depends(require_admin_ui),
                              name: str = Form(...), team_name_required: str = Form(""),
                              max_participants: str = Form(""),
                              external_register_url: str = Form(""),
                              external_registrations_url: str = Form(""),
                              info_url: str = Form(""),
                              file: Optional[UploadFile] = File(None)):
    """Maakt het onderdeel; één "Toevoegen" bewaart de velden én de info-bijlage.

    De bijlage kon tot #715 pas ná het aanmaken opgeladen worden, via "Bewerken".
    Het toevoegformulier toonde enkel URL-velden en wekte zo de indruk dat een
    externe URL de enige weg was. Zelfde leest als ``onderdeel_bijwerken`` (#654):
    eerst de velden, dan het bestand als er een meegestuurd is.
    """
    from app.domains.activities import service
    from app.domains.media.api import replace_component_info
    from app.schemas.activity import ComponentCreate

    gegevens = ComponentCreate(
        name=name.strip(), team_name_required=bool(team_name_required),
        max_participants=_opt_int(max_participants),
        external_register_url=_opt_str(external_register_url),
        external_registrations_url=_opt_str(external_registrations_url),
        info_url=_opt_str(info_url))
    component = service.add_component(db, activity_id, gegevens, actor=email)
    if component is None:
        raise HTTPException(status_code=404, detail=_("Activity not found"))

    if file is not None and file.filename:
        try:
            await replace_component_info(db, component.id, file, background_tasks)
        except (LookupError, HTTPException) as exc:
            return _detail_response(request, db, activity_id, error=_upload_error(exc))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
async def onderdeel_bijwerken(activity_id: int, component_id: int, request: Request,
                              background_tasks: BackgroundTasks,
                              db: Session = Depends(get_db),
                              email: str = Depends(require_admin_ui),
                              name: str = Form(...), team_name_required: str = Form(""),
                              max_participants: str = Form(""),
                              external_register_url: str = Form(""),
                              external_registrations_url: str = Form(""),
                              info_url: str = Form(""),
                              file: Optional[UploadFile] = File(None)):
    """Bewerkt het onderdeel; één "Opslaan" bewaart tekstvelden én de info-bijlage.

    §2.12 verbood een eigen submit-knop bij het uploadveld al, maar dat was in #623
    alleen op de activiteit toegepast. Het onderdeel hield twee vormen naar twee
    endpoints en dus twee "Opslaan"-knoppen onder elkaar (#654). Zelfde leest als
    activiteit_bijwerken: eerst de velden, dan het bestand als er een meegestuurd is.

    De verwijderknop naast de bijlage blijft een aparte actie (/info/verwijderen):
    verwijderen is geen bewaarhandeling en hoort niet onder de gedeelde "Opslaan".
    """
    from app.domains.activities import service
    from app.domains.media.api import replace_component_info
    from app.schemas.activity import ComponentUpdate

    velden = ComponentUpdate(
        name=name.strip(), team_name_required=bool(team_name_required),
        max_participants=_opt_int(max_participants),
        external_register_url=_opt_str(external_register_url),
        external_registrations_url=_opt_str(external_registrations_url),
        info_url=_opt_str(info_url),
    ).model_dump(exclude_unset=True)
    if service.update_component(db, activity_id, component_id, velden,
                                actor=email) is None:
        raise HTTPException(status_code=404, detail=_("Component not found"))

    if file is not None and file.filename:
        try:
            await replace_component_info(db, component_id, file, background_tasks)
        except (LookupError, HTTPException) as exc:
            return _detail_response(request, db, activity_id, error=_upload_error(exc))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def onderdeel_verwijderen(activity_id: int, component_id: int, request: Request,
                          db: Session = Depends(get_db),
                          email: str = Depends(require_admin_ui)):
    from app.domains.activities import service

    if not service.delete_component(db, activity_id, component_id, actor=email):
        raise HTTPException(status_code=404, detail=_("Component not found"))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/verplaats",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def onderdeel_verplaatsen(activity_id: int, component_id: int, request: Request,
                          db: Session = Depends(get_db),
                          email: str = Depends(require_admin_ui),
                          richting: str = Form("omhoog")):
    """Onderdeel omhoog/omlaag herordenen (sort_order-wissel) — #451."""
    from app.domains.activities.api import get_activity

    activity = get_activity(db, activity_id)
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
    from app.domains.activities import service
    from app.schemas.activity import ProductCreate

    bedrag = _decimal(price)
    gegevens = ProductCreate(
        name=name.strip(), price=bedrag,
        member_price=_decimal(member_price) if member_price.strip() else None,
        is_free=(afrekening == "gratis"),
        pay_on_site=(afrekening == "ter_plaatse"),
        max_participants=_opt_int(max_participants))
    try:
        product = service.add_product(db, activity_id, component_id, gegevens,
                                      actor=email)
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=422, detail=str(fout))
    if product is None:
        raise HTTPException(status_code=404, detail=_("Component not found"))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/producten/{product_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def product_verwijderen(activity_id: int, component_id: int, product_id: int,
                        request: Request, db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui)):
    from app.domains.activities import service

    if not service.delete_product(db, component_id, product_id, actor=email):
        raise HTTPException(status_code=404, detail=_("Product not found"))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/producten/{product_id}/verplaats",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def product_verplaatsen(activity_id: int, component_id: int, product_id: int,
                        request: Request, db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui),
                        richting: str = Form("omhoog")):
    """Product omhoog/omlaag herordenen binnen zijn onderdeel (sort_order) — #451."""
    from app.domains.activities.api import get_component

    component = get_component(db, component_id, activity_id=activity_id)
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
    from app.domains.activities import service
    from app.schemas.activity import ProductUpdate

    bedrag = _decimal(price)
    velden = ProductUpdate(
        name=name.strip(), price=bedrag,
        member_price=_decimal(member_price) if member_price.strip() else None,
        is_free=(afrekening == "gratis"),
        pay_on_site=(afrekening == "ter_plaatse"),
        max_participants=_opt_int(max_participants),
    ).model_dump(exclude_unset=True)
    try:
        product = service.update_product(db, component_id, product_id, velden,
                                         actor=email)
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=422, detail=str(fout))
    if product is None:
        raise HTTPException(status_code=404, detail=_("Product not found"))
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/affiche", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def affiche_uploaden(activity_id: int, request: Request,
                           background_tasks: BackgroundTasks,
                           file: Optional[UploadFile] = File(None),
                           db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui)):
    """Affiche (poster) uploaden vanuit de activiteiten-admin (#451)."""
    from app.domains.media.api import replace_activity_poster

    if file is not None and file.filename:
        try:
            await replace_activity_poster(db, activity_id, file, background_tasks)
        except (LookupError, HTTPException) as exc:
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

    delete_activity_poster(db, activity_id)
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/info/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def onderdeel_info_verwijderen(activity_id: int, component_id: int, request: Request,
                               db: Session = Depends(get_db),
                               email: str = Depends(require_admin_ui)):
    """Info-bijlage van een onderdeel verwijderen (#623), via dezelfde media-facade."""
    from app.domains.media.api import delete_component_info

    delete_component_info(db, component_id)
    return _detail_response(request, db, activity_id)


@router.post("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/info",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
async def onderdeel_info_uploaden(activity_id: int, component_id: int, request: Request,
                             background_tasks: BackgroundTasks,
                             file: Optional[UploadFile] = File(None),
                             db: Session = Depends(get_db),
                             email: str = Depends(require_admin_ui)):
    """Info-bijlage (afbeelding of PDF) per onderdeel uploaden (#451).

    Heette "reglement" tot #623; één woord voor één ding (§2.13)."""
    from app.domains.media.api import replace_component_info

    if file is not None and file.filename:
        try:
            await replace_component_info(db, component_id, file, background_tasks)
        except (LookupError, HTTPException) as exc:
            return _detail_response(request, db, activity_id,
                                    error=_upload_error(exc))
    return _detail_response(request, db, activity_id)


# ── Gedeelde inschrijving-detail (betalingen + activiteiten-admin, #455/#451) ──

def _detail_ctx(request: Request, db: Session, registration_id: int,
                *, edit_open: bool = False, quantities: dict | None = None) -> dict | None:
    """Gedeelde context voor de inschrijving-detail/editor: de verrijkte
    inschrijving + de beschikbare producten van haar onderdeel (voor de
    'regel toevoegen'-keuze). Geeft None als de inschrijving niet bestaat."""
    from app.domains.activities.api import (enrich_registration, get_activity,
                                            get_registration)  # noqa: F401

    # include_deleted: een betaling is een financieel feit, dus de bewaarde naam
    # blijft zichtbaar ook als de inschrijving geschrapt is (#190).
    reg = get_registration(db, registration_id, include_deleted=True)
    if reg is None:
        return None
    activity = get_activity(db, reg.activity_id, include_deleted=True)
    products = []
    component = None
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
    # #670: met `quantities` rekent hij door op de aantallen uit het formulier,
    # zónder iets te bewaren — dat is de live-herberekening. Zonder is het de
    # bewaarde stand, zoals voorheen. Beide via totals.py, want een tweede
    # berekening in deze module is precies wat §19.3 uitsluit.
    from app.domains.activities.api import (compute_registration_total,
                                            quote_registration)

    totaal, regels = (quote_registration(reg, quantities) if quantities is not None
                      else compute_registration_total(reg))
    bedragen, idx = {}, 0
    for item in (reg.items or []):
        if getattr(item, "product", None) is None:
            continue
        if idx < len(regels):
            bedragen[item.id] = regels[idx]
        idx += 1

    verrijkt = enrich_registration(reg, activity)
    for regel in verrijkt["items"]:
        bedrag = bedragen.get(regel["id"])
        regel["unit_price"] = bedrag["unit_price"] if bedrag else None
        regel["line_total"] = bedrag["subtotal"] if bedrag else None
        # #732: ook het AANTAL moet meekomen, niet alleen de bedragen. Het antwoord
        # van /totaal vervangt het hele paneel — inclusief het veld waarin je net
        # typte — en `enrich_registration` zet daar de BEWAARDE stand in. Wie 2 naar
        # 1 bracht, kreeg dus een 1-prijs naast een 2 in het invoerveld, en bij
        # Opslaan stuurde het formulier die 2 terug: `inschrijving_opslaan` zag geen
        # verschil met de bewaarde waarde en bewaarde niets. De wijziging verdween
        # zonder melding.
        #
        # Zonder `quantities` blijft het de bewaarde stand — dat is het gewone
        # openen van het paneel — en dit endpoint bewaart nog steeds niets (#613-2).
        if quantities is not None and regel["id"] in quantities:
            regel["quantity"] = quantities[regel["id"]]

    return {
        "reg": verrijkt,
        "products": products,
        "totaal": totaal,
        # #716: de ploegnaam is bewerkbaar wanneer het onderdeel er een vraagt, óf
        # wanneer de inschrijving er al een heeft. Die tweede reden is nodig: gaat
        # `team_name_required` later af, dan blijft de bewaarde ploegnaam in de kop
        # staan en moet ze corrigeerbaar blijven. Zonder een van beide is het veld
        # enkel ruis.
        "toon_ploegnaam": bool(
            (component is not None and component.team_name_required)
            or verrijkt.get("team_name")),
        # #733: getoond en verplicht zijn twee dingen. Het veld verschijnt óók bij
        # een bewaarde ploegnaam op een onderdeel dat er geen vraagt — daar mag ze
        # wél leeggemaakt worden, dus daar hoort geen sterretje.
        "ploegnaam_verplicht": bool(component is not None
                                    and component.team_name_required),
        "editable": reg.deleted_at is None,
        "edit_open": edit_open,
        "csrf_token": csrf_from_request(request),
        # Golf 4 (#913): de paginavariant heeft de kop en de canonieke terugweg
        # nodig. Ze komen hiervandaan — activiteit en onderdeel zijn hierboven al
        # geladen — zodat de pagina ze niet zelf opnieuw afleidt.
        "activiteit_id": reg.activity_id,
        "activiteit_titel": activity.name if activity is not None else "",
        "component_naam": component.name if component is not None else None,
    }


def _render_detail(request: Request, db: Session, registration_id: int,
                   *, edit_open: bool = False, ververs: bool = False,
                   error: str | None = None, toast: str | None = None,
                   quantities: dict | None = None) -> HTMLResponse:
    """Rendert het detailfragment.

    ``edit_open`` houdt het paneel na een bewerking open (#613-3): het fragment
    vervangt zichzelf via outerHTML, dus zonder dit viel het terug in lees-modus en
    voelde het alsof er niets gebeurd was. Dat geldt voor de tussenacties; de
    afsluitende "Opslaan" sluit het paneel juist wél (#717).

    ``toast`` stuurt een bevestiging out-of-band mee. Deze functie is de enige plek
    die dit template rendert, dus die ene vlag volstaat om de toast weg te houden
    bij de detailroute, /totaal en /regels — die renderen hetzelfde fragment.

    ``ververs`` zet een ``HX-Trigger`` (#613-4/#617-3). De kaart erboven op
    /admin/betalingen staat buiten dit fragment en bleef op het oude bedrag staan —
    of toonde een nieuwe terugbetaling pas na F5 — terwijl de server al
    gereconcilieerd had. De betalingenlijst luistert op dat event.
    """
    ctx = _detail_ctx(request, db, registration_id, edit_open=edit_open,
                      quantities=quantities)
    if ctx is None:
        return HTMLResponse("")
    ctx["error"] = error
    ctx["toast_bericht"] = toast
    # Golf 8-feedback: op de eigen pagina draagt het cluster ook Verwijderen
    # (achter de bewerkklik, uiterst links). Of we óp die pagina zijn, zegt
    # HX-Current-URL — de POSTs van het fragment reizen daarmee.
    huidig = request.headers.get("HX-Current-URL", "")
    ctx["op_pagina"] = (f"/admin/inschrijvingen/{registration_id}" in huidig
                        and "/fragment" not in huidig)
    resp = templates.TemplateResponse(request, "_inschrijving_detail.html", ctx)
    if ververs:
        resp.headers["HX-Trigger"] = "betalingen-ververst"
    return resp


@router.get("/admin/inschrijvingen/{registration_id}/fragment",
            response_class=HTMLResponse)
def inschrijving_detail(registration_id: int, request: Request,
                        db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui)):
    """Detail/editor van één inschrijving (contact + producten + opmerking) als
    htmx-fragment. Herbruikbaar vanuit betalingen ('Toon inschrijvingsdetails')
    en de activiteiten-admin. Verrijking neemt soft-deleted mee (financieel feit);
    een soft-deleted inschrijving is niet bewerkbaar.

    Tot golf 4 (#913) woonde dit fragment op de id-URL zelf; die is nu van de
    volwaardige pagina hieronder (huispatroon: pagina op de id-URL, fragmenten op
    subpaden — zoals /admin/activiteiten/{id} naast zijn fragmentroutes)."""
    return _render_detail(request, db, registration_id)


@router.get("/admin/inschrijvingen/{registration_id}", response_class=HTMLResponse)
def inschrijving_pagina(registration_id: int, request: Request,
                        terug: str = "",
                        db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui)):
    """De inschrijving als volwaardige pagina (golf 4, #913 — B2).

    De recordnaam in een lijst opent deze pagina; het inline openvouwen blijft
    bestaan als secundaire variant (het fragment op /fragment). Zelfde bron:
    beide renderen `_inschrijving_detail.html` uit `_detail_ctx`.

    `terug` is de A7-retourcontext: de lijst die hierheen linkte geeft haar eigen
    adres mee, zodat de terugknop filters en sortering herstelt. Gevalideerd via
    `veilige_terug`; alles wat geen intern pad is valt terug op de canonieke plek
    van dit record — zijn activiteit."""
    from app.domains.activities.viewmodels import AdminInschrijvingView

    # De rij-knop in de lijsten heet sinds de feedback van 15 sep "Details" en
    # opent LEESmodus: de consistente Bewerken-opener (met Verwijderen in het
    # cluster) staat op de pagina zelf. De vroegere `bewerk=1` verdween daarmee.
    ctx = _detail_ctx(request, db, registration_id, edit_open=False)
    if ctx is None:
        raise HTTPException(status_code=404, detail=_("Inschrijving niet gevonden"))
    from app.domains.activities.api import inschrijving_kop_ctx

    # Kop (terugweg + label + tabs) uit de gedeelde bouwer — de ingebedde
    # Betalingen-tab rendert exact dezelfde kop.
    kop = inschrijving_kop_ctx(db, registration_id, email, "overzicht", terug)
    if kop is None:  # kan niet meer na de 404 hierboven; mypy weet dat niet
        raise HTTPException(status_code=404, detail=_("Inschrijving niet gevonden"))
    ctx.update(kop)
    vm = AdminInschrijvingView(
        **ctx, error=None, toast_bericht=None, op_pagina=True, nav_items=NAV)
    return templates.TemplateResponse(request, "admin_inschrijving.html",
                                      vm.as_context())


def _reg_or_404(db: Session, registration_id: int):
    from app.domains.activities.api import get_registration

    reg = get_registration(db, registration_id)
    if reg is None:
        raise HTTPException(status_code=404, detail=_("Inschrijving niet gevonden"))
    return reg


@router.post("/admin/inschrijvingen/{registration_id}/totaal",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
async def inschrijving_totaal(registration_id: int, request: Request,
                              db: Session = Depends(get_db),
                              email: str = Depends(require_admin_ui)):
    """Herberekent regelbedragen en totaal bij een gewijzigd aantal (#670).

    **Bewaart niets.** Er is bewust één "Opslaan" voor aantallen én opmerking
    (#613-2), en de autosave-op-change is daar destijds uitgehaald. Een
    live-endpoint dat stilletjes opslaat brengt die via de achterdeur terug, dus
    dit leest het formulier en rekent — meer niet. Daar staat een test op.

    Eigen endpoint en niet het publieke `/totaal`: dat laatste is open, dit vraagt
    `require_admin_ui` + CSRF. Het patroon is hetzelfde, de rekenkant is dezelfde
    (`totals.py`), alleen de deur verschilt.
    """
    formulier = await request.form()
    aantallen = {}
    for sleutel, waarde in formulier.items():
        # form.items() kan een UploadFile geven; alleen tekstvelden zijn aantallen —
        # zelfde guard als in inschrijving_opslaan.
        if not sleutel.startswith("quantity_") or not isinstance(waarde, str):
            continue
        try:
            aantallen[int(sleutel[len("quantity_"):])] = max(0, int(waarde))
        except ValueError:
            continue  # een leeg of onleesbaar veld laat het item op zijn eigen aantal
    return _render_detail(request, db, registration_id, edit_open=True,
                          quantities=aantallen)


@router.post("/admin/inschrijvingen/{registration_id}/opmerking",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def inschrijving_opmerking(registration_id: int, request: Request,
                           db: Session = Depends(get_db),
                           email: str = Depends(require_admin_ui),
                           remarks: str = Form("")):
    from app.domains.activities import service
    from app.schemas.activity import RegistrationContactUpdate

    reg = _reg_or_404(db, registration_id)
    velden = RegistrationContactUpdate(remarks=remarks).model_dump(exclude_unset=True)
    try:
        bijgewerkt = service.update_registration_contact(db, reg.activity_id,
                                                        registration_id, velden,
                                                        actor=email)
    except service.ActiviteitFout as fout:
        # #733 toetst op de uitkomst, dus ook een opmerking-opslag op een inschrijving
        # waar een verplicht veld al leeg stond loopt hier langs. In de banner, niet
        # als 500.
        return _render_detail(request, db, registration_id, edit_open=True,
                              error=str(fout))
    if bijgewerkt is None:
        raise HTTPException(status_code=404, detail=_("Registration not found"))
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
    from app.domains.activities import service
    from app.schemas.activity import RegistrationContactUpdate

    reg = _reg_or_404(db, registration_id)
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
        try:
            gewijzigd = service.update_order_line(db, reg.activity_id, registration_id,
                                                  item_id, quantity=aantal, actor=email)
        except service.ActiviteitFout as fout:
            raise HTTPException(status_code=400, detail=str(fout))
        if gewijzigd is None:
            raise HTTPException(status_code=404, detail=_("Order line not found"))

    # Contactgegevens meenemen in dezelfde "Opslaan" (#624). Enkel wat het formulier
    # meestuurt wordt gewijzigd; de route laat de rest ongemoeid.
    contact = {"remarks": str(form.get("remarks") or "")}
    for veld in ("contact_name", "contact_email", "phone", "team_name"):
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
    try:
        bijgewerkt = service.update_registration_contact(
            db, reg.activity_id, registration_id,
            gegevens.model_dump(exclude_unset=True), actor=email)
    except service.ActiviteitFout as fout:
        # #733: een verplicht veld leeggemaakt. In de bestaande foutbanner en met een
        # 200, want htmx swapt een 4xx niet — dan zou de gebruiker niets zien
        # gebeuren, precies zoals bij een ongeldig e-mailadres hierboven.
        return _render_detail(request, db, registration_id, edit_open=True,
                              error=str(fout))
    if bijgewerkt is None:
        raise HTTPException(status_code=404, detail=_("Registration not found"))
    # #717: dit is de afsluitende handeling, geen tussenstap. Openblijven gaf
    # hetzelfde scherm terug als vóór de klik — zelfde velden, zelfde knop, geen
    # enkel teken dat er bewaard was — en dus de reflex om nog eens te klikken.
    # Sluiten alleen volstaat niet (dan zie je leesmodus zonder bevestiging), een
    # toast alleen ook niet (dan blijft de knop staan). De tussenacties hierboven
    # en hieronder houden edit_open=True: dat is #613-3 en blijft gelden.
    return _render_detail(request, db, registration_id, ververs=True,
                          toast=_("De inschrijving is opgeslagen."))


@router.post("/admin/inschrijvingen/{registration_id}/regels",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def inschrijving_regel_toevoegen(registration_id: int, request: Request,
                                 db: Session = Depends(get_db),
                                 email: str = Depends(require_admin_ui),
                                 product_id: str = Form(""),
                                 quantity: int = Form(1)):
    """Voegt een regel toe. Aparte actie, buiten de ene "Opslaan" (#613-2).

    `product_id` is sinds #670 optioneel op HTTP-niveau. De keuzelijst staat nu in
    hetzelfde formulier als de aantallen — geneste formulieren bestaan niet — dus
    ze kan geen `required` dragen zonder óók Opslaan te blokkeren wanneer er niets
    gekozen is. De controle staat daarom hier, met een leesbare melding in plaats
    van een 422.
    """
    from app.domains.activities import service

    reg = _reg_or_404(db, registration_id)
    if not (product_id or "").strip():
        return _render_detail(request, db, registration_id, edit_open=True,
                              error=_("Kies eerst een product om toe te voegen."))
    gekozen = int(product_id)
    try:
        toegevoegd = service.add_order_line(db, reg.activity_id, registration_id,
                                            gekozen, quantity, actor=email)
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=400, detail=str(fout))
    if toegevoegd is None:
        raise HTTPException(status_code=404, detail=_("Registration not found"))
    return _render_detail(request, db, registration_id, edit_open=True, ververs=True)


@router.post("/admin/inschrijvingen/{registration_id}/regels/{item_id}",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def inschrijving_regel_bijwerken(registration_id: int, item_id: int, request: Request,
                                 db: Session = Depends(get_db),
                                 email: str = Depends(require_admin_ui),
                                 quantity: int = Form(...)):
    from app.domains.activities import service

    reg = _reg_or_404(db, registration_id)
    try:
        gewijzigd = service.update_order_line(db, reg.activity_id, registration_id,
                                              item_id, quantity=quantity, actor=email)
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=400, detail=str(fout))
    if gewijzigd is None:
        raise HTTPException(status_code=404, detail=_("Order line not found"))
    return _render_detail(request, db, registration_id, edit_open=True, ververs=True)


@router.post("/admin/inschrijvingen/{registration_id}/regels/{item_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def inschrijving_regel_verwijderen(registration_id: int, item_id: int, request: Request,
                                   db: Session = Depends(get_db),
                                   email: str = Depends(require_admin_ui)):
    from app.domains.activities import service

    reg = _reg_or_404(db, registration_id)
    if service.delete_order_line(db, reg.activity_id, registration_id, item_id,
                                 actor=email) is None:
        raise HTTPException(status_code=404, detail=_("Order line not found"))
    return _render_detail(request, db, registration_id, edit_open=True, ververs=True)


# ── Inschrijvingen + export ────────────────────────────────────────────────────

# Sorteersleutels voor de inschrijvingenlijst (golf 4, #913 — zelfde regels als de
# golf 3-referentie op het e-maillog): een whitelist omdat de sleutel uit de
# querystring komt, en elke ordening eindigt op id (#761) zodat gelijke waarden een
# stabiele volgorde houden. Python-side, zoals ledenwijzigingen: de lijst is al
# verrijkt tot dicts wanneer hij hier aankomt.
# De sorteer-whitelist verhuisde naar de service (sorteer_inschrijvingen):
# de gezinstab sorteert sinds de unificatie met exact dezelfde sleutels.


def _record_tabs(activiteit, reg_count: int, db, email: str, actief: str) -> dict:
    """Doorgeefluik naar de ene tabs-bouwer in de service (golf 8, #913):
    de payment-kant rendert dezelfde recordkop en mag alleen via de facade."""
    from app.domains.activities.api import record_tabs
    from app.kernel.tenant_config import tenant_admin_chat_enabled

    # Golf 10 (#913): de "AI · Activiteit"-knop in de recordkop bestaat alleen
    # als Raakje voor beheer aan staat — één bron (kernel, CR-07 §6.3), geen
    # eigen vlag ernaast.
    return {"record_tabs": record_tabs(db, activiteit, email, actief,
                                       reg_count=reg_count),
            "raakje_admin": tenant_admin_chat_enabled(db)}


def _record_rail(db, activiteit) -> dict:
    """De rechterrail van de recordpagina: publicatie-info en bezetting per
    onderdeel — via dezelfde telling als de volzet-berekening (#451), in één
    query (#651: het detailscherm haalt niet de hele boom op)."""
    from app.domains.activities.api import booked_per_component

    bezetting = booked_per_component(db, [activiteit.id])
    onderdelen = [{
        "naam": c.name,
        "bezet": bezetting.get(c.id, 0),
        "max": c.max_participants,
    } for c in activiteit.sub_registrations]
    # "Inschrijvingen totaal" verdween op Koens vraag (15 sep): het aantal
    # staat al op de tab.
    return {"rail_onderdelen": onderdelen}


@router.get("/admin/activiteiten/{activity_id}/inschrijvingen",
            response_class=HTMLResponse)
def activiteit_inschrijvingen_tab(activity_id: int, request: Request,
                                  sort: str = "datum", richting: str = "asc",
                                  db: Session = Depends(get_db),
                                  email: str = Depends(require_admin_ui)):
    """De Inschrijvingen-tab van de recordpagina (golf 8, #913): álle
    inschrijvingen van de activiteit, over de onderdelen heen, met een
    Onderdeel-kolom en de golf 4-sorteermachinerie."""
    from urllib.parse import quote

    from app.domains.activities.api import (
        INSCHRIJVING_SORT_VELDEN, get_activity, registrations_for,
        sorteer_inschrijvingen,
    )
    from app.domains.activities.viewmodels import AdminActiviteitInschrijvingenView

    activiteit = get_activity(db, activity_id)
    if activiteit is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    regs = registrations_for(db, activity_id, alle=True) or []
    regs, sort, richting = sorteer_inschrijvingen(regs, sort, richting)

    # Feedbackronde 2 (15 sep): gegroepeerd per onderdeel, open/dichtklapbaar,
    # met een exportknop per groep — de Overzicht-knoppen zijn hierheen
    # verhuisd. De sortering geldt bínnen elke groep. "Zonder onderdeel"
    # achteraan: zo blijven ook die bereikbaar (de reden achter #650).
    # Groepssleutels altijd compleet (datum/titel_url None): het gedeelde
    # sjabloon rendert onder StrictUndefined.
    groepen = []
    for c in activiteit.sub_registrations:
        rijen = [r for r in regs if r["component_id"] == c.id]
        groepen.append({
            "naam": c.name, "aantal": len(rijen), "regs": rijen,
            "export_href": (f"/admin/activiteiten/{activity_id}"
                            f"/onderdelen/{c.id}/export"),
            "titel_url": None, "datum": None})
    zonder = [r for r in regs if r["component_id"] is None]
    if zonder:
        groepen.append({"naam": _("Zonder onderdeel"), "aantal": len(zonder),
                        "regs": zonder, "export_href": None,
                        "titel_url": None, "datum": None})

    basis = f"/admin/activiteiten/{activity_id}/inschrijvingen"
    sorteer_urls = {
        naam: (f"{basis}?sort={naam}&richting="
               + ("desc" if sort == naam and richting == "asc" else "asc"))
        for naam in INSCHRIJVING_SORT_VELDEN}
    terug = quote(f"{basis}?sort={sort}&richting={richting}", safe="")
    vm = AdminActiviteitInschrijvingenView(
        a=activiteit, groepen=groepen, totaal=len(regs),
        sort=sort, richting=richting, sorteer_urls=sorteer_urls,
        terug=terug, toon_onderdeel=False,
        **_record_tabs(activiteit, len(regs), db, email, "inschrijvingen"),
        csrf_token=csrf_from_request(request), nav_items=NAV)
    return templates.TemplateResponse(
        request, "admin_activiteit_inschrijvingen.html", vm.as_context())


@router.post("/admin/activiteiten/{activity_id}/inschrijvingen/{registration_id}/verwijderen",
             response_class=HTMLResponse, dependencies=[Depends(require_csrf)])
def inschrijving_verwijderen(activity_id: int, registration_id: int, request: Request,
                             component_id: int | None = None,
                             sort: str = "datum", richting: str = "asc",
                             vanuit: str = "",
                             db: Session = Depends(get_db),
                             email: str = Depends(require_admin_ui)):
    """Verwijdert een inschrijving en keert terug naar de activiteit.

    Sinds feedbackronde 2 van golf 8 is de inschrijvingspagina (cluster,
    uiterst links) de enige plek met een verwijderknop — de lijstfragmenten
    met een directe rij-delete bestaan niet meer. De oude parameters blijven
    aanvaard zodat bestaande links geen 422 geven."""
    from app.domains.activities import service

    if not service.delete_registration(db, activity_id, registration_id, actor=email):
        raise HTTPException(status_code=404, detail=_("Registration not found"))
    return Response(status_code=204, headers={
        "HX-Redirect": f"/admin/activiteiten/{activity_id}"})


@router.get("/admin/activiteiten/{activity_id}/onderdelen/{component_id}/export")
def onderdeel_export(activity_id: int, component_id: int, request: Request,
                     db: Session = Depends(get_db),
                     email: str = Depends(require_admin_ui)) -> Response:
    from app.domains.activities import service

    resultaat = service.component_export(db, activity_id, component_id)
    if resultaat is None:
        raise HTTPException(status_code=404, detail=_("Component not found"))
    inhoud, bestandsnaam = resultaat
    return Response(
        content=inhoud,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={"Content-Disposition": f'attachment; filename="{bestandsnaam}"'})
