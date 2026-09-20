"""Server-rendered mediabeheer (React-exit 405-d, #405 — §21).

Sponsors en activiteitenfoto's: uploaden (multipart via htmx), metadata
bewerken (titel, link, volgorde, actief) en verwijderen. Hergebruikt de
media-routerfuncties als servicelaag.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    admin_user_by_email, csrf_from_request,
    SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf,
)
from app.ui import admin_nav, is_fragment_request, templates
from app.i18n import _

router = APIRouter(include_in_schema=False)

NAV = admin_nav("/admin/media")


# #708: activiteitenfoto's zijn wat er dagelijks bijkomt; sponsorlogo's zet je
# eens per jaar. De standaard hoort de gewone handeling te zijn.
#
# Alle DRIE de plekken moeten mee — de lijst, het uploadscherm en de terugval in
# `_lijst_ctx`. "+ Uploaden" geeft de huidige filterstand door in de URL, dus
# verander je alleen het uploadscherm, dan overschrijft de lijst hem meteen weer en
# lijkt de wijziging niet te werken.
STANDAARD_KIND = "activity_photo"


def _filterstand(kind: str, q: str = "", activity_id: Optional[int] = None) -> str:
    """"Waar ik was", als query-string. De enige plek die dat adres samenstelt (#962).

    Soort, zoekterm en activiteit vormen samen de plek waar je stond, en die plek
    moet drie overgangen overleven: van de lijst naar het uploadscherm, van het
    uploadscherm terug, en van een mislukte upload terug naar hetzelfde scherm. Tot
    nu toe bouwde elk van die drie zijn eigen adres — de knop in het sjabloon, een
    verborgen veld en de redirect — en dat is precies hoe ze uit elkaar liepen: de
    foutafhandeling nam de filterstand wél mee, het geslaagde pad niet. De
    uitzondering zat dus op het pad dat je elke keer neemt.

    **Een activiteit reist alleen mee bij activiteitenfoto's.** Bij een sponsorlogo
    betekent ze niets — er is daar geen activiteitenfilter — en meesturen zou een
    parameter achterlaten die bij de volgende overgang weer opduikt. De regel staat
    hier en niet bij de drie aanroepers, want een regel die je op drie plaatsen moet
    onthouden is de fout die dit issue is.
    """
    from urllib.parse import urlencode

    params: list[tuple[str, str]] = [("kind", kind)]
    if q:
        params.append(("q", q))
    if activity_id and kind == "activity_photo":
        params.append(("activity_id", str(activity_id)))
    return urlencode(params)


def _lijst_ctx(request: Request, db: Session, kind: str, q: str = "",
               activity_id: Optional[int] = None) -> dict:
    from app.domains.activities.api import activity_options
    from app.domains.media.api import (VALID_KINDS, activity_ids_with_media,
                                       list_media)

    actief_kind = kind if kind in VALID_KINDS else STANDAARD_KIND
    if activity_id is None:
        # GET: het filter staat in de querystring. Bij een mutatie (POST) geeft de
        # kaart hem als verborgen veld mee, zodat het filter niet wegvalt.
        raw = request.query_params.get("activity_id")
        activity_id = int(raw) if raw and raw.isdigit() else None

    # Álle activiteiten (naam + jaar) voor de upload-dropdown (#476): je moet
    # foto's aan om het even welke activiteit kunnen koppelen, ook zonder foto's.
    #
    # `activity_options` en niet `list_activities` (#645): die laatste laadt datums,
    # onderdelen én producten eager en berekent de bezetting per onderdeel — een
    # lijstbewerking, hergebruikt om drie velden in een <select> te zetten. Dat
    # kostte dit scherm p95 578 ms tegen 9–122 ms voor de andere adminroutes.
    alle_activiteiten = [{"id": optie.id, "naam": optie.name,
                          "jaar": optie.first_date.year if optie.first_date else None}
                         for optie in activity_options(db)]
    # Filter-dropdown: enkel activiteiten die al media hebben (#459), mét jaar.
    aids = activity_ids_with_media(db)
    activiteiten = [a for a in alle_activiteiten if a["id"] in aids]

    # #891: bij activiteitenfoto's toont het scherm niets tot er een activiteit gekozen
    # is. Ongefilterd stond hier een lijst van alle albums door elkaar, met pijltjes die
    # iets doen wat je op dat scherm niet kán zien: de volgorde van een foto geldt binnen
    # HAAR album, en over activiteiten heen bestaat er geen volgorde.
    #
    # Dat is dezelfde tegenstrijdigheid die bij #882 opdook, waar de groepsgrens bewust
    # aan het asset zelf moest hangen en niet aan de getoonde lijst — juist omdát die
    # lijst ongefilterd geen bruikbare groep is. Dit haalt ze weg in plaats van ze te
    # omzeilen.
    #
    # ALLEEN voor deze soort: sponsors en component-info hangen niet aan een activiteit,
    # en daar is de volle lijst juist de bedoeling.
    kies_eerst = actief_kind == "activity_photo" and activity_id is None
    assets = [] if kies_eerst else list_media(db, kind=actief_kind,
                                              activity_id=activity_id)
    # Vrij zoeken op titel (C1, #588). Media zonder titel valt weg zodra er
    # gezocht wordt — dat is de bedoeling van een zoekterm.
    term = q.strip().lower()
    if term:
        # admin_list_media levert lichte metadata-dicts (_meta), geen ORM-objecten.
        assets = [a for a in assets if term in (a.get("title") or "").lower()]

    # Chip-labels horen per request opgebouwd: _() volgt de taal van de tenant.
    # Enkelvoud, want dezelfde labels voeden nu zowel het filter op de lijst als de
    # keuzelijst bij het uploaden (#258). "Sponsorlogo" leest in beide goed;
    # "Sponsors" deed dat niet in een keuzelijst waar je één soort kiest.
    kind_labels = {"sponsor": _("Sponsorlogo"),
                   "activity_photo": _("Activiteitenfoto"),
                   "tenant_logo": _("Logo van de vereniging")}
    # #882: de pijltjes moeten weten of dit item het eerste of laatste van ZIJN GROEP
    # is — niet van de lijst. Ongefilterd staan de foto's van alle activiteiten door
    # elkaar, dus de buur in de lijst hoort vaak bij een ander album.
    for groep_key in {(a["kind"], a["activity_id"], a["component_id"]) for a in assets}:
        groep = [a for a in assets
                 if (a["kind"], a["activity_id"], a["component_id"]) == groep_key]
        for positie, asset in enumerate(groep):
            asset["is_first"] = positie == 0
            asset["is_last"] = positie == len(groep) - 1

    return {"assets": assets, "q": q, "gefilterd": bool(term or activity_id),
            "kies_eerst": kies_eerst,
            "kind": actief_kind, "kinds": sorted(VALID_KINDS),
            "kind_options": [(k, kind_labels.get(k, k)) for k in sorted(VALID_KINDS)],
            "activity_id": activity_id, "activiteiten": activiteiten,
            "alle_activiteiten": alle_activiteiten,
            # Waar je stond, als één waarde (#962). Het sjabloon plakt er een pad
            # voor en stelt niets zelf samen — de knop die hem vergat, is de reden
            # dat je de activiteit drie keer moest kiezen.
            "filterstand": _filterstand(actief_kind, q, activity_id),
            "csrf_token": csrf_from_request(request)}


def _lijst_response(request: Request, db: Session, kind: str,
                    error: str | None = None, q: str = "",
                    activity_id: Optional[int] = None):
    """Enkel de kaarten (C1, #588): kop, knop en filterbalk staan op de pagina."""
    ctx = _lijst_ctx(request, db, kind, q, activity_id)
    ctx["error"] = error
    return templates.TemplateResponse(request, "_me_lijst.html", ctx)


@router.get("/admin/media", response_class=HTMLResponse)
def admin_media(request: Request, kind: str = STANDAARD_KIND, q: str = "",
                db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)):
    # htmx (de filterbalk) krijgt enkel de kaarten terug: een pagina-swap zou het
    # zoekveld tijdens het typen vervangen.
    if is_fragment_request(request):
        return _lijst_response(request, db, kind, q=q)
    return templates.TemplateResponse(request, "admin_media.html", {
        "nav_items": NAV, "error": None, **_lijst_ctx(request, db, kind, q)})


@router.get("/admin/media/nieuw", response_class=HTMLResponse)
def media_nieuw(request: Request, db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)):
    """Uploaden als volledige pagina (#627, §2.8) i.p.v. een modal.

    Hergebruikt de contextbouwer van de lijst: de dropdown met álle activiteiten en
    de huidige filterstand komen daaruit, zodat je na het uploaden terugkeert in
    dezelfde filtering.
    """
    # `kind` uit de query, zodat "+ Uploaden" vanaf de foto-filter meteen de
    # activiteit-dropdown toont (die hoort enkel bij activity_photo).
    kind = (request.query_params.get("kind") or STANDAARD_KIND).strip()
    ctx = _lijst_ctx(request, db, kind=kind)
    ctx["nav_items"] = NAV
    return templates.TemplateResponse(request, "admin_media_nieuw.html", ctx)


