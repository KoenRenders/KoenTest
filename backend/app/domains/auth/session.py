"""Sessie-/CSRF-laag voor server-rendered schermen (#398, §21) — sinds fase 1b
(#399) onderdeel van het auth-component. Het mechanisme:
- HttpOnly-sessiecookie met een HMAC-getekende waarde (email|exp) — geen JWT in
  localStorage voor server-pagina's.
- CSRF: dubbel-submit met een HMAC-token afgeleid van de sessiewaarde; htmx
  stuurt hem als ``X-CSRF-Token`` (via hx-headers op <body>), formulieren als
  verborgen veld.
Alles stdlib (hmac/hashlib) — geen nieuwe dependencies.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.i18n import _

SESSION_COOKIE = "raak_session"
SESSION_MAX_AGE = 60 * 60 * 12  # 12 uur — zelfde horizon als een werkdag


def _sign(value: str) -> str:
    return hmac.new(settings.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()


def make_session_value(email: str) -> str:
    exp = int(time.time()) + SESSION_MAX_AGE
    base = f"{email}|{exp}"
    return f"{base}|{_sign(base)}"


def read_session_value(raw: Optional[str]) -> Optional[str]:
    """Geeft het e-mailadres terug als de cookie geldig en niet verlopen is."""
    if not raw or raw.count("|") != 2:
        return None
    email, exp, sig = raw.rsplit("|", 2)
    base = f"{email}|{exp}"
    if not hmac.compare_digest(_sign(base), sig):
        return None
    if int(exp) < time.time():
        return None
    return email


def set_session_cookie(response: Response, email: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        make_session_value(email),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.app_env in ("uat", "prod"),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Wis de sessie-cookie (uitloggen, #467) — zelfde path als bij het zetten."""
    response.delete_cookie(SESSION_COOKIE, path="/")


def csrf_token_for(session_value: str) -> str:
    return _sign(f"csrf|{session_value}")


def _session_raw(request: Request) -> Optional[str]:
    return request.cookies.get(SESSION_COOKIE)


def require_admin_ui(request: Request, db: Session = Depends(get_db)) -> str:
    """Identiteit + ADMIN/FINANCE-rol voor server-rendered admin-schermen.
    Zonder geldige sessie: redirect naar de bestaande login (303 via HTTPException
    zou de flow breken; we sturen een 401-pagina-redirect)."""
    from app.domains.auth.service import get_user_roles  # lazy: vermijdt cykel

    email = read_session_value(_session_raw(request))
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Niet aangemeld"),
            headers={"HX-Redirect": "/aanmelden", "Location": "/aanmelden"},
        )
    roles = get_user_roles(db, email)
    if not ({"ADMIN", "FINANCE", "ACCOUNT_ADMIN", "OPERATOR"} & set(roles)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_("Geen toegang"))
    return email


def require_csrf(request: Request) -> None:
    """Dubbel-submit-CSRF voor POST's op server-pagina's: token in header
    (htmx) of formulierveld moet matchen met de sessie-afgeleide waarde."""
    raw = _session_raw(request)
    token = request.headers.get("x-csrf-token")
    if raw is None or token is None or not hmac.compare_digest(csrf_token_for(raw), token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_("CSRF-token ongeldig"))


def csrf_from_request(request: Request) -> str:
    """CSRF-token voor de sessie van dit request (#444) — de gedeelde vervanger
    van de per-scherm gedupliceerde _csrf()-helpers."""
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


def admin_user_by_email(db: Session, email: str):
    """De actieve backoffice-User voor dit e-mailadres, of 401 (#444) — de
    gedeelde vervanger van de per-scherm gedupliceerde _admin_user()-helpers.
    Gebruikt als history-actor bij hergebruik van routerfuncties in de UI."""
    from sqlalchemy import func

    from app.domains.auth.models import User
    from app.i18n import _

    user = (db.query(User)
            .filter(func.lower(User.email) == email.strip().lower(),
                    User.is_active == True)  # noqa: E712
            .first())
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=_("Niet aangemeld"))
    return user
