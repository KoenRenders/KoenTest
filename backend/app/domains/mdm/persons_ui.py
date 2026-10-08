"""Personen in the back office (CR-22 S7, #1712; R18, R25): `/admin/personen`.

A list page on the kit's toolbar and table: every natural person of the
tenant, the view "Zonder gezin" first, a search, and one action behind `⋯` —
Verwijderen, with a confirmation that names the household when there is one.
Nothing is edited here.

The gate is today's `require_admin_ui` (ADMIN, OPERATOR); CR-24 replaces it by
a right later. A shell router: persons are master data, with or without the
membership module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    address_says_nobody,
    csrf_from_request,
    require_admin_ui,
    require_csrf,
)
from app.domains.mdm.api import (
    PERSON_VIEWS,
    MasterDataError,
    delete_listed_person,
    module_enabled,
    person_row,
    persons_page,
    persons_view_from,
)
from app.i18n import _
from app.kernel.modules import ModuleCode
from app.ui import PER_PAGE_OPTIONS, admin_nav, filterparams, per_page_from, templates
from app.ui.viewmodel import ViewModel

router = APIRouter(include_in_schema=False)

PAGE = "/admin/personen"
LIST = PAGE + "/lijst"
VIEW_PARAM = "zicht"


@dataclass(frozen=True, kw_only=True)
class PersonsView(ViewModel):
    """`personen.html` and its fragment `_personen_lijst.html`."""

    rows: list[dict[str, Any]]
    columns: list[dict[str, Any]]
    segments: list[dict[str, Any]]
    view: str
    q: str
    page: int
    per_page: int
    total: int
    page_sizes: list[int]
    pager_url: str
    empty_reason: str
    # The shell sends it with every htmx request of the page (the delete).
    csrf_token: str
    error: str | None = None
    oob: bool = False
    nav_items: list[Any] | None = None


def _confirmation(row) -> str:
    if row.household_name:
        return _(
            "%(name)s verwijderen? Deze persoon wordt ook uit het gezin %(household)s gehaald."
        ) % {
            "name": row.name,
            "household": row.household_name,
        }
    return _("%(name)s verwijderen?") % {"name": row.name}


def _row(row, households: bool, double_email: bool) -> dict[str, Any]:
    attrs = f'hx-post="{PAGE}/{row.id}/verwijderen" hx-target="#personen-lijst" hx-swap="innerHTML"'
    return {
        "person": row,
        # A person has no page of his own: the name leads to the household's
        # record where there is one, and is plain text otherwise.
        "href": f"/admin/leden/gezin/{row.household_id}"
        if row.household_id and households
        else None,
        "in_household": row.household_id is not None,
        "is_account": row.is_account,
        # #1740: his address stands on someone else too and signs nobody in —
        # asked of the sign-in's own rule (`auth.address_says_nobody`).
        "double_email": double_email,
        "menu": [
            {
                "kind": "delete",
                "label": _("Verwijderen"),
                "attrs": attrs,
                "confirm": _confirmation(row),
            }
        ],
    }


def _empty_reason(view: str, q: str) -> str:
    if q:
        return _("Geen personen gevonden voor deze zoekopdracht.")
    if view == PERSON_VIEWS[0]:
        return _("Er zijn geen personen zonder gezin.")
    if view == PERSON_VIEWS[1]:
        return _("Er zijn geen personen in een gezin.")
    return _("Er zijn nog geen personen.")


def _view(request: Request, db: Session, *, error: str | None = None, **extra) -> PersonsView:
    state = filterparams(request)
    view = persons_view_from(state.get(VIEW_PARAM))
    q = (state.get("q") or "").strip()
    per_page = per_page_from(state.get("per_page"))
    try:
        page = max(1, int(state.get("page") or 1))
    except ValueError:
        page = 1
    found = persons_page(db, view=view, q=q, page=page, per_page=per_page)
    page = min(page, max(1, -(-found.total // per_page)))
    without, within, everyone = PERSON_VIEWS
    labels = {without: _("Zonder gezin"), within: _("In een gezin"), everyone: _("Alle")}
    query = {VIEW_PARAM: view, "q": q, "per_page": per_page}
    households = module_enabled(ModuleCode.MEMBERSHIP)
    return PersonsView(
        rows=[
            _row(
                r,
                households,
                # A waiting address counts for nothing yet, so it cannot be double.
                bool(r.email and not r.email_waiting and address_says_nobody(db, r.email)),
            )
            for r in found.rows
        ],
        columns=[
            {"key": "naam", "label": _("Naam"), "cell": "name"},
            {"key": "contact", "label": _("E-mail en mobiel"), "cell": "context"},
            {"key": "soort", "label": _("Soort"), "cell": "status"},
            {"key": "gezin", "label": _("Gezin"), "cell": "extra", "priority": 1},
            {"key": "aangemaakt", "label": _("Aangemaakt"), "cell": "extra", "priority": 2},
            {"key": "acties", "label": _("Acties"), "cell": "actions"},
        ],
        segments=[{"value": v, "label": labels[v], "count": found.counts[v]} for v in PERSON_VIEWS],
        view=view,
        q=q,
        page=page,
        per_page=per_page,
        total=found.total,
        page_sizes=list(PER_PAGE_OPTIONS),
        pager_url=f"{LIST}?{urlencode({k: v for k, v in query.items() if v != ''})}",
        empty_reason=_empty_reason(view, q),
        csrf_token=csrf_from_request(request),
        error=error,
        **extra,
    )


@router.get(PAGE, response_class=HTMLResponse)
def persons_page_screen(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
):
    view = _view(request, db, nav_items=admin_nav(PAGE))
    return templates.TemplateResponse(request, "personen.html", view.as_context())


@router.get(LIST, response_class=HTMLResponse)
def persons_list(
    request: Request, db: Session = Depends(get_db), email: str = Depends(require_admin_ui)
):
    """The list alone: the toolbar swaps this fragment, so the search field is
    not replaced under the fingers."""
    return templates.TemplateResponse(
        request, "_personen_lijst.html", _view(request, db, oob=True).as_context()
    )


@router.post(
    PAGE + "/{person_id}/verwijderen",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def person_delete(
    person_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_admin_ui),
):
    """Delete a person; the list comes back as it was filtered, with the reason
    above it when the delete is refused (the main member of a household)."""
    error = None
    row = person_row(db, person_id)
    if row is None:
        error = _("Deze persoon bestaat niet (meer).")
    else:
        try:
            delete_listed_person(db, person_id, actor=email)
        except MasterDataError as refusal:
            error = _("%(name)s is niet verwijderd. %(reason)s") % {
                "name": row.name,
                "reason": str(refusal),
            }
    return templates.TemplateResponse(
        request, "_personen_lijst.html", _view(request, db, error=error, oob=True).as_context()
    )
