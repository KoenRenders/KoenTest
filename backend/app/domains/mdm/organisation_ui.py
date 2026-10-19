"""Mijn organisatie: the organisation a signed-in person acts for, on the public
site (CR-26 F7, F14, phase 2; Koen, 15 October 2026: a company buys through a
signed-in person who registers the organisation once).

The router is included under `require_module(INVOICES)` (F14): at a tenant
without the module the page does not exist, and nor does *namens* in the
checkout. It lives in `mdm`, which is core, and its prefix stands in the module's
`route_prefixes`, so the module gate sees it.

Register: name, legal form, VAT number (required), address. A VAT number already
registered in the account **links** the person to that organisation and writes
nothing (the first person's data stands). *Ontkoppelen* ends the relation with an
end date; the organisation and its old orders stay.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import _
from app.kernel.refusals import FieldError
from app.ui import account_nav, refusal_response, site_context, templates
from app.ui.account_ui import signed_in_person, to_sign_in
from app.ui.viewmodel import ViewModel

router = APIRouter(tags=["ui-account"])

MY_ORGANISATION = "/mijn/organisatie"
#: Where a refused save is shown: the page's message line.
MESSAGE = "#organisatie-melding"


@dataclass(frozen=True, kw_only=True)
class MyOrganisationPage(ViewModel):
    """`my_organisation.html`."""

    title: str
    nav: list[dict]
    active: str
    #: The organisations this person acts for now: id, name, vat_number, legal_form label.
    organisations: list[dict]
    legal_forms: list[tuple[str, str]]
    postal_options: list[tuple[str, str]]
    #: What was typed, for a refused form; empty on a fresh page.
    values: dict = field(default_factory=dict)
    #: The page answers a good save: "Opgeslagen ✓", and says whether it linked.
    saved: bool = False
    linked: bool = False


def _page(request: Request, db: Session, person, *, values=None, saved=False, linked=False):
    from app.domains.mdm.api import (
        legal_form_options,
        list_postal_codes,
        organisations_acting_for,
    )

    forms = dict(legal_form_options(db))
    organisations = [
        {**o, "legal_form_label": forms.get(o["legal_form"], "")}
        for o in organisations_acting_for(db, person.id)
    ]
    postal = [
        (pc.postal_code, f"{pc.postal_code} {pc.municipality}") for pc in list_postal_codes(db)
    ]
    page = MyOrganisationPage(
        title=_("Mijn organisatie"),
        nav=account_nav(db, household=bool(person.member_persons)),
        active=MY_ORGANISATION,
        organisations=organisations,
        legal_forms=[("", _("— Geen —"))] + list(forms.items()),
        postal_options=[("", _("— Kies een postcode —"))] + postal,
        values=values or {},
        saved=saved,
        linked=linked,
    )
    context = site_context(db, request)
    context.update(page.as_context())
    return templates.TemplateResponse(request, "my_organisation.html", context)


@router.get(MY_ORGANISATION, response_class=HTMLResponse)
def my_organisation(request: Request, db: Session = Depends(get_db)):
    signed_in, person = signed_in_person(request, db)
    if not signed_in:
        return to_sign_in(request)
    if person is None:
        raise HTTPException(status_code=404)
    return _page(request, db, person)


@router.post(MY_ORGANISATION, response_class=HTMLResponse)
async def register_my_organisation(request: Request, db: Session = Depends(get_db)):
    """Register an organisation, or link to the one the VAT number already names.
    A refusal writes nothing and leaves the form as typed."""
    from app.domains.auth.api import require_csrf
    from app.domains.mdm.api import OngeldigeInstelling, register_organisation

    signed_in, person = signed_in_person(request, db)
    if not signed_in:
        raise HTTPException(status_code=401, detail=_("Niet aangemeld"))
    require_csrf(request)
    if person is None:
        raise HTTPException(status_code=404)
    form = {key: str(value) for key, value in (await request.form()).items()}
    try:
        _id, created = register_organisation(db, person.id, form, actor=f"person:{person.id}")
    except OngeldigeInstelling as refusal:
        return refusal_response(
            request,
            [FieldError(name, message) for name, message in refusal.fouten.items()],
            MESSAGE,
        )
    response = _page(request, db, person, saved=True, linked=not created)
    response.headers["HX-Push-Url"] = MY_ORGANISATION
    return response


@router.post(MY_ORGANISATION + "/{organization_id}/ontkoppelen", response_class=HTMLResponse)
def unlink_my_organisation(organization_id: int, request: Request, db: Session = Depends(get_db)):
    """Ontkoppelen: the relation ends today. The organisation stays, with its
    orders; the person acts for it no more."""
    from app.domains.auth.api import require_csrf
    from app.domains.mdm.api import end_acts_for

    signed_in, person = signed_in_person(request, db)
    if not signed_in:
        raise HTTPException(status_code=401, detail=_("Niet aangemeld"))
    require_csrf(request)
    if person is None or not end_acts_for(db, person.id, organization_id):
        raise HTTPException(status_code=404)
    db.commit()
    return _page(request, db, person)
