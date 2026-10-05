"""The member's own screens: Word lid, Mijn gezin and renewing the membership.

Since CR-11 pilot B (#1590; end state §2.6) the three stand on the public form
page: a column of section cards with one action bar. The household is one
picture on all three (`household_page`): its persons as a repeating group with
their e-mail addresses, and the address.

- **Word lid** (`/lid-worden`) creates a household. The form is read by
  `signup_form`; creating it stays `register_family`'s (deduplication, price
  rules, mail, audit). A refusal answers the banner alone, with every refused
  field named — the page keeps what was typed.
- **Mijn gezin** (`/leden/gezin`) is read first; `?bewerken=1` is the edit mode,
  whose one "Opslaan" is `mdm`'s door (`POST /leden/gezin`, `mdm/ui.py`): the
  household and its persons are master data. The page stays this module's.
- **Renewing** (`/leden/gezin/vernieuwen`) is its own act on its own page.

Postal code always a select (fixed UI decision); an online payment leaves with a
hard redirect (`HX-Redirect`).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.mdm.api import PaymentMethod
from app.i18n import _
from app.limiter import registration_limiter
from app.ui import refusal_response, site_context, templates

router = APIRouter(include_in_schema=False)

#: The message lines of the three pages: where a refused send or save is shown.
SIGNUP_MESSAGE = "#lid-worden-melding"
RENEW_MESSAGE = "#vernieuw-melding"


def _codes(db: Session) -> dict:
    """De keuzelijsten voor de formulieren — inclusief de ontdubbeling per code,
    die in de service woont omdat ze uit de tenant-scheiding volgt (#635 I)."""
    from app.domains.mdm.api import form_code_lists

    return form_code_lists(db)


def _signup_terms():
    """Price and validity for the Word lid page (F3, #996): the same helpers the
    sign-up itself uses, so the screen and the booking cannot differ."""
    from app.domains.membership.household_page import Terms
    from app.domains.payment.api import membership_price_for_date, membership_valid_period

    _from, until = membership_valid_period()
    return Terms(amount=membership_price_for_date(), valid_to=until)


def _signup_page(request: Request, db: Session, **state) -> HTMLResponse:
    from app.domains.membership.household_page import SignupPage, signup_group

    page = SignupPage(group=signup_group(_codes(db)), terms=_signup_terms(), **state)
    return templates.TemplateResponse(
        request, "lid_worden.html", {**site_context(db, request), "page": page}
    )


@router.get("/lid-worden", response_class=HTMLResponse)
def lid_worden(request: Request, db: Session = Depends(get_db)):
    return _signup_page(request, db)


@router.get("/lid-worden/relatie", response_class=PlainTextResponse)
def signup_relation(others: str = ""):
    """The relation a person added on the Word lid page starts with (#1321, #1590):
    the one rule's answer, given the relations already chosen after the main
    member. The page asks instead of knowing, so the rule stays in one place."""
    from app.domains.mdm.api import RelationType
    from app.domains.membership.api import default_relation

    earlier = [RelationType.PRIMARY_MEMBER.value] + [r for r in others.split(",") if r]
    return default_relation(earlier)


@router.get("/lid-worden/email-rij", response_class=HTMLResponse)
def email_row(request: Request):
    """One extra e-mail row of the board's "new member" form (#1246), which still
    builds its persons from `_lid_persoon_rij.html`. The public page no longer
    asks for it: its rows are the kit's repeating group (#1590)."""

    def _int(name: str, default: int, minimum: int) -> int:
        try:
            return max(minimum, int(request.query_params.get(name, default)))
        except ValueError:
            return default

    from app.domains.membership.viewmodels import EmailRowView

    view = EmailRowView(
        index=_int("index", 1, 1),
        nummer=_int("nummer", 2, 2),
        name_prefix=f"m{_int('member', 0, 0)}_",
    )
    return templates.TemplateResponse(request, "_email_rij.html", view.as_context())


@router.post(
    "/lid-worden", response_class=HTMLResponse, dependencies=[Depends(registration_limiter)]
)
async def lid_worden_submit(
    request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    from app.domains.membership.api import register_family
    from app.domains.membership.signup_form import signup_from_form
    from app.kernel.refusals import FieldError

    data, errors = signup_from_form(await request.form())
    if data is None:
        return refusal_response(request, errors, SIGNUP_MESSAGE, send=True)
    try:
        result = register_family(db, data, background_tasks)
    except HTTPException as refusal:
        # What the service refuses has no field here (a known household, a rule on
        # the object): it stands in the banner, the form stays as typed.
        return refusal_response(
            request, [FieldError("", str(refusal.detail))], SIGNUP_MESSAGE, send=True
        )

    checkout_url = getattr(result, "checkout_url", None)
    response = _signup_page(request, db, done=True, to_checkout=bool(checkout_url))
    if checkout_url:
        response.headers["HX-Redirect"] = checkout_url
    return response


# ── Mijn gezin and the renewal ────────────────────────────────────────────────


def _session_member(request: Request, db: Session):
    """Ingelogd lid via de HttpOnly-sessie, of None."""
    from app.domains.auth.api import SESSION_COOKIE, login_person_for_email, read_session_value

    email = read_session_value(request.cookies.get(SESSION_COOKIE))
    if not email:
        return None
    return login_person_for_email(db, email)


def _to_sign_in(request: Request):
    """#1437: remember the page, so the sign-in comes back here — whatever the role
    (a board member who is also a member lands in the portal)."""
    from urllib.parse import quote

    from fastapi.responses import RedirectResponse

    here = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(f"/aanmelden?terug={quote(here, safe='/')}", status_code=302)


def _running_renewal(db: Session, person):
    """How an open renewal stands (#618): the transfer to make, or the online
    payment to resume — `(transfer, online)`, at most one of them set.

    Amount and reference come **from the booking itself**, not again from the
    price rule: if the price changes between two visits the screen would show
    another amount than what is due.
    """
    from app.domains.membership.api import household_member_for, open_renewal_payment
    from app.domains.membership.household_page import OnlineDue, TransferDue

    try:
        member = household_member_for(db, person)
    except Exception:
        return None, None
    record = open_renewal_payment(db, member) if member is not None else None
    if record is None:
        return None, None
    if record.method == PaymentMethod.TRANSFER:
        from app.kernel.tenant_config import tenant_payment_beneficiary, tenant_payment_iban

        return (
            TransferDue(
                amount=record.amount,
                ogm=record.structured_communication,
                iban=tenant_payment_iban(db),
                beneficiary=tenant_payment_beneficiary(db),
            ),
            None,
        )
    # Broken off at the provider (#618-3): with a checkout URL the member can
    # resume; without one only the explanation that it is still running.
    from app.domains.payment.api import checkout_url_for

    return None, OnlineDue(amount=record.amount, checkout_url=checkout_url_for(db, record))


def _household_page(
    request: Request, db: Session, person, *, edit: bool, saved: bool = False
) -> HTMLResponse:
    from datetime import date

    from app.domains.membership.api import (
        household_view,
        membership_coverage_until,
        renewal_available,
    )
    from app.domains.membership.household_page import HouseholdPage, household_group

    short_date = templates.env.filters["kortedatum"]
    household = household_view(db, person)
    # Cover up to and including an already paid next year (#496).
    valid_until = membership_coverage_until(person)
    transfer, online = _running_renewal(db, person)
    page = HouseholdPage(
        group=household_group(household, _codes(db), me=person.id, short_date=short_date),
        edit=edit,
        valid_until=valid_until,
        renewal_available=renewal_available(valid_until, date.today()),
        renewal_running=bool(transfer or online),
        transfer=transfer,
        board_member_name=household.get("board_member_name"),
        saved=saved,
    )
    return templates.TemplateResponse(
        request, "gezin_portaal.html", {**site_context(db, request), "page": page}
    )


@router.get("/leden/gezin", response_class=HTMLResponse)
def gezin_portaal(request: Request, db: Session = Depends(get_db)):
    person = _session_member(request, db)
    if person is None:
        return _to_sign_in(request)
    return _household_page(request, db, person, edit=request.query_params.get("bewerken") == "1")


def render_family_portal(request: Request, db: Session, person) -> HTMLResponse:
    """Mijn gezin as it stands now, in read mode — the answer of the household's
    one save, whose door is `mdm`'s (CR-13 phase 3, #1250; #1590): the screen
    stays `membership`'s, so `mdm` asks it for the page through
    `membership.api.family_portal_page`. A saved household reads "Opgeslagen ✓"."""
    response = _household_page(request, db, person, edit=False, saved=True)
    response.headers["HX-Push-Url"] = "/leden/gezin"
    return response


def _require_member_csrf(request: Request, db: Session):
    from app.domains.auth.api import require_csrf

    person = _session_member(request, db)
    if person is None:
        raise HTTPException(status_code=401, detail=_("Niet aangemeld"))
    require_csrf(request)
    return person


def _renew_page(request: Request, db: Session, person) -> HTMLResponse:
    from datetime import date

    from app.domains.membership.api import (
        household_view,
        membership_coverage_until,
        renewal_available,
        renewal_terms,
    )
    from app.domains.membership.household_page import RenewPage, Terms, household_summary

    valid_until = membership_coverage_until(person)
    running_transfer, online = _running_renewal(db, person)
    available = renewal_available(valid_until, date.today())
    terms = None
    if available:
        _from, until, amount = renewal_terms(db, person)
        terms = Terms(amount=amount, valid_to=until)
    summary, address_line = household_summary(household_view(db, person), _codes(db))
    page = RenewPage(
        valid_until=valid_until,
        renewal_available=available,
        terms=terms,
        transfer=running_transfer,
        online=online,
        summary=summary,
        address_line=address_line,
    )
    return templates.TemplateResponse(
        request, "lidmaatschap_vernieuwen.html", {**site_context(db, request), "page": page}
    )


@router.get("/leden/gezin/vernieuwen", response_class=HTMLResponse)
def renew_page(request: Request, db: Session = Depends(get_db)):
    person = _session_member(request, db)
    if person is None:
        return _to_sign_in(request)
    return _renew_page(request, db, person)


@router.post("/leden/gezin/vernieuwen", response_class=HTMLResponse)
def gezin_vernieuwen(
    request: Request, db: Session = Depends(get_db), payment_method: str = Form("")
):
    from app.domains.membership.api import household_renew_membership
    from app.domains.membership.signup_form import PAYMENT_METHODS
    from app.kernel.refusals import FieldError

    person = _require_member_csrf(request, db)
    if payment_method not in PAYMENT_METHODS:
        return refusal_response(
            request,
            [FieldError("payment_method", _("Kies een betaalwijze."))],
            RENEW_MESSAGE,
            send=True,
        )
    try:
        result = household_renew_membership(db, person, payment_method=payment_method)
    except HTTPException as refusal:
        return refusal_response(
            request, [FieldError("", str(refusal.detail))], RENEW_MESSAGE, send=True
        )
    checkout_url = result.get("checkout_url") if isinstance(result, dict) else None
    if checkout_url:
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = checkout_url
        return response
    # A transfer (#497): the payment details on the screen, from the booking.
    return _renew_page(request, db, person)
