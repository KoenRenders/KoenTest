"""Server-rendered berichten-pagina (#398) — de micro-pilot van §21.4.

'Contacteer ons' als geseed formulier (slug 'berichten'): capture → submission
→ SubmissionCreated → behartigen-taak (workflow). Deze route is gespecialiseerd
op dat ene formulier; de generieke htmx-render van álle formulieren volgt met
de React-exit (#405).
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.forms.models import Form as FormModel
from app.limiter import form_submit_limiter
from app.ui import templates

router = APIRouter(include_in_schema=False)

BERICHTEN_SLUG = "berichten"


def _berichten_form(db: Session) -> FormModel | None:
    return db.query(FormModel).filter(FormModel.slug == BERICHTEN_SLUG).first()


@router.get("/berichten", response_class=HTMLResponse)
def berichten_page(request: Request, db: Session = Depends(get_db)):
    form = _berichten_form(db)
    return templates.TemplateResponse(request, "berichten.html", {"form": form, "error": None})


@router.post("/berichten", response_class=HTMLResponse,
             dependencies=[Depends(form_submit_limiter)])
def berichten_submit(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    naam: str = Form(""),
    email: str = Form(""),
    bericht: str = Form(""),
):
    form = _berichten_form(db)
    naam, email, bericht = naam.strip(), email.strip(), bericht.strip()
    if form is None:
        return templates.TemplateResponse(
            request, "_berichten_form.html",
            {"form": None, "error": "Berichten zijn tijdelijk niet beschikbaar.",
             "naam": naam, "email": email, "bericht": bericht})
    if not naam or not bericht:
        return templates.TemplateResponse(
            request, "_berichten_form.html",
            {"form": form, "error": "Vul je naam en je bericht in.",
             "naam": naam, "email": email, "bericht": bericht})

    from app.domains.forms.api import submit_bericht

    submit_bericht(db, naam=naam, email=email or None, bericht=bericht,
                   background_tasks=background_tasks)
    return templates.TemplateResponse(request, "_berichten_bedankt.html", {"naam": naam})
