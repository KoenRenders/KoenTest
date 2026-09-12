"""Publieke fotopagina's (React-exit 405-e, #405 — §21).

/fotos: albumoverzicht per jaar (gearchiveerde activiteiten met foto's, met
cover-thumbnail); /activiteiten/{id}/fotos: het album zelf. Server-rendered
in de SiteShell; hergebruikt de media-routerfuncties als servicelaag.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
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


@router.get("/activiteiten/{activity_id}/fotos", response_class=HTMLResponse)
def activiteit_fotos(activity_id: int, request: Request,
                     db: Session = Depends(get_db)):
    from app.domains.activities.api import get_activity
    from app.domains.media.api import list_activity_photos

    # Lazy, zoals elders: `_()` moet de taal van de actieve tenant volgen en niet die
    # van het importmoment.
    from app.i18n import _
    from app.kernel.tenant_config import tenant_base_url

    activiteit = get_activity(db, activity_id)
    fotos = list_activity_photos(db, activity_id)
    context = {**site_context(db, request), "activiteit": activiteit, "fotos": fotos}
    if activiteit is not None:
        # #881: de naam van het ALBUM in de voorbeschouwing, niet die van de site.
        context["og_title"] = _("Foto's — %(naam)s") % {"naam": activiteit.name}
        context["og_description"] = _(
            "Bekijk de foto's van %(naam)s.") % {"naam": activiteit.name}
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
