"""Server-rendered aanmeldscherm (fase 1, #399 — §21).

Zelfde login-flow als de API (magic-link + OTP, één flow voor iedereen), maar
zonder React: e-mail invullen → code ontvangen → code invullen → HttpOnly-
sessiecookie + door naar de werkbank. Bestaat naast de React-login tot de
React-exit (#405); de API-endpoints blijven de enige plek met de flow-logica.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.session import set_session_cookie
from app.i18n import _
from app.limiter import login_limiter
from app.ui import templates, veilige_terug
from app.ui.viewmodel import ViewModel

router = APIRouter(include_in_schema=False)


def _session_address(request: Request, consumed) -> str:
    """The address the session carries once a code or a link did its work.

    A sign-in and a new account: the address of the code. A CONFIRMED address
    (CR-22 R15, #1711) signs nobody else in: whoever is signed in stays who he
    is — a parent confirming a child's address stays the parent. Two cases
    move to the new address: nobody is signed in on this device (the link was
    opened elsewhere; the code proved the address, as a sign-in does), and the
    session was signed in with the address that was just replaced — that one
    no longer exists.
    """
    from app.domains.auth.api import SESSION_COOKIE, LoginPurpose, read_session_value

    current = read_session_value(request.cookies.get(SESSION_COOKIE))
    if (
        consumed.purpose is LoginPurpose.CONFIRM_ADDRESS
        and current
        and current.lower() != consumed.replaced.lower()
    ):
        return current
    return consumed.email


@router.get("/aanmelden", response_class=HTMLResponse)
def aanmelden_page(request: Request, db: Session = Depends(get_db)):
    from app.ui import site_context

    # De pagina includeert _sign_in_email.html, dat een foutbanner en het
    # ingevulde adres toont. Bij een verse GET zijn die leeg — maar wél beloofd
    # (#643): een template die iets vraagt, krijgt het van de route.
    # #1391 (W17): where to go after signing in, when a page sent the visitor
    # here. Carried as a hidden field through both steps; followed only when it
    # is a path on this site (`veilige_terug`), else the landing by role.
    return_to = veilige_terug(request.query_params.get("terug"), "")
    return templates.TemplateResponse(
        request,
        "sign_in.html",
        {**site_context(db, request), "error": None, "email": "", "terug": return_to},
    )


@router.post("/aanmelden", response_class=HTMLResponse, dependencies=[Depends(login_limiter)])
def aanmelden_submit(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(""),
    return_to: str = Form("", alias="terug"),
):
    email = email.strip()
    return_to = veilige_terug(return_to, "")
    if not email or "@" not in email:
        return templates.TemplateResponse(
            request,
            "_sign_in_email.html",
            {"error": _("Vul een geldig e-mailadres in."), "email": email, "terug": return_to},
        )
    from app.domains.auth.api import start_login

    # #1437: the mail link carries the page too, not only this code step.
    start_login(db, email, return_to=return_to)
    # Altijd hetzelfde vervolg — verklap niet of het adres gekend is.
    return templates.TemplateResponse(
        request,
        "_sign_in_code.html",
        {"email": email, "error": None, "terug": return_to, "new_account": False},
    )


@router.post("/aanmelden/code", response_class=HTMLResponse, dependencies=[Depends(login_limiter)])
def aanmelden_code(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(""),
    code: str = Form(""),
    return_to: str = Form("", alias="terug"),
    new_account: str = Form("", alias="nieuw"),
):
    from app.domains.auth.api import consume_code

    email, code = email.strip(), code.strip()
    return_to = veilige_terug(return_to, "")
    # CR-22 (#1707): the one code step for every purpose — a sign-in, and the
    # code that makes an account. A wrong or expired code is generic; a right
    # code whose purpose was refused (the address got an owner since the form
    # was sent) says why, and signs nobody in.
    consumed = consume_code(db, email, code)
    if consumed is None or consumed.refusal:
        error = consumed.refusal if consumed else _("Ongeldige of verlopen code.")
        return templates.TemplateResponse(
            request,
            "_sign_in_code.html",
            {
                "email": email,
                "error": error,
                "terug": return_to,
                # The step keeps its button's word after a wrong code (#1708).
                "new_account": new_account == "1",
            },
        )
    # The page that asked (#1437), else the account page (#1740) — the same
    # rule as the mail link, from the one place it lives.
    from app.domains.auth.api import landing_for

    email = _session_address(request, consumed)
    dest = return_to or landing_for(db, email)
    response = templates.TemplateResponse(request, "_sign_in_done.html", {})
    set_session_cookie(response, email, request)
    response.headers["HX-Redirect"] = dest
    return response


# ── Account aanmaken (CR-22 S4b, #1708; R3, R4) ──────────────────────────────


@dataclass(frozen=True, kw_only=True)
class CreateAccountView(ViewModel):
    """`create_account.html` and its form `_create_account_form.html`: what was
    typed, and per field what is wrong with it."""

    first_name: str = ""
    last_name: str = ""
    email: str = ""
    mobile: str = ""
    problems: dict[str, str] = field(default_factory=dict)
    terug: str = ""


@router.get("/account-aanmaken", response_class=HTMLResponse)
def create_account_page(request: Request, db: Session = Depends(get_db)):
    from app.ui import site_context

    return_to = veilige_terug(request.query_params.get("terug"), "")
    context = site_context(db, request)
    context.update(CreateAccountView(terug=return_to).as_context())
    return templates.TemplateResponse(request, "create_account.html", context)


@router.post(
    "/account-aanmaken", response_class=HTMLResponse, dependencies=[Depends(login_limiter)]
)
def create_account_submit(
    request: Request,
    db: Session = Depends(get_db),
    first_name: str = Form(""),
    last_name: str = Form(""),
    email: str = Form(""),
    mobile: str = Form(""),
    return_to: str = Form("", alias="terug"),
):
    """The four fields, each refused under itself; a good request always gets
    the same code step — the screen never says whether the address is known
    (CR-22 Q17). No person exists before the code is entered."""
    from app.domains.auth.api import AccountRequest, start_account

    return_to = veilige_terug(return_to, "")
    asked = AccountRequest(
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        email=email.strip(),
        mobile=mobile.strip(),
    )
    problems = asked.problems()
    if problems:
        view = CreateAccountView(
            first_name=asked.first_name,
            last_name=asked.last_name,
            email=asked.email,
            mobile=asked.mobile,
            problems=problems,
            terug=return_to,
        )
        return templates.TemplateResponse(request, "_create_account_form.html", view.as_context())
    start_account(db, asked, return_to=return_to)
    return templates.TemplateResponse(
        request,
        "_sign_in_code.html",
        {"email": asked.email, "error": None, "terug": return_to, "new_account": True},
    )


# URL-pariteit (React-exit 405-e, #405): de oude React-loginpaden blijven
# werken en sturen door naar de htmx-aanmeldflow resp. het magic-link-doel.


@router.get("/afmelden")
def afmelden(request: Request):
    """Uitloggen (#467): wis de sessie-cookie en ga naar de homepage."""
    from fastapi.responses import RedirectResponse

    from app.domains.auth.session import clear_session_cookie

    resp = RedirectResponse("/", status_code=302)
    clear_session_cookie(resp)
    return resp


@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_redirect(request: Request):
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/aanmelden", status_code=302)


@router.get("/admin/login/verify", response_class=HTMLResponse)
def admin_login_verify_redirect(request: Request, token: str = ""):
    from fastapi.responses import RedirectResponse

    return RedirectResponse(f"/login/verify?token={token}", status_code=302)


# Login-pariteit (#405): /login = de htmx-aanmeldflow; /login/verify blijft het
# magic-link-doel uit de e-mails en zet de sessie + stuurt door.
#
# Moved here from membership/ui.py with CR-19 (#1475), unchanged: signing in
# belongs to auth, and the membership router is switched off with the
# membership module — a tenant without members must still sign in.


@router.get("/login", response_class=HTMLResponse)
def login_redirect(request: Request):
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/aanmelden", status_code=302)


@router.get("/leden/login", response_class=HTMLResponse)
def member_login_redirect(request: Request):
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/aanmelden", status_code=302)


@router.get("/login/verify", response_class=HTMLResponse)
def login_verify(request: Request, token: str = "", terug: str = "", db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse

    from app.domains.auth.login import consume_link
    from app.domains.auth.service import landing_for
    from app.ui import site_context

    # Eenmalig verzilveren (#268) — die regel woont in de auth-service, niet hier.
    # CR-22 Q36 (#1707): the link does what the code does, for every purpose —
    # the link of "Bevestig je account" makes the account and signs in. A link
    # whose purpose was refused gets the same page as a spent one: nobody is
    # signed in, and the page says no more than that.
    consumed = consume_link(db, token)
    if consumed is None or consumed.refusal:
        return templates.TemplateResponse(
            request, "login_verlopen.html", site_context(db, request), status_code=401
        )
    email = _session_address(request, consumed)
    # The page that asked (#1437), checked by the one `veilige_terug` — a link
    # can be edited, so only a path on this site counts; else the account
    # page (#1740), the same rule as the code step.
    response = RedirectResponse(veilige_terug(terug, landing_for(db, email)), status_code=302)
    set_session_cookie(response, email, request)
    return response


@router.get("/leden/login/verify", response_class=HTMLResponse)
def member_login_verify_redirect(request: Request, token: str = "", terug: str = ""):
    """URL-pariteit (React-exit 405-e): oud React-pad → het magic-link-doel."""
    from urllib.parse import quote

    from fastapi.responses import RedirectResponse

    extra = f"&terug={quote(terug, safe='/')}" if terug else ""
    return RedirectResponse(f"/login/verify?token={token}{extra}", status_code=302)
