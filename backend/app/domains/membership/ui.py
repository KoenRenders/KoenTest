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
from app.i18n import _
from app.kernel.clock import belgian_today
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


def _signed_in_account(request: Request, db: Session):
    """The person signed in as an ACCOUNT — no household yet — or None (#1883).
    Who has a household is offered no "Word lid" (#1883, point 3); who is not
    signed in gets the empty form."""
    from app.domains.auth.api import (
        SESSION_COOKIE,
        login_person_for_email,
        read_session_value,
    )

    email = read_session_value(request.cookies.get(SESSION_COOKIE))
    person = login_person_for_email(db, email) if email else None
    # CR-26: an account is a person in no household at all; one whose household
    # is a member of another department of the account joins with it (F5).
    return person if person is not None and not person.member_persons else None


def _signup_page(request: Request, db: Session, **state) -> HTMLResponse:
    from app.domains.membership.household_page import SignupPage, signup_group

    group = signup_group(
        _codes(db),
        own=_signed_in_account(request, db),
        short_date=templates.env.filters["kortedatum"],
    )
    page = SignupPage(group=group, terms=_signup_terms(), **state)
    return templates.TemplateResponse(
        request, "lid_worden.html", {**site_context(db, request), "page": page}
    )


@router.get("/lid-worden", response_class=HTMLResponse)
def sign_up_page(request: Request, db: Session = Depends(get_db)):
    """Word lid. A signed-in account stands in it as the main member, with what
    the application already has of him (#1883).

    CR-26 (A3, F5): a signed-in person whose household is a member of another
    department of the account joins with that household — the page that pays a
    membership, for this department, not a second household (Koen, 19 October
    2026, to the existing payment page or a concept first: "1a")."""
    joiner = _session_joiner(request, db)
    if joiner is not None:
        return _renew_page(request, db, joiner, joining=True)
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


