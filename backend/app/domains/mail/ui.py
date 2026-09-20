"""Server-rendered e-maillogscherm (fase 1, #399 — §21).

Zelfde inzage als de admin-API (#328): filterbaar overzicht + verwijderen.
Sessie-auth (HttpOnly-cookie) + CSRF, zoals de werkbank.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf
from app.domains.mail.api import (EMAIL_LOG_SORT_KEYS, EMAIL_STATUSES,
                                  EMAIL_TYPES, delete_email_log, list_email_log)
from app.i18n import _
from app.ui import (PER_PAGE_OPTIONS, admin_nav, filterparams, per_page_from,
                    sort_description, templates)

router = APIRouter(include_in_schema=False)


_TYPE_LABELS = {
    "membership_confirmation": "Lidmaatschap",
    "activity_confirmation": "Activiteit",
    "idea_ack": "Idee (bevestiging)",
    "idea_board": "Idee (bestuur)",
    "magic_link": "Inloglink",
    "member_contact_notice": "Contactbericht",
    "form_confirmation": "Formulier (bevestiging)",
    "other": "Overig",
}
_STATUS_LABELS = {"sent": "Verstuurd", "failed": "Mislukt", "skipped": "Overgeslagen"}


def _sorteer_labels() -> dict[str, str]:
    """De zichtbare kolomnaam per sorteersleutel (#1083).

    Per request en niet als moduleconstante: `_()` volgt de taal van de tenant.
    Hier en niet in het sjabloon, omdat de meta-regel boven de tabel dezelfde
    woorden gebruikt als de kolomkop.
    """
    return {"datum": _("Datum"), "ontvanger": _("Ontvanger"),
            "onderwerp": _("Onderwerp"), "type": _("Type"),
            "status": _("Status")}


def _ctx(request: Request, db: Session) -> dict:
    # #671: uit HX-Current-URL als htmx die meestuurt, anders uit de query-string.
    stand = filterparams(request)
    email_type = (stand.get("email_type") or "").strip()
    status = (stand.get("status") or "").strip()
    recipient = (stand.get("recipient") or "").strip()
    try:
        page = max(1, int(stand.get("page", "1")))
    except ValueError:
        page = 1
    # Golf 3 (#913): sorteerbare kolommen. Onbekende sleutel → datum; de
    # kop-URL's dragen de volledige stand (deelbare link, §3.5-principe) en
    # klikken op de actieve kolom draait de richting.
    sort = (stand.get("sort") or "datum").strip()
    if sort not in EMAIL_LOG_SORT_KEYS:
        sort = "datum"
    richting = "asc" if (stand.get("richting") or "").strip() == "asc" else "desc"
    labels = _sorteer_labels()
    # Golf 3 (#913): paginagrootte-keuze — whitelist, zoals alles wat uit de
    # querystring komt. De whitelist staat sinds #1083 in `app.ui`, want de
    # keuzelijst in de meta-regel wordt uit diezelfde reeks gevuld.
    per_page = per_page_from(stand.get("per_page"))
    rows, has_next = list_email_log(db, email_type=email_type, status=status,
                                    recipient=recipient, page=page,
                                    page_size=per_page, sort=sort,
                                    richting=richting)

    from urllib.parse import urlencode

    def _sorteer_url(key: str) -> str:
        volgende = "asc" if (sort == key and richting == "desc") else "desc"
        # Standaardrichting per klik: eerst desc (nieuwste/hoogste eerst), een
        # tweede klik draait om. Pagina reset — een andere ordening is een
        # andere lijst.
        params = {k: v for k, v in (("email_type", email_type), ("status", status),
                                    ("recipient", recipient)) if v}
        params.update({"sort": key, "richting": volgende if sort == key else ("desc" if key == "datum" else "asc")})
        # Altijd meesturen (#1083): met "alleen als het afwijkt" viel de keuze bij
        # een kop-klik terug op de standaard zodra ze toevallig 50 was — en die
        # voorwaarde is precies het soort ding dat bij de volgende standaard
        # vergeten wordt.
        params["per_page"] = str(per_page)
        return "/admin/e-maillog/lijst?" + urlencode(params)
    raw = request.cookies.get(SESSION_COOKIE) or ""
    return {
        "csrf_token": csrf_token_for(raw),
        "rows": rows,
        "email_type": email_type,
        "status": status,
        "recipient": recipient,
        "page": page,
        "has_prev": page > 1,
        "has_next": has_next,
        "sort": sort,
        "richting": richting,
        "per_page": per_page,
        "sorteer_urls": {key: _sorteer_url(key) for key in EMAIL_LOG_SORT_KEYS},
        "sorteer_labels": labels,
        "per_page_options": PER_PAGE_OPTIONS,
        # De meta-regel boven de tabel (§2.3). Bewust "op deze pagina": dit scherm
        # doet met opzet GEEN COUNT (§2.3 noemt het als het geval daarvoor) en
        # haalt één rij extra op om te weten of er nog een pagina is. "N e-mails"
        # zou dus een totaal suggereren dat we niet gemeten hebben.
        "meta_telling": _("%(aantal)s e-mails op deze pagina") % {"aantal": len(rows)},
        "meta_volgorde": sort_description(labels[sort], richting,
                                          is_date=(sort == "datum")),
        "email_types": EMAIL_TYPES,
        "email_statuses": EMAIL_STATUSES,
        "type_labels": _TYPE_LABELS,
        "status_labels": _STATUS_LABELS,
        "nav_items": admin_nav("/admin/e-maillog"),
    }


@router.get("/admin/e-maillog", response_class=HTMLResponse)
def email_log_page(request: Request, db: Session = Depends(get_db),
                   email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "email_log.html", _ctx(request, db))


@router.get("/admin/e-maillog/lijst", response_class=HTMLResponse)
def email_log_lijst(request: Request, db: Session = Depends(get_db),
                    email: str = Depends(require_admin_ui)):
    """Fragment voor filterwissels (htmx)."""
    return templates.TemplateResponse(request, "_email_log_lijst.html", _ctx(request, db))


@router.post("/admin/e-maillog/{log_id}/verwijderen", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
def email_log_verwijderen(log_id: int, request: Request, db: Session = Depends(get_db),
                          email: str = Depends(require_admin_ui)):
    delete_email_log(db, log_id)
    # #760-absorptie (golf 3): elke mutatie bevestigt — fragment-antwoord, dus
    # de toast mag out-of-band mee (#748).
    ctx = _ctx(request, db)
    ctx["toast_melding"] = _("Logregel verwijderd.")
    return templates.TemplateResponse(request, "_email_log_lijst.html", ctx)


@router.get("/admin/emails", response_class=HTMLResponse)
def emails_redirect(request: Request):
    """URL-pariteit (React-exit 405-e): het oude React-pad → /admin/e-maillog."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse("/admin/e-maillog", status_code=302)
