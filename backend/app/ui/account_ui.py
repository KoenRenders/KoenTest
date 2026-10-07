"""The account pages of the public site: "Mijn <site>" (CR-22 S3, #1706; R13,
R14, R26).

The landing page of whoever is signed in, and the shell the modules' own pages
stand in — Mijn gezin today, Mijn gegevens, Mijn inschrijvingen and later Mijn
aankopen from their own slices. It belongs to no single domain, so it lives in
`app/ui` (`AGENTS.md`, *UI-architectuur*); what it shows comes from each
domain's facade.

In this slice only a member reaches it: signing in still lands on Mijn gezin
(`auth.landing_for`) and an account without a household does not exist yet
(S4a).

**Who has no person here has no "Mijn <site>"** (Koen, 7 October 2026): a
session whose address belongs to no person on this tenant — a board user who
is no member, or someone signed in at another tenant on the same host — gets
no account menu (`_site_account.html`) and this page answers 404. Without a
session at all the page asks to sign in and comes back, as Mijn gezin does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.ui import account_nav, site_context, templates
from app.ui.viewmodel import ViewModel

router = APIRouter(tags=["ui-account"])

#: The landing page's own path — the first item of the account menu.
ACCOUNT_HOME = "/mijn"


@dataclass(frozen=True, kw_only=True)
class AccountHome(ViewModel):
    """The landing page after signing in."""

    #: "Mijn " + the site's name: the page's title and the menu's first item.
    title: str
    first_name: str
    #: The account menu, the same list the header and the drawer show.
    nav: list[dict]
    active: str
    #: How the household's membership stands — the card of Mijn gezin (R26);
    #: None for whoever has no household, or where the tenant has no members.
    card: Optional[Any] = None


def signed_in_person(request: Request, db: Session):
    """`(signed_in, person)`: is there a session, and the person it belongs to
    on this tenant — None for a session without one."""
    from app.domains.auth.api import SESSION_COOKIE, login_person_for_email, read_session_value

    email = read_session_value(request.cookies.get(SESSION_COOKIE))
    if not email:
        return False, None
    return True, login_person_for_email(db, email)


def to_sign_in(request: Request) -> RedirectResponse:
    """Ask to sign in, and come back to this page (#1437)."""
    here = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(f"/aanmelden?terug={quote(here, safe='/')}", status_code=302)


def _membership_card(db: Session, person) -> Optional[Any]:
    from app.domains.mdm.api import module_enabled
    from app.kernel.modules import ModuleCode

    if not module_enabled(ModuleCode.MEMBERSHIP) or not person.member_persons:
        return None
    from app.domains.membership.api import membership_card

    return membership_card(db, person)


@router.get(ACCOUNT_HOME, response_class=HTMLResponse)
def account_home(request: Request, db: Session = Depends(get_db)):
    signed_in, person = signed_in_person(request, db)
    if not signed_in:
        return to_sign_in(request)
    if person is None:
        # A session without a person here has no account page; sending it to
        # the sign-in would loop, it IS signed in.
        raise HTTPException(status_code=404)
    nav = account_nav(db)
    page = AccountHome(
        title=nav[0]["label"],
        first_name=(person.first_name or "").strip(),
        nav=nav,
        active=ACCOUNT_HOME,
        card=_membership_card(db, person),
    )
    context = site_context(db, request)
    context.update(page.as_context())
    return templates.TemplateResponse(request, "account_home.html", context)
