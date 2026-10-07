"""Mijn inschrijvingen: the account page of the activities (CR-22 S5, #1709;
R8, R14). The registrations of the signed-in person — or of his household —
each with its payment state. Which registrations, and how each stands, is
`activities.api.my_registrations`; this module only shows them.

No id comes from the URL: the list is asked for the person of the session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import _
from app.ui import account_nav, site_context, templates
from app.ui.account_ui import signed_in_person, to_sign_in
from app.ui.viewmodel import ViewModel

router = APIRouter(tags=["ui-account"])

MY_REGISTRATIONS = "/mijn/inschrijvingen"


@dataclass(frozen=True, kw_only=True)
class MyRegistrationsPage(ViewModel):
    """`my_registrations.html`."""

    title: str
    nav: list[dict]
    active: str
    #: `MyRegistration` rows, newest first.
    registrations: list[Any]


@router.get(MY_REGISTRATIONS, response_class=HTMLResponse)
def my_registrations_page(request: Request, db: Session = Depends(get_db)) -> Response:
    from app.domains.activities.api import my_registrations

    signed_in, person = signed_in_person(request, db)
    if not signed_in:
        return to_sign_in(request)
    if person is None:
        # A session without a person here has no account pages (#1706).
        raise HTTPException(status_code=404)
    page = MyRegistrationsPage(
        title=_("Mijn inschrijvingen"),
        nav=account_nav(db),
        active=MY_REGISTRATIONS,
        registrations=my_registrations(db, person),
    )
    context = site_context(db, request)
    context.update(page.as_context())
    return templates.TemplateResponse(request, "my_registrations.html", context)
