"""Mijn gegevens: a person's own details on the public site (CR-22 S6a, #1710;
R16, R17, D6).

Name, mobile and e-mail addresses are attributes of ONE natural person, edited
in one way wherever the person appears: this page for oneself, and the person
block of Mijn gezin for every person of a household. So this page shows that
block (`membership`'s `_household_rows.html`, through `membership.api`) and
writes through the helpers of the household's one save
(`mdm.household_save.save_person`): a change here shows there at once, and the
other way round.

Not asked here: address, date of birth, gender (R17) — a member keeps those in
Mijn gezin.

A router of its own and not `mdm/ui.py`: that one answers only where the tenant
has members, and a tenant without members has accounts too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import _
from app.limiter import login_limiter
from app.ui import account_nav, refusal_response, site_context, templates
from app.ui.account_ui import signed_in_person, to_sign_in
from app.ui.viewmodel import ViewModel

router = APIRouter(tags=["ui-account"])

MY_DETAILS = "/mijn/gegevens"
#: Where a refused save is shown: the page's message line.
MESSAGE = "#gegevens-melding"


@dataclass(frozen=True, kw_only=True)
class MyDetailsPage(ViewModel):
    """`my_details.html`."""

    title: str
    #: The account menu and the page that is open in it.
    nav: list[dict]
    active: str
    #: The person block of Mijn gezin, for this one person (`membership.api`).
    block: Any
    edit: bool
    #: The page answers a save: it says "Opgeslagen ✓".
    saved: bool = False
    #: Where a member keeps address and household, None for whoever has none.
    household_href: Optional[str] = None


def _page(request: Request, db: Session, person, *, edit: bool, saved: bool = False):
    from app.domains.membership.api import person_block

    nav = account_nav(db, household=bool(person.member_persons))
    household = "/leden/gezin"
    in_menu = any(item["href"] == household for item in nav)
    page = MyDetailsPage(
        title=_("Mijn gegevens"),
        nav=nav,
        active=MY_DETAILS,
        block=person_block(person, edit=edit),
        edit=edit,
        saved=saved,
        household_href=household if in_menu and person.member_persons else None,
    )
    context = site_context(db, request)
    context.update(page.as_context())
    return templates.TemplateResponse(request, "my_details.html", context)


@router.get(MY_DETAILS, response_class=HTMLResponse)
def my_details(request: Request, db: Session = Depends(get_db)):
    signed_in, person = signed_in_person(request, db)
    if not signed_in:
        return to_sign_in(request)
    if person is None:
        # A session without a person here has no account pages (#1706).
        raise HTTPException(status_code=404)
    return _page(request, db, person, edit=request.query_params.get("bewerken") == "1")


@router.post(MY_DETAILS, response_class=HTMLResponse)
async def my_details_save(request: Request, db: Session = Depends(get_db)):
    """The page's one "Opslaan": the name, the mobile number and the e-mail rows
    in one transaction. A refusal writes nothing and leaves the form as typed;
    a good save answers the page in read mode."""
    from app.domains.auth.api import require_csrf
    from app.domains.mdm.api import (
        HouseholdSaveRefused,
        actor_of,
        household_from_form,
        save_person,
    )

    signed_in, person = signed_in_person(request, db)
    if not signed_in:
        raise HTTPException(status_code=401, detail=_("Niet aangemeld"))
    require_csrf(request)
    if person is None:
        raise HTTPException(status_code=404)
    payload = household_from_form(await request.form())
    try:
        save_person(db, person, payload.persons, actor=actor_of(person), errors=payload.errors)
    except HouseholdSaveRefused as refusal:
        return refusal_response(request, refusal.errors, MESSAGE)
    response = _page(request, db, person, edit=False, saved=True)
    response.headers["HX-Push-Url"] = MY_DETAILS
    return response


# ── A waiting e-mail address and its code (CR-22 S6b, #1711; R15, F6) ────────
#
# An address a person types himself — here or in Mijn gezin — waits for the
# code that was mailed to it. Its row offers two ways on: "Code invoeren" (the
# page below, with the one code step of the sign-in) and "Code opnieuw sturen".
# Both pages show the same row (`_household_rows.html`), so the two routes
# live here once, in the router a tenant without members has too.

ENTER_CODE = "/mijn/e-mailadres/{contact_id}/bevestigen"
SEND_CODE = "/mijn/e-mailadres/{contact_id}/code"


@dataclass(frozen=True, kw_only=True)
class ConfirmAddressPage(ViewModel):
    """`confirm_address.html`: the code step, for one waiting address."""

    title: str
    #: The address the code was sent to; the step sends it along with the code.
    email: str
    #: Where the step leads once the address counts.
    terug: str
    #: What the step's partial asks: no error on a fresh page, and the
    #: button's word ("Bevestigen", not "Inloggen").
    error: Optional[str] = None
    new_account: bool = True


def _back(request: Request) -> str:
    """The page the row stood on — Mijn gezin or Mijn gegevens — from where
    the browser says it came; this page when it does not say."""
    from urllib.parse import urlsplit

    from app.ui import veilige_terug

    came_from = request.headers.get("HX-Current-URL") or request.headers.get("referer") or ""
    path = urlsplit(came_from).path if came_from else ""
    return veilige_terug(path, MY_DETAILS)


@router.get(ENTER_CODE, response_class=HTMLResponse)
def confirm_address(contact_id: int, request: Request, db: Session = Depends(get_db)):
    from app.domains.mdm.api import waiting_address
    from app.ui import veilige_terug

    signed_in, person = signed_in_person(request, db)
    if not signed_in:
        return to_sign_in(request)
    address = waiting_address(db, person, contact_id) if person is not None else None
    if address is None:
        # Not this person's row, or it waits no more: the same answer.
        raise HTTPException(status_code=404)
    page = ConfirmAddressPage(
        title=_("Bevestig je e-mailadres"),
        email=address,
        terug=veilige_terug(request.query_params.get("terug"), "") or _back(request),
    )
    context = site_context(db, request)
    context.update(page.as_context())
    return templates.TemplateResponse(request, "confirm_address.html", context)


@router.post(SEND_CODE, response_class=HTMLResponse, dependencies=[Depends(login_limiter)])
def send_address_code(contact_id: int, request: Request, db: Session = Depends(get_db)):
    """ "Code opnieuw sturen": a new code, and on to the page that asks it.
    Limited like the sign-in: it sends a mail."""
    from urllib.parse import quote

    from app.domains.auth.api import require_csrf
    from app.domains.mdm.api import request_address_code

    signed_in, person = signed_in_person(request, db)
    if not signed_in:
        raise HTTPException(status_code=401, detail=_("Niet aangemeld"))
    require_csrf(request)
    if person is None or request_address_code(db, person, contact_id) is None:
        raise HTTPException(status_code=404)
    target = ENTER_CODE.format(contact_id=contact_id) + f"?terug={quote(_back(request), safe='/')}"
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = target
    return response
