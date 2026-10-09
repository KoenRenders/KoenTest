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


# Rollenmodel (#530, beslissing Koen): FINANCE = enkel betalingen/vorderingen;
# de algemene admin-schermen zijn ADMIN (of OPERATOR-superuser). ACCOUNT_ADMIN is
# nog niet functioneel ingevuld → geen algemene toegang tot het gedefinieerd is.
_GENERAL_ADMIN_ROLES = {"ADMIN", "OPERATOR"}
_PAYMENTS_VIEW_ROLES = {"ADMIN", "FINANCE", "OPERATOR"}
# Muteren van geld is nauwer dan bekijken: een ADMIN mag de betalingenpagina zien,
# maar niet bevestigen of terugbetalen (financiële scheiding, #83).
_PAYMENTS_MUTATE_ROLES = {"FINANCE", "OPERATOR"}


def admits_admin_ui(roles) -> bool:
    """Would `require_admin_ui` let someone with these roles in? (#1499)

    For a place that shows the way in — the public header's back-office link —
    and must not keep its own copy of the set: an operator holds OPERATOR on
    every tenant and ADMIN on none, and a link that asked for ADMIN alone hid
    the back office from them. Reads `_GENERAL_ADMIN_ROLES` when called, the
    set `require_admin_ui` checks.
    """
    return bool(_GENERAL_ADMIN_ROLES & set(roles))


def back_office_home(roles) -> Optional[str]:
    """The page these roles enter the back office by, or None when they open
    none of it (#1740): its start page for whoever `require_admin_ui` admits,
    payments for someone who may only see those (FINANCE alone — the start page
    would refuse him).

    One home for that knowledge, here with the sets it reads: the public
    header's way in and the way out of the "no access" page both ask it. Until
    #1740 the sign-in's landing carried a copy and sent a board member who
    signed in on the public site into the back office.
    """
    held = set(roles)
    if _GENERAL_ADMIN_ROLES & held:
        return "/admin"
    if _PAYMENTS_VIEW_ROLES & held:
        return "/admin/betalingen"
    return None


def _require_ui_roles(request: Request, db: Session, allowed: set[str]) -> str:
    """Identiteit + rolcheck voor server-rendered schermen. Zonder geldige sessie:
    een 401-pagina-redirect naar de login (303 via HTTPException zou de htmx-flow
    breken).

    #1458: a plain browser GET — a link someone was sent — gets the 303 after all,
    to the sign-in page carrying the requested page as `terug`, so signing in
    lands there (the sign-in flow checks it with `veilige_terug`, #1437). A
    browser does not follow `Location` on a 401 and showed the bare JSON. htmx
    requests and other methods keep the 401 above.
    """
    from app.domains.auth.service import get_user_roles  # lazy: vermijdt cykel

    email = _signed_in(request)
    if not (allowed & set(get_user_roles(db, email))):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_("Geen toegang"))
    return email


