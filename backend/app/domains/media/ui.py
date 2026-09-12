"""Publieke fotopagina's (React-exit 405-e, #405 — §21).

/fotos: albumoverzicht per jaar (gearchiveerde activiteiten met foto's, met
cover-thumbnail); /activiteiten/{id}/fotos: het album zelf. Server-rendered
in de SiteShell; hergebruikt de media-routerfuncties als servicelaag.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import form_submit_limiter
from app.ui import site_context, templates

router = APIRouter(include_in_schema=False)


@router.get("/fotos", response_class=HTMLResponse)
def fotos_overzicht(request: Request, db: Session = Depends(get_db)):
    from app.domains.activities.api import list_activities
    from app.domains.media.api import activity_photo_covers

    covers = {row["activity_id"]: row["thumb_url"]
              for row in activity_photo_covers(db)}
    albums = [a for a in list_activities(db, scope="archived") if a.id in covers]

    per_jaar: dict[int, list] = {}
    for album in albums:
        primair = album.sort_date or (album.dates[0].start_date if album.dates else None)
        jaar = primair.year if primair else 0
        per_jaar.setdefault(jaar, []).append(album)
    jaren = sorted(per_jaar, reverse=True)

    return templates.TemplateResponse(request, "fotos.html", {
        **site_context(db, request), "jaren": jaren, "per_jaar": per_jaar,
        "covers": covers})


# #883: de cookie die "één duimpje per bezoeker" mogelijk maakt.
#
# **Ze wordt pas gezet bij de eerste klik, nooit bij het bekijken van een pagina.** Dat is
# de kern van de afweging: zo is de opslag het directe gevolg van een handeling die de
# bezoeker zelf vraagt, en niet iets dat op het toestel van iemand belandt die niets
# gevraagd heeft. Zie de afsluitcomment van #883 voor de volledige uitleg; de beslissing
# over een toestemmingsbanner is aan Koen.
#
# HttpOnly: alleen de server leest ze. SameSite=Lax volstaat — dit is geen gevoelige
# handeling en een duimpje vanaf een externe link mag werken.
DUIM_COOKIE = "raak_duim"
DUIM_MAX_AGE = 60 * 60 * 24 * 180  # een half jaar


def _duim_token(request: Request) -> str | None:
    waarde = (request.cookies.get(DUIM_COOKIE) or "").strip()
    return waarde or None


@router.get("/activiteiten/{activity_key}/fotos", response_class=HTMLResponse)
def activiteit_fotos(activity_key: str, request: Request,
                     db: Session = Depends(get_db)):
    """Het album van één activiteit, op nummer ÓF op vriendelijke URL (#884).

    Het pad is een STRING en geen int: `/activiteiten/7/fotos` en
    `/activiteiten/zomerfeest-2026/fotos` leiden naar dezelfde pagina. De nummer-URL
    blijft werken omdat er nummer-URL's in verstuurde e-mails, WhatsApp-berichten en de
    zoekmachine staan.

    Precies één van de twee is canoniek: bestaat er een slug, dan is die het, en de
    nummer-URL verwijst ernaar. Anders indexeert Google beide adressen en verdeelt hij
    de waarde over twee pagina's — dan verzwak je wat je wilde versterken.
    """
    from app.domains.activities.api import activity_by_key
    from app.domains.media.api import list_activity_photos

    # Lazy, zoals elders: `_()` moet de taal van de actieve tenant volgen en niet die
    # van het importmoment.
    from app.i18n import _
    from app.kernel.tenant_config import tenant_base_url

    activiteit = activity_by_key(db, activity_key)
    if activiteit is None:
        raise HTTPException(status_code=404, detail=_("Activiteit niet gevonden"))
    activity_id = activiteit.id
    fotos = list_activity_photos(db, activity_id)
    from app.domains.media.api import thumb_counts, thumbs_of_visitor

    ids = [f["id"] for f in fotos]
    token = _duim_token(request)
    context = {**site_context(db, request), "activiteit": activiteit, "fotos": fotos,
               # #883: alleen AANTALLEN en "heb ik zelf geduimd" — nooit wie.
               "duimen": thumb_counts(db, ids),
               "eigen_duimen": thumbs_of_visitor(db, ids, token)}
    if activiteit is not None:
        # #881: de naam van het ALBUM in de voorbeschouwing, niet die van de site.
        context["og_title"] = _("Foto's — %(naam)s") % {"naam": activiteit.name}
        context["og_description"] = _(
            "Bekijk de foto's van %(naam)s.") % {"naam": activiteit.name}
    # #884: precies ÉÉN van de twee adressen is canoniek, en deze pagina zegt altijd
    # welke. Bestaat er een slug, dan is die het en wijst de nummer-URL ernaar; anders is
    # de nummer-URL zelf het canonieke adres. Zonder die uitspraak indexeert Google beide
    # en verdeelt hij de waarde over twee pagina's.
    #
    # `tenant_base_url` geeft de host waarop dit verzoek binnenkwam (#860), dus dit blijft
    # kloppen op elke omgeving en op een platform-host met pad-prefix. Bewust hier en niet
    # in `site_context`: daar hangt `canonical_url` aan de ingestelde `base_url`, en dat
    # gedrag verandert deze wijziging niet voor de rest van de site.
    _sleutel = activiteit.slug or activity_id
    context["canonical_url"] = f"{tenant_base_url(db)}/activiteiten/{_sleutel}/fotos"
    if fotos:
        # De VOLLEDIGE foto en niet de thumbnail: WhatsApp en Facebook wijzen kleine
        # beelden af of tonen ze onscherp. De eerste van het album (laagste
        # `sort_order`) — dezelfde volgorde die de pagina zelf toont.
        #
        # Absoluut, want een crawler lost een relatief pad niet op; `tenant_base_url`
        # geeft de host waarop dit verzoek binnenkwam (#860). En die URL is publiek:
        # `/api/v1/media/{id}` heeft geen sessie nodig, wat hier een eis is en geen
        # toeval — een crawler heeft er geen.
        context["og_image"] = f"{tenant_base_url(db)}{fotos[0]['url']}"
    return templates.TemplateResponse(request, "fotos_album.html", context)


@router.post("/fotos/{asset_id}/duim", response_class=HTMLResponse,
             dependencies=[Depends(form_submit_limiter)])
def foto_duim(asset_id: int, request: Request, db: Session = Depends(get_db)):
    """Duimpje aan of uit voor deze bezoeker (#883). Publiek, geen sessie.

    De cookie wordt HIER gezet als ze nog niet bestaat — bij de klik dus, en niet bij het
    bekijken van een albumpagina. Zonder token is er geen "één per bezoeker", en met een
    token dat bij elk paginabezoek gezet wordt sla je iets op bij iemand die niets
    gevraagd heeft.

    Een rem erop (`form_submit_limiter`): dit schrijft rijen en is publiek. Niet
    fraudebestendig — dat is aanvaard en staat in de omschrijving op het scherm — maar een
    script hoort niet ongelimiteerd rijen te kunnen maken.
    """
    import secrets

    from app.domains.media.api import toggle_thumb
    from app.i18n import _

    token = _duim_token(request) or secrets.token_urlsafe(32)
    try:
        aantal, aan = toggle_thumb(db, asset_id, token)
    except LookupError:
        raise HTTPException(status_code=404, detail=_("Foto niet gevonden"))

    antwoord = templates.TemplateResponse(request, "_duim.html", {
        "foto_id": asset_id, "aantal": aantal, "aan": aan})
    if _duim_token(request) is None:
        antwoord.set_cookie(DUIM_COOKIE, token, max_age=DUIM_MAX_AGE,
                            httponly=True, samesite="lax", path="/")
    return antwoord