@router.post(
    "/lid-worden", response_class=HTMLResponse, dependencies=[Depends(registration_limiter)]
)
async def sign_up_submit(
    request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    from app.domains.membership.api import register_family
    from app.domains.membership.signup_form import own_details, signup_from_form
    from app.kernel.form_guard import NotSent, Proof
    from app.kernel.refusals import FieldError

    form = await request.form()
    # #1883: a signed-in account is the main member with his own details.
    account = _signed_in_account(request, db)
    data, errors = signup_from_form(form, own=own_details(account) if account is not None else None)
    if data is None:
        return refusal_response(request, errors, SIGNUP_MESSAGE, send=True)
    # CR-22 R9 (#1713): an account that signs up while signed in becomes the
    # main member itself — the door says who is signed in, the service decides.
    from app.domains.auth.api import SESSION_COOKIE, login_person_for_email, read_session_value

    session_email = read_session_value(request.cookies.get(SESSION_COOKIE))
    signed_in = login_person_for_email(db, session_email) if session_email else None
    try:
        result = register_family(
            db, data, background_tasks, signed_in=signed_in, proof=Proof.from_request(request, form)
        )
    except HTTPException as refusal:
        # What the service refuses has no field here (a known household, a rule on
        # the object): it stands in the banner, the form stays as typed.
        return refusal_response(
            request, [FieldError("", str(refusal.detail))], SIGNUP_MESSAGE, send=True
        )
    except NotSent as hurry:
        # A person's pace (Koen, 15 October 2026): the banner over the form as typed.
        return refusal_response(
            request,
            [FieldError("", str(hurry))],
            SIGNUP_MESSAGE,
            send=True,
            guard_form="#lid-worden-form",
        )

    checkout_url = getattr(result, "checkout_url", None)
    response = _signup_page(request, db, done=True, to_checkout=bool(checkout_url))
    if checkout_url:
        response.headers["HX-Redirect"] = checkout_url
    return response


# ── Mijn gezin and the renewal ────────────────────────────────────────────────


def _session_member(request: Request, db: Session):
    """The signed-in member of a household through the HttpOnly session, or None.

    None for an account too (CR-22, #1707): a person without a household has no
    Mijn gezin. `_to_sign_in` sends him to his account page, not to the sign-in
    he already passed.
    """
    from app.domains.auth.api import (
        SESSION_COOKIE,
        has_household,
        login_person_for_email,
        read_session_value,
    )

    email = read_session_value(request.cookies.get(SESSION_COOKIE))
    if not email:
        return None
    person = login_person_for_email(db, email)
    return person if has_household(person) else None


def _to_sign_in(request: Request, db: Session):
    """#1437: remember the page, so the sign-in comes back here — whatever the role
    (a board member who is also a member lands in the portal)."""
    from urllib.parse import quote

    from fastapi.responses import RedirectResponse

    from app.domains.auth.api import SESSION_COOKIE, landing_for, read_session_value

    # CR-22 (#1707): whoever IS signed in and has no household — an account —
    # would be sent to sign in, and come straight back here: a loop. He goes
    # where he lands instead (his account page, or the site without a person).
    email = read_session_value(request.cookies.get(SESSION_COOKIE))
    if email:
        return RedirectResponse(landing_for(db, email), status_code=302)
    here = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(f"/aanmelden?terug={quote(here, safe='/')}", status_code=302)


#: Mijn gezin: where a running renewal stands (#1641).
HOUSEHOLD_PAGE = "/leden/gezin"


def _household_page(
    request: Request, db: Session, person, *, edit: bool, saved: bool = False
) -> HTMLResponse:
    from app.domains.membership.api import household_view, membership_card
    from app.domains.membership.household_page import HouseholdPage, household_group

    short_date = templates.env.filters["kortedatum"]
    household = household_view(db, person)
    page = HouseholdPage(
        group=household_group(
            household, _codes(db), me=person.id, short_date=short_date, edit=edit
        ),
        edit=edit,
        card=membership_card(db, person, household=household),
        saved=saved,
    )
    return templates.TemplateResponse(
        request, "household_page.html", {**site_context(db, request), "page": page}
    )


@router.get("/leden/gezin", response_class=HTMLResponse)
def household_page(request: Request, db: Session = Depends(get_db)):
    person = _session_member(request, db)
    if person is None:
        return _to_sign_in(request, db)
    return _household_page(request, db, person, edit=request.query_params.get("bewerken") == "1")


def render_family_portal(request: Request, db: Session, person) -> HTMLResponse:
    """Mijn gezin as it stands now, in read mode — the answer of the household's
    one save, whose door is `mdm`'s (CR-13 phase 3, #1250; #1590): the screen
    stays `membership`'s, so `mdm` asks it for the page through
    `membership.api.family_portal_page`. A saved household reads "Opgeslagen ✓"."""
    response = _household_page(request, db, person, edit=False, saved=True)
    response.headers["HX-Push-Url"] = "/leden/gezin"
    return response


def _session_joiner(request: Request, db: Session):
    """The signed-in person whose household is a member of another department
    of the account and not of this one (CR-26 A3), or None."""
    from app.domains.auth.api import (
        SESSION_COOKIE,
        in_household_elsewhere,
        login_person_for_email,
        read_session_value,
    )

    email = read_session_value(request.cookies.get(SESSION_COOKIE))
    person = login_person_for_email(db, email) if email else None
    return person if in_household_elsewhere(person) else None


def _require_member_csrf(request: Request, db: Session, *, or_joiner: bool = False):
    from app.domains.auth.api import require_csrf

    person = _session_member(request, db)
    if person is None and or_joiner:
        person = _session_joiner(request, db)
    if person is None:
        raise HTTPException(status_code=401, detail=_("Niet aangemeld"))
    require_csrf(request)
    return person


def _renew_page(request: Request, db: Session, person, *, joining: bool = False) -> HTMLResponse:

    from app.domains.membership.api import (
        household_view,
        membership_coverage_until,
        renewal_available,
        renewal_terms,
    )
    from app.domains.membership.household_page import RenewPage, Terms, household_summary

    valid_until = membership_coverage_until(person)
    available = renewal_available(valid_until, belgian_today())
    terms = None
    if available:
        _from, until, amount = renewal_terms(db, person)
        terms = Terms(amount=amount, valid_to=until)
    summary, address_line = household_summary(household_view(db, person), _codes(db))
    page = RenewPage(
        valid_until=valid_until,
        renewal_available=available,
        terms=terms,
        summary=summary,
        address_line=address_line,
        joining=joining,
        # Cancelling a join goes to the account page: Mijn gezin is not here yet.
        household_href="/mijn" if joining else "/leden/gezin",
    )
    return templates.TemplateResponse(
        request, "lidmaatschap_vernieuwen.html", {**site_context(db, request), "page": page}
    )


@router.get("/leden/gezin/vernieuwen", response_class=HTMLResponse)
def renew_page(request: Request, db: Session = Depends(get_db)):
    person = _session_member(request, db)
    if person is None:
        return _to_sign_in(request, db)
    # #1641 (CR-11 Q79): this page starts a renewal. One that runs stands in the
    # Lidmaatschap card of Mijn gezin — the one place — so that is where
    # opening this page lands meanwhile.
    from app.domains.membership.api import renewal_is_running

    if renewal_is_running(db, person):
        from fastapi.responses import RedirectResponse

        return RedirectResponse(HOUSEHOLD_PAGE, status_code=303)
    return _renew_page(request, db, person)


@router.post("/leden/gezin/vernieuwen", response_class=HTMLResponse)
def renew_membership_page(
    request: Request, db: Session = Depends(get_db), payment_method: str = Form("")
):
    from app.domains.membership.api import household_renew_membership
    from app.domains.membership.signup_form import PAYMENT_METHODS
    from app.kernel.refusals import FieldError

    # CR-26: the household of another department joins here the same way.
    person = _require_member_csrf(request, db, or_joiner=True)
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
    # A transfer (#497): the payment details stand in the Lidmaatschap card of
    # Mijn gezin, from the booking (#1641) — a hard redirect, as to a checkout.
    response = HTMLResponse("")
    response.headers["HX-Redirect"] = HOUSEHOLD_PAGE
    return response
