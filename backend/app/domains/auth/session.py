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
import logging
import time
from http import HTTPMethod
from typing import Optional
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.domains.auth.models import Right
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


def session_cookie_secure(request: Optional[Request]) -> bool:
    """Hoort de sessiecookie de ``Secure``-vlag te dragen? (#865)

    Tot nu keek dit naar de NAAM van de omgeving — ``app_env in ("uat", "prod")`` —
    en niet naar de verbinding. Een lijst met omgevingsnamen loopt per definitie
    achter: een omgeving die er later bijkomt draait https en krijgt de vlag toch
    niet, en niemand merkt het, want een cookie zonder ``Secure`` werkt gewoon.

    Twee bronnen, in deze volgorde:

    1. **Wordt deze omgeving over https bediend?** Dan staat de vlag er, punt. Dat
       lezen we uit ``FRONTEND_URL``, de canonieke origin van de omgeving zelf.
    2. Anders: het schema van dít verzoek — uit ``X-Forwarded-Proto``, want achter
       Caddy ziet de backend de verbinding van de proxy en niet die van de browser.

    **Waarom de omgeving vóór het verzoek komt, en niet andersom.** Het issue vraagt
    de vlag het schema van het verzoek te laten volgen. Dat alleen zou betekenen dat
    een meegestuurde ``X-Forwarded-Proto: http`` de vlag van een échte https-sessie
    afhaalt — een header die de backend niet kan onderscheiden van een die de proxy
    zette. De omgeving als ondergrens neemt dat weg zonder de winst op te geven: de
    lijst met omgevingsnamen is verdwenen, een nieuwe https-omgeving klopt vanzelf,
    en op een omgeving zonder https volgt de vlag netjes het verzoek.
    """
    if settings.frontend_url.strip().lower().startswith("https://"):
        return True
    if request is None:
        return False
    doorgestuurd = (request.headers.get("x-forwarded-proto") or "").split(",")[0]
    schema = doorgestuurd.strip().lower() or request.url.scheme
    return schema == "https"


def set_session_cookie(response: Response, email: str, request: Optional[Request] = None) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        make_session_value(email),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=session_cookie_secure(request),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Wis de sessie-cookie (uitloggen, #467) — zelfde path als bij het zetten."""
    response.delete_cookie(SESSION_COOKIE, path="/")


def csrf_token_for(session_value: str) -> str:
    return _sign(f"csrf|{session_value}")


def _session_raw(request: Request) -> Optional[str]:
    return request.cookies.get(SESSION_COOKIE)


#: Where the back office is entered: the workbench, for everyone (Q13).
BACK_OFFICE_HOME = "/admin/werkbank"


def back_office_home(db: Session, email: str) -> Optional[str]:
    """The page this user enters the back office by, or None when he opens none
    of it: the workbench, for everyone who holds a back-office role (CR-24 Q13;
    Koen, 9 October 2026: one address for everyone, signing in stays as #1740
    made it). Every such role bundles `workbench.use`, so that right is the
    question.

    One home for that knowledge: the public header's way in and the way out of
    the "no access" page both ask it.
    """
    from app.domains.auth.service import may  # lazy: avoids a cycle

    return BACK_OFFICE_HOME if may(db, email, Right.WORKBENCH_USE) else None


def _signed_in(request: Request) -> str:
    """Who this request's session says it is, or the way to the sign-in — the
    identity half of every gate on a screen.

    Without a valid session a request gets a 401 with `HX-Redirect`: a 303
    would break the htmx flow. A plain browser GET — a link someone was sent —
    gets the 303 after all (#1458), to the sign-in page carrying the page asked
    for as `terug`, so signing in lands there (the sign-in flow checks it with
    `veilige_terug`, #1437): a browser does not follow `Location` on a 401 and
    showed the bare JSON.
    """
    email = read_session_value(_session_raw(request))
    if email is None and request.method == HTTPMethod.GET and not request.headers.get("HX-Request"):
        here = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail=_("Niet aangemeld"),
            headers={"Location": f"/aanmelden?terug={quote(here, safe='/')}"},
        )
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_("Niet aangemeld"),
            headers={"HX-Redirect": "/aanmelden", "Location": "/aanmelden"},
        )
    return email


