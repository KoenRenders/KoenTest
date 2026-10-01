"""Server-rendered aanmeldscherm (fase 1, #399 — §21).

Zelfde login-flow als de API (magic-link + OTP, één flow voor iedereen), maar
zonder React: e-mail invullen → code ontvangen → code invullen → HttpOnly-
sessiecookie + door naar de werkbank. Bestaat naast de React-login tot de
React-exit (#405); de API-endpoints blijven de enige plek met de flow-logica.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.session import set_session_cookie
from app.i18n import _
from app.limiter import login_limiter
from app.ui import templates, veilige_terug

router = APIRouter(include_in_schema=False)


@router.get("/aanmelden", response_class=HTMLResponse)
def aanmelden_page(request: Request, db: Session = Depends(get_db)):
    from app.ui import site_context

    # De pagina includeert _aanmelden_email.html, dat een foutbanner en het
    # ingevulde adres toont. Bij een verse GET zijn die leeg — maar wél beloofd
    # (#643): een template die iets vraagt, krijgt het van de route.
    # #1391 (W17): where to go after signing in, when a page sent the visitor
    # here. Carried as a hidden field through both steps; followed only when it
    # is a path on this site (`veilige_terug`), else the landing by role.
    return_to = veilige_terug(request.query_params.get("terug"), "")
    return templates.TemplateResponse(
        request,
        "aanmelden.html",
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
            "_aanmelden_email.html",
            {"error": _("Vul een geldig e-mailadres in."), "email": email, "terug": return_to},
        )
    from app.domains.auth.api import start_login

    # #1437: the mail link carries the page too, not only this code step.
    start_login(db, email, return_to=return_to)
    # Altijd hetzelfde vervolg — verklap niet of het adres gekend is.
    return templates.TemplateResponse(
        request, "_aanmelden_code.html", {"email": email, "error": None, "terug": return_to}
    )


@router.post("/aanmelden/code", response_class=HTMLResponse, dependencies=[Depends(login_limiter)])
def aanmelden_code(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(""),
    code: str = Form(""),
    return_to: str = Form("", alias="terug"),
):
    from app.domains.auth.api import check_otp

    email, code = email.strip(), code.strip()
    return_to = veilige_terug(return_to, "")
    if not check_otp(db, email, code):
        return templates.TemplateResponse(
            request,
            "_aanmelden_code.html",
            {"email": email, "error": _("Ongeldige of verlopen code."), "terug": return_to},
        )
    # The page that asked, else the landing by role (#530, #1437) — the same
    # rule as the mail link, from the one place it lives.
    from app.domains.auth.api import landing_for

    dest = return_to or landing_for(db, email)
    response = templates.TemplateResponse(request, "_aanmelden_klaar.html", {})
    set_session_cookie(response, email, request)
    response.headers["HX-Redirect"] = dest
    return response


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
