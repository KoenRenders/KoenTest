"""The e-mail log in the back office: the list on the kit and a page per mail (#1925).

Koen, 16 October 2026, to "Het e-maillog opent een mail in een venster. In de
lijst van de kit opent een rij een record, en een mail heeft geen eigen pagina":
"geef een email maar een read-only eigen scherm, in een volgende versie gaan we
ook binnenkomende mails visualiseren". So the list stands on `list_page` with the
kit's toolbar and table, a row's subject opens the mail's own page, and that page
reads only: the mail as it was sent, to whom, when, its type and its status.

The page says what a mail IS, not which way it went: its facts are a list the
view-model builds ("Aan"), so an incoming mail later adds its own ("Van") on the
same page. Nothing of an incoming mail is built here.

Verwijderen stands on the mail's page, under Acties (CR-11's row rule: a list row
shows at most the positive action of its state, and a mail has none).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import Right, csrf_from_request, require_csrf, require_right
from app.domains.mail.api import (
    EMAIL_LOG_SORT_KEYS,
    EMAIL_TYPE,
    MAIL_STATUS,
    MailStatus,
    delete_email_log,
    get_email_log,
    list_email_log,
)
from app.i18n import _, short_datetime
from app.kernel.codes import code_label, code_labels, register_tones, tone
from app.ui import (
    PER_PAGE_DEFAULT,
    PER_PAGE_OPTIONS,
    admin_nav,
    filterparams,
    list_return,
    per_page_from,
    templates,
    veilige_terug,
    way_back,
)
from app.ui.viewmodel import ViewModel

router = APIRouter(include_in_schema=False)

PAGE = "/admin/e-maillog"
LIST = PAGE + "/lijst"

# CR-12 phase 4: the words of the e-mail types and statuses come from their
# label tables. The badge tone stays here, next to the screen that draws it
# (§B4.5): sent green, failed red, the two that did not leave yellow.
register_tones(
    MAIL_STATUS.name,
    {
        MailStatus.SENT: "green",
        MailStatus.FAILED: "red",
        MailStatus.SKIPPED: "yellow",
        MailStatus.LOGGED: "yellow",
    },
)


@dataclass(frozen=True, kw_only=True)
class EmailLogView(ViewModel):
    """`email_log.html` and its fragment `_email_log_lijst.html`."""

    rows: list[dict[str, Any]]
    columns: list[dict[str, Any]]
    q: str
    email_type: str
    status: str
    sort: str | None
    sort_options: list[tuple[str, str]]
    type_options: list[tuple[str, str]]
    status_options: list[tuple[str, str]]
    page: int
    per_page: int
    total: int
    page_sizes: list[int]
    pager_url: str
    empty_reason: str
    csrf_token: str
    oob: bool = False
    nav_items: list[Any] | None = None


@dataclass(frozen=True, kw_only=True)
class EmailRecordView(ViewModel):
    """`email_record.html` — one mail, read only."""

    title: str
    badges: list[dict[str, str]]
    facts: list[dict[str, str]]
    actions: list[dict[str, Any]]
    way_back: dict[str, str]
    body: str | None
    error: str | None
    csrf_token: str
    nav_items: list[Any] = field(default_factory=list)


def _state(request: Request) -> dict[str, Any]:
    stand = filterparams(request)
    sort = (stand.get("sort") or "").strip()
    if sort.lstrip("-") not in EMAIL_LOG_SORT_KEYS:
        sort = ""
    try:
        page = max(1, int(stand.get("page") or 1))
    except ValueError:
        page = 1
    return {
        "q": (stand.get("q") or "").strip(),
        "email_type": (stand.get("email_type") or "").strip(),
        "status": (stand.get("status") or "").strip(),
        "sort": sort,
        "page": page,
        "per_page": per_page_from(stand.get("per_page")),
    }


def _view(request: Request, db: Session, **extra) -> EmailLogView:
    s = _state(request)
    # The kit's sort ("onderwerp", "-onderwerp") on the service's (key, direction);
    # no sort is the newest first, as the log always read.
    key = s["sort"].lstrip("-") or "datum"
    direction = "desc" if (not s["sort"] or s["sort"].startswith("-")) else "asc"
    rows, total = list_email_log(
        db,
        email_type=s["email_type"],
        status=s["status"],
        recipient=s["q"],
        page=s["page"],
        page_size=s["per_page"],
        sort=key,
        richting=direction,
    )
    filters = {k: s[k] for k in ("q", "email_type", "status") if s[k]}
    way = list_return(
        PAGE,
        **filters,
        sort=s["sort"],
        page=s["page"] if s["page"] > 1 else "",
        per_page=s["per_page"] if s["per_page"] != PER_PAGE_DEFAULT else "",
    )

    def sort_urls(column: str) -> dict[str, Any]:
        nxt = f"-{column}" if s["sort"] == column else column
        query = urlencode({**filters, "sort": nxt, "per_page": s["per_page"]})
        return {
            "sort_url": f"{LIST}?{query}",
            "sort_page_url": f"{PAGE}?{query}",
            "sorted": ("desc" if s["sort"].startswith("-") else "asc")
            if s["sort"].lstrip("-") == column
            else None,
        }

    return EmailLogView(
        rows=[
            {
                "mail": row,
                "href": f"{PAGE}/{row.id}?terug={quote(way, safe='/')}",
                "type": code_label(EMAIL_TYPE.name, row.email_type, db=db),
            }
            for row in rows
        ],
        columns=[
            {"key": "onderwerp", "label": _("Onderwerp"), "cell": "name", **sort_urls("onderwerp")},
            {
                "key": "ontvanger",
                "label": _("Ontvanger"),
                "cell": "context",
                **sort_urls("ontvanger"),
            },
            {"key": "status", "label": _("Status"), "cell": "status", **sort_urls("status")},
            {
                "key": "type",
                "label": _("Type"),
                "cell": "extra",
                "priority": 2,
                **sort_urls("type"),
            },
            {"key": "datum", "label": _("Datum"), "cell": "moment", **sort_urls("datum")},
        ],
        q=s["q"],
        email_type=s["email_type"],
        status=s["status"],
        sort=s["sort"],
        sort_options=[
            ("", _("Recentste eerst")),
            ("datum", _("Oudste eerst")),
            ("onderwerp", _("Onderwerp (A–Z)")),
            ("ontvanger", _("Ontvanger (A–Z)")),
            ("status", _("Status")),
            ("type", _("Type")),
        ],
        type_options=code_labels(EMAIL_TYPE.name, db=db),
        status_options=code_labels(MAIL_STATUS.name, db=db),
        page=s["page"],
        per_page=s["per_page"],
        total=total,
        page_sizes=list(PER_PAGE_OPTIONS),
        pager_url=f"{LIST}?{urlencode({**filters, 'sort': s['sort'], 'per_page': s['per_page']})}",
        empty_reason=_("Geen e-mails gevonden voor deze filter.")
        if filters
        else _("Er zijn nog geen e-mails."),
        csrf_token=csrf_from_request(request),
        **extra,
    )


@router.get(PAGE, response_class=HTMLResponse)
def email_log_page(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_VIEW)),
):
    view = _view(request, db, nav_items=admin_nav(PAGE, request))
    return templates.TemplateResponse(request, "email_log.html", view.as_context())


@router.get(LIST, response_class=HTMLResponse)
def email_log_list(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_VIEW)),
):
    """The list alone: the toolbar swaps this fragment, so the search field is not
    replaced under the fingers."""
    return templates.TemplateResponse(
        request, "_email_log_lijst.html", _view(request, db, oob=True).as_context()
    )


@router.get(PAGE + "/{log_id}", response_class=HTMLResponse)
def email_record(
    log_id: int,
    request: Request,
    terug: str = "",
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_VIEW)),
):
    """One mail, read only: as it was sent, to whom, when, its type and status."""
    mail = get_email_log(db, log_id)
    if mail is None:
        raise HTTPException(status_code=404, detail=_("Niet gevonden"))
    back = way_back(db, terug, PAGE)
    view = EmailRecordView(
        title=mail.subject or _("(geen onderwerp)"),
        badges=[
            {
                "label": code_label(MAIL_STATUS.name, mail.status, db=db),
                "tone": tone(MAIL_STATUS.name, mail.status),
            }
        ],
        facts=[
            {"text": _("Aan: %(adres)s") % {"adres": mail.recipient}},
            {"text": short_datetime(mail.created_at)},
            {"text": code_label(EMAIL_TYPE.name, mail.email_type, db=db)},
        ],
        actions=[
            {
                "kind": "delete",
                "label": _("Verwijderen"),
                "attrs": f'hx-post="{PAGE}/{mail.id}/verwijderen"'
                + (f' hx-vals=\'{{"terug": "{back["href"]}"}}\'' if back["href"] else ""),
                "confirm": _('E-mail "%(onderwerp)s" definitief verwijderen?')
                % {"onderwerp": mail.subject},
            }
        ],
        way_back=back,
        body=mail.body,
        error=mail.error_message,
        csrf_token=csrf_from_request(request),
        nav_items=admin_nav(PAGE, request),
    )
    return templates.TemplateResponse(request, "email_record.html", view.as_context())


@router.post(
    PAGE + "/{log_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
async def email_log_delete(
    log_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_MANAGE)),
):
    """Delete one mail from the log, from its own page; back to where it was
    opened from."""
    form = await request.form()
    delete_email_log(db, log_id)
    back = veilige_terug(str(form.get("terug") or ""), PAGE)
    return Response(status_code=204, headers={"HX-Redirect": back})


@router.get("/admin/emails", response_class=HTMLResponse)
def emails_redirect(request: Request):
    """URL-pariteit (React-exit 405-e): het oude React-pad → /admin/e-maillog."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(PAGE, status_code=302)
