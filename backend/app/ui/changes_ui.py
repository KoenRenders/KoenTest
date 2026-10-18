"""The Wijzigingen screen: the audit log on the kit's list page (#2109).

One primary view over the append-only history (#512, v1.4 parity): the uniform
audit log with a group segment and an actor search. The member-data changes for
Raak Nationaal stay available as an .ods export (a route of its own), under the
toolbar's `⋯`. Composer module: reads through reporting's facade
(`app.domains.reporting.api` — the change report, CR-13 phase 4c), no domain
internals.

The log is a list of dicts merged in Python from ~10 history tables, so the sort
and the paging are done in Python too — the whitelist of sort keys stays for the
same reason as in SQL: a key from outside is never blindly a field name.
"""

from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    Right,
    csrf_from_request,
    require_right,
)
from app.i18n import _
from app.kernel.clock import belgian_today
from app.ui import (
    PER_PAGE_DEFAULT,
    PER_PAGE_OPTIONS,
    admin_nav,
    filterparams,
    list_return,
    per_page_from,
    templates,
)
from app.ui.viewmodels import ChangesView

router = APIRouter(include_in_schema=False)

PAGE = "/admin/ledenwijzigingen"
LIST = PAGE + "/lijst"

#: The segments of the toolbar (§5.1): no counts. The change report knows a fourth
#: group, Inschrijvingen; it is on the screen under Alle.
SEGMENT_GROUPS = ("Leden", "Activiteiten", "Betalingen")

# Sortable columns: the kit's key → the field of the feed row.
_SORT_FIELDS = {
    "wanneer": "recorded_at",
    "wijziging": "operation_label",
    "groep": "group",
    "persoon": "person_name",
    "object": "entity",
    "actor": "actor",
}


