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
    from app.domains.media.router import activity_photo_covers

    covers = {row["activity_id"]: row["thumb_url"]
              for row in activity_photo_covers(db=db)}
    albums = [a for a in list_activities(db, scope="archived") if a.id in covers]

    per_jaar: dict[int, list] = {}
    for album in albums:
        primair = album.sort_date or (album.dates[0].start_date if album.dates else None)
        jaar = primair.year if primair else 0
        per_jaar.setdefault(jaar, []).append(album)
    jaren = sorted(per_jaar, reverse=True)

    return templates.TemplateResponse(request, "fotos.html", {
        **site_context(db), "jaren": jaren, "per_jaar": per_jaar,
        "covers": covers})


@router.get("/activiteiten/{activity_id}/fotos", response_class=HTMLResponse)
def activiteit_fotos(activity_id: int, request: Request,
                     db: Session = Depends(get_db)):
    from app.domains.activities.api import Activity
    from app.domains.media.router import list_activity_photos

    activiteit = db.query(Activity).filter(Activity.id == activity_id).first()
    fotos = list_activity_photos(activity_id, db=db)
    return templates.TemplateResponse(request, "fotos_album.html", {
        **site_context(db), "activiteit": activiteit, "fotos": fotos})
