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
from app.limiter import login_limiter
from app.ui import templates

router = APIRouter(include_in_schema=False)


@router.get("/aanmelden", response_class=HTMLResponse)
def aanmelden_page(request: Request):
    return templates.TemplateResponse(request, "aanmelden.html", {})


@router.post("/aanmelden", response_class=HTMLResponse,
             dependencies=[Depends(login_limiter)])
def aanmelden_submit(request: Request, db: Session = Depends(get_db),
                     email: str = Form("")):
    email = email.strip()
    if not email or "@" not in email:
        return templates.TemplateResponse(
            request, "_aanmelden_email.html",
            {"error": "Vul een geldig e-mailadres in.", "email": email})
    from app.domains.auth.router import start_login

    start_login(db, email)
    # Altijd hetzelfde vervolg — verklap niet of het adres gekend is.
    return templates.TemplateResponse(request, "_aanmelden_code.html",
                                      {"email": email, "error": None})


@router.post("/aanmelden/code", response_class=HTMLResponse,
             dependencies=[Depends(login_limiter)])
def aanmelden_code(request: Request, db: Session = Depends(get_db),
                   email: str = Form(""), code: str = Form("")):
    from app.domains.auth.router import check_otp

    email, code = email.strip(), code.strip()
    if not check_otp(db, email, code):
        return templates.TemplateResponse(
            request, "_aanmelden_code.html",
            {"email": email, "error": "Ongeldige of verlopen code."})
    response = templates.TemplateResponse(request, "_aanmelden_klaar.html", {})
    set_session_cookie(response, email)
    response.headers["HX-Redirect"] = "/admin/werkbank"
    return response


# URL-pariteit (React-exit 405-e, #405): de oude React-loginpaden blijven
# werken en sturen door naar de htmx-aanmeldflow resp. het magic-link-doel.

@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_redirect(request: Request):
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/aanmelden", status_code=302)


@router.get("/admin/login/verify", response_class=HTMLResponse)
def admin_login_verify_redirect(request: Request, token: str = ""):
    from fastapi.responses import RedirectResponse

    return RedirectResponse(f"/login/verify?token={token}", status_code=302)