def _signed_in(request: Request) -> str:
    """Who this request's session says it is, or the way to the sign-in: the
    303 for a plain browser GET, the 401 otherwise (#1458, described above).
    The identity half of every gate on a screen."""
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
    holds `right` in this workspace and returns the address, as the role-named
    gates do — `Depends(require_right(Right.ACTIVITY_MANAGE))`.

    It fails closed (C4.2): it admits on one condition only, the right being in
    the set the user's roles bundle. No session, a role whose bundle lacks the
    right, a right no bundle holds — each refuses, the operator included. And
    what is asked must be a member of `Right`: anything else is refused here,
    when the route is declared, not at the first request.
    """
    if not isinstance(right, Right):
        raise TypeError(f"require_right takes a member of Right, not {right!r}")

    def gate(request: Request, db: Session = Depends(get_db)) -> str:
        from app.domains.auth.service import may  # lazy: avoids a cycle

        email = _signed_in(request)
        if not may(db, email, right):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_("Geen toegang"))
        return email

    return gate


def require_admin_ui(request: Request, db: Session = Depends(get_db)) -> str:
    """Algemene admin-schermen: enkel ADMIN of OPERATOR (#530). FINANCE-only en het
    (nog ongedefinieerde) ACCOUNT_ADMIN komen hier NIET in — die scheiding voorkomt
    dat een penningmeester leden/CMS/activiteiten kan muteren."""
    return _require_ui_roles(request, db, _GENERAL_ADMIN_ROLES)


def require_finance_ui(request: Request, db: Session = Depends(get_db)) -> str:
    """Betalingen-schermen: ADMIN, FINANCE of OPERATOR mogen kijken/exporteren."""
    return _require_ui_roles(request, db, _PAYMENTS_VIEW_ROLES)


def may_use_admin_assistant(db: Session, email: str) -> bool:
    """Mag deze gebruiker de beheer-assistent aanspreken? (#1060)

    Dezelfde vraag als `require_admin_ui`, maar als vraag in plaats van als poort —
    voor de zichtbaarheid van een ingang. Ze is nodig omdat de twee niet
    samenvallen: het betalingenscherm draait op `require_finance_ui`, dus een
    FINANCE-only gebruiker ziet die lijst wél en mag de assistent niet. Zonder deze
    vraag zou daar een knop staan die op een 403 uitkomt.

    Geen nieuwe rol en geen verbreding (Koen, 20 september 2026): de ingang volgt
    exact wie de route toelaat.
    """
    from app.domains.auth.service import get_user_roles

    return bool(set(get_user_roles(db, email)) & set(_GENERAL_ADMIN_ROLES))


def may_view_payments(db: Session, email: str) -> bool:
    """Dezelfde vraag als require_finance_ui, maar als vraag i.p.v. poort —
    voor tab-zichtbaarheid (golf 9, #913): een tab die je niet mag openen
    hoort er niet te staan, maar een tab die je wél mag openen ook niet te
    ontbreken. Golf 8 gate-te op FINANCE alleen en verstopte de tab dus voor
    een gewone ADMIN."""
    from app.domains.auth.service import get_user_roles

    return bool(set(get_user_roles(db, email)) & set(_PAYMENTS_VIEW_ROLES))


def may_mutate_payments(db: Session, email: str) -> bool:
    """May this user change a payment — confirm, refund, edit, delete? FINANCE or
    OPERATOR (#83/#530). The question `require_finance_mutation` enforces, for a
    screen that shows the actions only to who may use them (#1574)."""
    from app.domains.auth.service import get_user_roles  # lazy: vermijdt cykel

    return bool(_PAYMENTS_MUTATE_ROLES & set(get_user_roles(db, email)))


def require_finance_mutation(
    db: Session = Depends(get_db), email: str = Depends(require_finance_ui)
) -> str:
    """Betaal-MUTATIES (bevestigen/terugbetalen/bewerken/verwijderen): FINANCE of
    OPERATOR (#83/#530).

    A route's dependency since CR-24 (#1722): it stands on `require_finance_ui`,
    which settles who is there, and then asks the narrower set. Until then a
    route called it in its body, behind `require_finance_ui` in its signature —
    the same two checks in the same order, so who gets in did not change. It
    lives here because authorisation has one place (#635 punt 10).
    """
    if not may_mutate_payments(db, email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_("Alleen FINANCE mag betalingen wijzigen."),
        )
    return email


def require_operator_ui(db: Session, email: str) -> None:
    """Tenantbeheer is OPERATOR-only (#581). Zelfde vorm als
    `require_finance_mutation`: geen `Depends`, want de identiteit is al
    vastgesteld en de check komt midden in een route. Woont hier omdat autorisatie
    één plek hoort te hebben — `app/ui/tenants_ui.py` had er een eigen kopie van
    (#635 punt 10)."""
    from app.domains.auth.service import get_user_roles  # lazy: vermijdt cykel

    if "OPERATOR" not in get_user_roles(db, email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_("Alleen de platformbeheerder (OPERATOR) mag tenants beheren."),
        )


def require_platform_operator_ui(
    db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
) -> str:
    """Platform administration (#1535): Tenants, Organisaties, a new account and
    the overview of every workspace. It lives in the platform workspace only —
    in a tenant workspace these screens answer 404, for the operator too, so a
    workspace shows nothing of the others — and there it is OPERATOR-only.

    A route's dependency since CR-24 (#1722), standing on `require_admin_ui` as
    it stood behind it in each route's body: the same checks in the same order.
    """
    from app.domains.auth.users import is_platform_workspace  # lazy: vermijdt cykel

    if not is_platform_workspace(db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_("Niet gevonden."))
    require_operator_ui(db, email)
    return email


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