def _since(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return belgian_today() - timedelta(days=30)


def _state(request: Request) -> dict:
    stand = filterparams(request)
    sort = (stand.get("sort") or "").strip()
    if sort.lstrip("-") not in _SORT_FIELDS:
        sort = ""
    try:
        page = max(1, int(stand.get("page") or 1))
    except ValueError:
        page = 1
    group = (stand.get("group") or "").strip()
    return {
        "group": group if group in SEGMENT_GROUPS else "",
        "q": (stand.get("q") or "").strip(),
        "since": _since((stand.get("since") or "").strip()),
        "sort": sort,
        "page": page,
        "per_page": per_page_from(stand.get("per_page")),
    }


def _view(request: Request, db: Session, **extra) -> ChangesView:
    from app.domains.reporting.api import all_changes_since

    s = _state(request)
    everything = all_changes_since(db, s["since"], group=s["group"] or None, actor=s["q"] or None)
    # No sort is the newest first, as the log always read; "wanneer" is the oldest first.
    key = s["sort"].lstrip("-") or "wanneer"
    descending = not s["sort"] or s["sort"].startswith("-")
    field = _SORT_FIELDS[key]

    def _key(row: dict):
        value = row.get(field)
        # None-safe: empty values last on ascending; sorted() is stable and the feed
        # comes in newest to oldest, so equal values keep a fixed order — the paging
        # counterpart of the #761 tiebreaker.
        if field == "recorded_at":
            return value
        return (value is None or value == "", str(value).lower(), row.get("entity_id") or 0)

    everything = sorted(everything, key=_key, reverse=descending)
    total = len(everything)
    rows = everything[(s["page"] - 1) * s["per_page"] : s["page"] * s["per_page"]]

    filters = {"group": s["group"], "q": s["q"], "since": s["since"].isoformat()}
    way = list_return(
        PAGE,
        **{k: v for k, v in filters.items() if v},
        sort=s["sort"],
        page=s["page"] if s["page"] > 1 else "",
        per_page=s["per_page"] if s["per_page"] != PER_PAGE_DEFAULT else "",
    )
    # P13 jump links: the record cell links to the record's own page, only for
    # entities that have one. Only the registration page knows the way back, so
    # only that jump carries this screen with its state.
    object_urls = {
        "Gezin": "/admin/leden/gezin/{id}",
        "Activiteit": "/admin/activiteiten/{id}",
        "Inschrijving": "/admin/inschrijvingen/{id}?terug=" + quote(way, safe=""),
    }
    for row in rows:
        template = object_urls.get(row["entity"])
        row["object_url"] = (
            template.format(id=row["entity_id"]) if template and row.get("entity_id") else None
        )

    carried = {k: v for k, v in filters.items() if v}

    def sort_urls(column: str, first: str = "asc") -> dict:
        # The first click on a column sorts ascending; on the date column the
        # list's own order (newest first) is already "sorted", so its first click
        # reverses it.
        if column == "wanneer":
            nxt = "" if s["sort"] == "wanneer" else "wanneer"
        else:
            nxt = f"-{column}" if s["sort"] == column else column
        query = urlencode({**carried, "sort": nxt, "per_page": s["per_page"]})
        active = s["sort"].lstrip("-") == column or (column == "wanneer" and not s["sort"])
        return {
            "sort_url": f"{LIST}?{query}",
            "sort_page_url": f"{PAGE}?{query}",
            "sorted": (("desc" if descending else "asc") if active else None),
        }

    columns = [
        {"key": "wanneer", "label": _("Tijdstip"), "cell": "moment", **sort_urls("wanneer")},
        {
            "key": "wijziging",
            "label": _("Wijziging"),
            "cell": "status",
            "width": 104,
            **sort_urls("wijziging"),
        },
        {
            "key": "groep",
            "label": _("Onderdeel"),
            "cell": "extra",
            "width": 120,
            **sort_urls("groep"),
        },
        {"key": "persoon", "label": _("Persoon"), "cell": "name", **sort_urls("persoon")},
        {
            "key": "object",
            "label": _("Record"),
            "cell": "context",
            "width": 140,
            **sort_urls("object"),
        },
        {
            "key": "actor",
            "label": _("Uitgevoerd door"),
            "cell": "extra",
            "priority": 2,
            "width": 170,
            **sort_urls("actor"),
        },
        # The widths are the narrowest the content reads at: seven columns have to fit
        # the frame at 1 100 px, where Details and Uitgevoerd door still stand.
        {"key": "details", "label": _("Details"), "cell": "text", "priority": 1, "width": 240},
    ]
    return ChangesView(
        rows=rows,
        columns=columns,
        segments=[
            {"value": "", "label": _("Alle")},
            {"value": "Leden", "label": _("Leden")},
            {"value": "Activiteiten", "label": _("Activiteiten")},
            {"value": "Betalingen", "label": _("Betalingen")},
        ],
        group=s["group"],
        q=s["q"],
        since=s["since"].isoformat(),
        sort=s["sort"],
        sort_options=[
            ("", _("Recentste eerst")),
            ("wanneer", _("Oudste eerst")),
            ("wijziging", _("Wijziging")),
            ("groep", _("Onderdeel")),
            ("persoon", _("Persoon")),
            ("object", _("Record")),
            ("actor", _("Uitgevoerd door")),
        ],
        # Under ⋯: the export of the member-data changes — of the period the screen
        # shows (the form's own `since`, read at the click), not of a period fixed
        # when the page loaded.
        menu=[
            {
                "label": _("Ledenexport (.ods)"),
                "href": PAGE + "/export",
                "icon": "download",
                "with_state": True,
            }
        ],
        page=s["page"],
        per_page=s["per_page"],
        total=total,
        page_sizes=list(PER_PAGE_OPTIONS),
        pager_url=f"{LIST}?{urlencode({**carried, 'sort': s['sort'], 'per_page': s['per_page']})}",
        empty_reason=_("Geen wijzigingen sinds %(datum)s.") % {"datum": s["since"].isoformat()},
        csrf_token=csrf_from_request(request),
        **extra,
    )


@router.get(PAGE, response_class=HTMLResponse)
def changes_page(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_VIEW)),
):
    view = _view(request, db, nav_items=admin_nav(PAGE, request))
    return templates.TemplateResponse(request, "admin_ledenwijzigingen.html", view.as_context())


@router.get(LIST, response_class=HTMLResponse)
def changes_list(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_VIEW)),
):
    """The list alone: the toolbar swaps this fragment, so the search field is not
    replaced under the fingers."""
    return templates.TemplateResponse(
        request, "_lw_inhoud.html", _view(request, db, oob=True).as_context()
    )


@router.get(PAGE + "/export")
def member_changes_export(
    request: Request,
    since: str = "",
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.SETTINGS_VIEW)),
) -> Response:
    from app.domains.reporting.api import build_member_changes_ods, member_changes_since

    start = _since(since)
    content = build_member_changes_ods(member_changes_since(db, start))
    return Response(
        content=content,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={
            "Content-Disposition": f'attachment; filename="ledenwijzigingen-vanaf-{start}.ods"'
        },
    )