@router.post("/admin/media", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def media_uploaden(request: Request, db: Session = Depends(get_db),
                         email: str = Depends(require_admin_ui),
                         files: List[UploadFile] = File(...),
                         kind: str = Form("sponsor"),
                         activity_id: Optional[int] = Form(None),
                         title: str = Form(""), link_url: str = Form(""),
                         q: str = Form(""), filter_activity_id: Optional[int] = Form(None)):
    from app.domains.media.api import MediaFout, upload_media

    try:
        await upload_media(db, files=files, kind=kind, activity_id=activity_id,
                           title=title.strip() or None,
                           link_url=link_url.strip() or None)
    except (LookupError, MediaFout) as exc:
        # Op het aanmaakscherm blijven mét de fout (#627): een fragment terugsturen
        # naar een pagina die geen lijst toont, laat de gebruiker in het ongewisse.
        ctx = _lijst_ctx(request, db, kind=kind, q=q, activity_id=filter_activity_id)
        ctx["nav_items"] = NAV
        ctx["error"] = str(exc)
        return templates.TemplateResponse(request, "admin_media_nieuw.html", ctx)
    # Media is met één handeling compleet, dus terug naar de lijst (#627) — en naar
    # DEZELFDE lijst (#962). Hier stond een kaal `/admin/media`, dus je kwam terug in
    # de ongefilterde lijst en koos je activiteit een derde keer, terwijl het typische
    # gebruik nu juist is: foto's van één activiteit, in meerdere keren.
    #
    # `kind` is dat van de UPLOAD en niet van het filter waar je vandaan kwam: schakel
    # je op dit scherm om naar een sponsorlogo, dan hoort de lijst te tonen wat je net
    # toevoegde en niet de filtering waarin het onzichtbaar is.
    terug = _filterstand(kind, q, filter_activity_id)
    return Response(status_code=204,
                    headers={"HX-Redirect": f"/admin/media?{terug}"})


@router.post("/admin/media/{asset_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def media_bijwerken(asset_id: int, request: Request,
                    db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui),
                    kind: str = Form("sponsor"), title: str = Form(""),
                    link_url: str = Form(""), is_active: str = Form(""),
                    show_in_footer: str = Form(""),
                    q: str = Form(""), filter_activity_id: Optional[int] = Form(None)):
    """Titel, link en zichtbaarheid. NIET de volgorde (#882).

    `sort_order` stond hier tot #882 als formulierveld met default "0". Nu de pijltjes
    de volgorde bepalen, stuurt het formulier dat veld niet meer mee — en dan zou die
    default bij élke keer opslaan de volgorde op 0 zetten. Vandaar: `sort_order` staat
    niet in de payload, en `update_media` raakt alleen aan wat er wél in staat.
    """
    from app.domains.media.api import MediaFout, update_media

    try:
        update_media(db, asset_id, {
            "title": title.strip() or None, "link_url": link_url.strip() or None,
            "is_active": bool(is_active),
            # #1057: een niet-aangevinkt vakje stuurt niets mee, dus dit is altijd
            # de stand van het formulier — voor élke soort. Buiten een sponsorlogo
            # betekent de kolom niets en leest niemand haar.
            "show_in_footer": bool(show_in_footer),
        })
    except (LookupError, MediaFout) as exc:
        return _lijst_response(request, db, kind, str(exc), q, filter_activity_id)
    return _lijst_response(request, db, kind, q=q, activity_id=filter_activity_id)


@router.post("/admin/media/{asset_id}/verplaats", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def media_verplaatsen(asset_id: int, request: Request,
                      db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui),
                      kind: str = Form("sponsor"), richting: str = Form("omhoog"),
                      q: str = Form(""), filter_activity_id: Optional[int] = Form(None)):
    """Media omhoog/omlaag herordenen (#882) — dezelfde vorm als de vier andere
    schermen met `ui.reorder`."""
    from app.domains.media.api import move_media

    try:
        move_media(db, asset_id, richting)
    except LookupError as exc:
        return _lijst_response(request, db, kind, str(exc), q, filter_activity_id)
    return _lijst_response(request, db, kind, q=q, activity_id=filter_activity_id)


@router.post("/admin/media/{asset_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def media_verwijderen(asset_id: int, request: Request,
                      db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui),
                      kind: str = Form("sponsor"),
                      q: str = Form(""), filter_activity_id: Optional[int] = Form(None)):
    from app.domains.media.api import delete_media

    try:
        delete_media(db, asset_id)
    except LookupError as exc:
        return _lijst_response(request, db, kind, str(exc), q, filter_activity_id)
    return _lijst_response(request, db, kind, q=q, activity_id=filter_activity_id)
