"""The public newsletter pages (CR-05 §3.5, #984): sign up, confirm, unsubscribe.

Mobile first — most visitors come on a phone. No login anywhere: the token in
the link is the proof, because it came out of the person's own mailbox.

**Why a button and not a plain link.** Confirming and unsubscribing both happen
on a POST, behind one button on the page the link opens. Mail security
scanners open every link in a mail before the recipient does; if opening the
link were enough, a scanner would confirm addresses nobody confirmed and
unsubscribe people who never asked. The mail client's own one-click
unsubscribe (RFC 8058) is a POST as well, and is served by the same route.

No CSRF token on these POSTs, like every other public form: there is no
session to tie it to. The rate limiter and the per-address brake in the
service carry the abuse protection.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.newsletter import api as nb
from app.domains.newsletter.viewmodels import PublicNewsletterView
from app.limiter import newsletter_signup_limiter
from app.ui import site_context, templates
from app.domains.newsletter.api import SubscriberStatus

router = APIRouter(include_in_schema=False)

# The token the test mail carries: the page explains instead of acting.
TEST_TOKEN = "test"


def _page(request: Request, db: Session, state: str, *, email: str = "",
          token: str = "", error: str | None = None,
          template: str = "nieuwsbrief.html") -> HTMLResponse:
    view = PublicNewsletterView(state=state, email=email, token=token, error=error,
                                site=site_context(db, request))
    return templates.TemplateResponse(request, template, view.as_context())


def _base_url(db: Session) -> str:
    from app.kernel.tenant_config import tenant_base_url

    return tenant_base_url(db).rstrip("/")


@router.get("/nieuwsbrief", response_class=HTMLResponse)
def signup_page(request: Request, db: Session = Depends(get_db)):
    return _page(request, db, "form")


@router.post("/nieuwsbrief", response_class=HTMLResponse,
             dependencies=[Depends(newsletter_signup_limiter)])
def signup(request: Request, db: Session = Depends(get_db),
           email: str = Form(""), first_name: str = Form(""),
           website: str = Form("")):
    """The form, from the footer or from the page itself.

    ``website`` is a honeypot: invisible to people, filled in by simple bots. A
    filled-in honeypot gets the same friendly answer and nothing happens.
    """
    fragment = bool(request.headers.get("HX-Request")) and not request.headers.get("HX-Boosted")
    template = "_nb_publiek.html" if fragment else "nieuwsbrief.html"
    if website.strip():
        return _page(request, db, "sent", email=email.strip(), template=template)
    base = _base_url(db)
    try:
        nb.subscribe_public(db, email, first_name,
                            lambda token: f"{base}/nieuwsbrief/bevestigen/{token}")
    except nb.NewsletterError as exc:
        return _page(request, db, "form", email=email.strip(), error=str(exc),
                     template=template)
    return _page(request, db, "sent", email=email.strip().lower(), template=template)


@router.get("/nieuwsbrief/bevestigen/{token}", response_class=HTMLResponse)
def confirm_page(token: str, request: Request, db: Session = Depends(get_db)):
    subscriber = nb.subscriber_by_confirm_token(db, token)
    if subscriber is None:
        return _page(request, db, "invalid")
    return _page(request, db, "confirm", email=subscriber.email, token=token)


@router.post("/nieuwsbrief/bevestigen/{token}", response_class=HTMLResponse,
             dependencies=[Depends(newsletter_signup_limiter)])
def confirm(token: str, request: Request, db: Session = Depends(get_db)):
    subscriber = nb.confirm(db, token)
    if subscriber is None:
        return _page(request, db, "invalid")
    return _page(request, db, "confirmed", email=subscriber.email)


@router.get("/nieuwsbrief/uitschrijven/{token}", response_class=HTMLResponse)
def unsubscribe_page(token: str, request: Request, db: Session = Depends(get_db)):
    if token == TEST_TOKEN:
        return _page(request, db, "test")
    subscriber = nb.subscriber_by_unsubscribe_token(db, token)
    if subscriber is None:
        return _page(request, db, "invalid")
    state = ("unsubscribed" if subscriber.status == nb.SubscriberStatus.UNSUBSCRIBED
             else "unsubscribe")
    return _page(request, db, state, email=subscriber.email, token=token)


@router.post("/nieuwsbrief/uitschrijven/{token}", response_class=HTMLResponse)
async def unsubscribe(token: str, request: Request, db: Session = Depends(get_db)):
    """The button on the page, and the mail client's one-click POST (RFC 8058).

    Not rate-limited: an unsubscribe must always work, and it can only ever
    remove the address the token belongs to.
    """
    form = await request.form()
    one_click = form.get("List-Unsubscribe") == "One-Click"
    if token == TEST_TOKEN:
        return (PlainTextResponse("test") if one_click
                else _page(request, db, "test"))
    subscriber = nb.unsubscribe(db, token)
    if one_click:
        return PlainTextResponse("ok" if subscriber is not None else "unknown")
    if subscriber is None:
        return _page(request, db, "invalid")
    return _page(request, db, "unsubscribed", email=subscriber.email, token=token)


@router.post("/nieuwsbrief/opnieuw/{token}", response_class=HTMLResponse,
             dependencies=[Depends(newsletter_signup_limiter)])
def resubscribe(token: str, request: Request, db: Session = Depends(get_db)):
    """"Per ongeluk? Toch opnieuw inschrijven" on the unsubscribe page."""
    subscriber = nb.resubscribe(db, token)
    if subscriber is None:
        return _page(request, db, "invalid")
    return _page(request, db, "confirmed", email=subscriber.email)