def require_right(right: Right):
    """The gate of a screen (CR-24 §B1, #1722): a dependency that lets in who
    holds `right` in this workspace and returns the address —
    `Depends(require_right(Right.ACTIVITY_MANAGE))`.

    It fails closed (C4.2): it admits on one condition only, the right being in
    the set the user's roles bundle. No session, a role whose bundle lacks the
    right, a right no bundle holds — each refuses, the operator included. And
    what is asked must be a member of `Right`: anything else is refused here,
    when the route is declared, not at the first request.
    """
    if not isinstance(right, Right):
        raise TypeError(f"require_right takes a member of Right, not {right!r}")

    def gate(request: Request, db: Session = Depends(get_db)) -> str:
        from app.domains.auth.service import rights_of  # lazy: avoids a cycle

        email = _signed_in(request)
        # The whole set, in one row: the gate answers from it, and the page's menu
        # reads the same set from the request instead of asking again.
        held = request.state.rights = rights_of(db, email)
        if right not in held:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                # Q12: one sentence, whatever was asked — it names no role and no right.
                detail=_("Je hebt geen toegang tot deze actie."),
            )
        return email

    # Read by whoever shows a way in only to who may use it: the menu asks the
    # right of the screen an item leads to, instead of keeping a list of its own.
    gate.right = right  # type: ignore[attr-defined]
    return gate


def require_platform_right(right: Right):
    """The gate of a platform screen (CR-24 F8, #1722): Tenants, Organisaties, a
    new account and the overview of every workspace. The right, and then the
    workspace: these screens live in the platform workspace only (#1535), so
    whoever holds the right finds no such page in a tenant's workspace — the
    operator too, so a workspace shows nothing of the others.

    Until CR-24 the order was a role first: who passed the back office's gate
    without being the operator — an ADMIN — got that 404 too. He holds no
    platform right and is refused now, 403, on an address his menu does not
    show.
    """
    holds = require_right(right)

    def gate(request: Request, db: Session = Depends(get_db)) -> str:
        from app.domains.auth.users import is_platform_workspace  # lazy: avoids a cycle

        email = holds(request, db)
        if not is_platform_workspace(db):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Niet gevonden."))
        return email

    gate.right = right  # type: ignore[attr-defined]
    return gate


def require_tenant_workspace(db: Session) -> int:
    """The tenant of this workspace, for its own screens (#1535): "Onze
    organisatie" and "Instellingen". The platform has neither — it is
    administered through Tenants and Organisaties — so there they answer 404."""
    from app.domains.auth.users import _actieve_werkruimte, is_platform_workspace

    if is_platform_workspace(db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Niet gevonden."))
    return _actieve_werkruimte()


def require_csrf(request: Request) -> None:
    """Dubbel-submit-CSRF voor POST's op server-pagina's: token in header
    (htmx) of formulierveld moet matchen met de sessie-afgeleide waarde.

    Drie wezenlijk verschillende situaties gaven dezelfde 403 en waren daardoor
    niet uit elkaar te houden (#662): géén sessiecookie, géén header, of een
    header die niet matcht. Elk vraagt een andere oplossing — een verlopen sessie,
    een verzoek dat buiten de schil vertrekt, of een token dat bij een andere
    sessie hoort — dus het onderscheid gaat als veld naar het log.

    Dit lost niets op en dat is opzet: de meting op HDEV (vier 403's op vier
    endpoints die alle vier óók 200 gaven, nul aanmeldingen, een geldig token op
    elke pagina) sluit de verklaring "herinlog in een ander venster" uit. Een fix
    bovenop een onbekende oorzaak maskeert alleen het symptoom.

    De tokenwaarde wordt NOOIT gelogd, ook niet afgekort: het is een
    beveiligingstoken en deze logs worden opgehaald met `raak fetch`. Bij een
    mismatch is enkel nuttig óf de header leeg was, niet wat erin stond.
    """
    raw = _session_raw(request)
    token = request.headers.get("x-csrf-token")
    reden = None
    if raw is None:
        reden = "no_cookie"
    elif token is None:
        reden = "no_header"
    elif not token:
        reden = "empty_header"
    elif not hmac.compare_digest(csrf_token_for(raw), token):
        reden = "mismatch"
    if reden is not None:
        logging.getLogger("app.auth.csrf").warning(
            "CSRF-controle geweigerd", extra={"csrf_fail": reden}
        )
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

    user = (
        db.query(User)
        .filter(func.lower(User.email) == email.strip().lower(), User.is_active == True)  # noqa: E712
        .first()
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_("Niet aangemeld"))
    return user
