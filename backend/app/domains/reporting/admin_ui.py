"""The reporting screens (#833, CR-06 §5): the list and the query panel.

Everything sits behind `require_admin_ui` — ADMIN or OPERATOR, the same door as
every other admin screen. v2.3.0 adds no new security surface: the roles the
universe declares per object are a declaration, not a fence (#832).

**The panel's whole state lives in the query string.** Which objects are chosen,
which filters are shown and what they are set to, the sort and the page — all of
it travels as parameters, and every change is one htmx request that re-renders the
panel. Nothing is kept in the browser, so a shared link opens the same report, a
refresh changes nothing, and there is no second place where the state could
disagree with the screen.

The paths are Dutch because a board member reads them in the address bar and gets
them in a link; the module, the routes and the parameters are English like all new
code (CLAUDE.md, "URL paths follow the audience").
"""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import _
from app.domains.auth.api import (
    SESSION_COOKIE, csrf_token_for, require_admin_ui, require_csrf,
)
from app.domains.reporting.api import (
    Direction,
    Filter,
    Operator,
    Selection,
    SelectionError,
    SavedReportError,
    Sort,
    BY_KEY,
    build_dataset_ods,
    build_report_ods,
    classes_of,
    classes_with_objects,
    copy_report,
    dataset_filename,
    delete_report,
    dimension_values,
    get_saved_report,
    list_saved_reports,
    log_export,
    mark_run,
    report_filename,
    run_validated,
    save_report,
    selection_of,
    selection_to_dict,
    update_report,
)
from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id
from app.ui import admin_nav, is_fragment_request, templates
from app.domains.reporting.viewmodels import ReportListView, ReportPanelView

router = APIRouter(include_in_schema=False)

NAV = "/admin/rapporten"
ODS_MEDIA_TYPE = "application/vnd.oasis.opendocument.spreadsheet"
PER_PAGE = 50

# Where a drill-down lands (design-system P8). A report is a way in, not a dead
# end: the row that says "Quiz — 41 inschrijvingen" links to the activity.
DRILL_URLS = {
    "activity": "/admin/activiteiten/{id}",
    "household": "/admin/leden/gezin/{id}",
    "payment": "/admin/betalingen?record={id}",
}


def _tenant(request: Request) -> int:
    """The tenant of this request — from the middleware, never from the caller."""
    return current_tenant_id.get() or DEFAULT_TENANT_ID


def _csrf(request: Request) -> str:
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


# ── Reading the panel state out of the query string ──────────────────────────

def _read_state(params) -> dict:
    """The panel state, plus the one command that is changing it.

    Two kinds of parameter, deliberately named apart. The **state** — `object`,
    `filter`, `v_<key>`, `op_<key>`, `sort`, `dir` — lives in hidden inputs of the
    panel form and travels with every request. A **command** — `add`, `remove`,
    `up`, `down`, `sort_by`, `goto` — is the name/value of the button that was
    pressed, and htmx sends it alongside.

    Keeping them apart is what makes the order right: `object` keeps its DOM order
    (`getlist`, not a dict), and a newly added object lands at the end because the
    server appends it, not because of how htmx happened to merge two query
    strings.

    Any command except `goto` puts you back on page one. Changing a filter while
    you are on page three and staying on page three shows an empty table and reads
    as "no data".

    Takes the parameter mapping and not the request: on a GET the state travels in
    the query string, and on a save it travels in the form body. Same reading, one
    function — two would drift.
    """
    objects = [k for k in params.getlist("object") if k in BY_KEY]
    filters = [k for k in params.getlist("filter") if k in BY_KEY]
    values = {k[2:]: (params.get(k) or "").strip()
              for k in params.keys() if k.startswith("v_")}
    values = {k: v for k, v in values.items() if v}
    operators = {k[3:]: (params.get(k) or "eq")
                 for k in params.keys() if k.startswith("op_")}
    sort = params.get("sort") or ""
    direction = params.get("dir") or "asc"

    add = params.get("add")
    if add in BY_KEY and add not in objects:
        objects.append(add)
    remove = params.get("remove")
    if remove in objects:
        objects.remove(remove)
        if sort == remove:
            sort, direction = "", "asc"

    add_filter = params.get("add_filter")
    if add_filter in BY_KEY and add_filter not in filters:
        filters.append(add_filter)
    remove_filter = params.get("remove_filter")
    if remove_filter in filters:
        filters.remove(remove_filter)
        values.pop(remove_filter, None)
        operators.pop(remove_filter, None)

    for command, step in (("up", -1), ("down", 1)):
        key = params.get(command)
        if key in objects:
            index = objects.index(key)
            buur = index + step
            if 0 <= buur < len(objects):
                objects[index], objects[buur] = objects[buur], objects[index]

    sort_by = params.get("sort_by")
    if sort_by in objects:
        # Clicking the column you are already sorting on turns it around; that is
        # what every table in this application does.
        direction = "desc" if (sort_by == sort and direction == "asc") else "asc"
        sort = sort_by

    goto = params.get("goto")
    page = max(1, int(goto)) if (goto or "").isdigit() else 1

    return {
        "objects": objects,
        "filters": filters,
        "values": values,
        "operators": operators,
        "sort": sort,
        "direction": direction,
        "page": page,
    }


def _selection(state: dict) -> Selection:
    """The state as a `Selection`. Raises `SelectionError` with the reason."""
    filters = []
    for key in state["filters"]:
        waarde = state["values"].get(key)
        if not waarde:
            continue
        # The operator travels as a hidden input beside the control that produced
        # the value: a dropdown compares exactly, a text field searches. Deriving
        # it here instead would be a second place that has to agree with the
        # template about which control was rendered.
        try:
            operator = Operator(state["operators"].get(key, "eq"))
        except ValueError as exc:
            raise SelectionError(
                f"Onbekende filtersoort: '{state['operators'].get(key)}'.") from exc
        filters.append(Filter(key, operator, (waarde,)))

    sort: tuple[Sort, ...] = ()
    if state["sort"] in state["objects"]:
        richting = Direction.DESC if state["direction"] == "desc" else Direction.ASC
        sort = (Sort(state["sort"], richting),)

    return Selection(
        object_keys=tuple(state["objects"]), filters=tuple(filters), sort=sort,
        limit=PER_PAGE + 1, offset=(state["page"] - 1) * PER_PAGE,
    )


def _query_string(state: dict) -> str:
    """The state back into a query string — for the export link and paging."""
    paren: list[tuple[str, str]] = []
    paren += [("object", k) for k in state["objects"]]
    paren += [("filter", k) for k in state["filters"]]
    paren += [(f"v_{k}", v) for k, v in state["values"].items()]
    paren += [(f"op_{k}", v) for k, v in state["operators"].items()]
    if state["sort"]:
        paren.append(("sort", state["sort"]))
        paren.append(("dir", state["direction"]))
    return urlencode(paren)


def _state_from_selection(selection: Selection, page: int = 1) -> dict:
    """A saved selection back into panel state, so the panel opens on it."""
    return {
        "objects": list(selection.object_keys),
        "filters": [f.object_key for f in selection.filters],
        "values": {f.object_key: (f.values[0] if f.values else "")
                   for f in selection.filters},
        "operators": {f.object_key: f.operator.value for f in selection.filters},
        "sort": selection.sort[0].object_key if selection.sort else "",
        "direction": selection.sort[0].direction.value if selection.sort else "asc",
        "page": page,
    }


# ── The panel view-model ─────────────────────────────────────────────────────

def _panel(request: Request, db: Session, state: dict, *, report=None,
           error: str | None = None, toast: bool = False) -> ReportPanelView:
    """Build the panel from its state. One place, so page and fragment agree."""
    tenant_id = _tenant(request)
    chosen = [BY_KEY[k] for k in state["objects"]]

    filter_options: dict[str, list[str]] = {}
    for key in state["filters"]:
        filter_options[key] = dimension_values(db, key, tenant_id=tenant_id)

    columns: list = []
    rows: list = []
    totals: dict = {}
    drill_aliases: dict = {}
    message: str | None = None
    has_next = False

    if state["objects"]:
        try:
            selection = _selection(state)
            result = run_validated(db, selection, tenant_id=tenant_id)
            columns = result.columns
            rows = result.rows[:PER_PAGE]
            has_next = len(result.rows) > PER_PAGE
            totals = result.totals
            drill_aliases = result.drill_aliases
        except SelectionError as exc:
            message = str(exc)
    else:
        message = "Kies objecten links, filters rechts."

    return ReportPanelView(
        classes=classes_with_objects(),
        objects_by_key=dict(BY_KEY),
        kind_symbols={"measure": "Σ", "dimension": "▦", "detail": "·"},
        kind_labels={"measure": "maat", "dimension": "dimensie", "detail": "detail"},
        chosen_keys=state["objects"],
        filter_keys=state["filters"],
        chosen=chosen,
        filter_options=filter_options,
        filter_values=state["values"],
        columns=columns,
        rows=rows,
        totals=totals,
        drill_aliases=drill_aliases,
        drill_urls=DRILL_URLS,
        message=message,
        sort=state["sort"],
        direction=state["direction"],
        page=state["page"],
        per_page=PER_PAGE,
        has_prev=state["page"] > 1,
        has_next=has_next,
        report_id=report.id if report else None,
        name=report.name if report else "",
        description=(report.description or "") if report else "",
        is_shared=report.is_shared if report else True,
        # A shipped report has no owner and therefore belongs to the tenant:
        # anyone who may see it may adjust it (see `update_report`).
        is_owner=bool(report) and (report.owner_email is None
                                   or report.owner_email == _viewer(request)),
        is_builtin=bool(report and report.builtin_key),
        query=_query_string(state),
        error=error,
        toast=toast,
        csrf_token=_csrf(request),
        nav_items=admin_nav(NAV),
    )


def _viewer(request: Request) -> str:
    """The signed-in e-mail, read back from the session cookie."""
    from app.domains.auth.api import read_session_value

    return read_session_value(request.cookies.get(SESSION_COOKIE)) or ""


# ── The list (design-system C1) ──────────────────────────────────────────────

def _list_view(request: Request, db: Session, email: str) -> ReportListView:
    params = request.query_params
    q = (params.get("q") or "").strip()
    owner = params.get("owner") or "all"
    shared = params.get("shared") or "all"
    reports = list_saved_reports(db, tenant_id=_tenant(request), viewer=email,
                                q=q, owner=owner, shared=shared)
    return ReportListView(
        reports=reports,
        classes_per_report={r.id: classes_of(r) for r in reports},
        owned={r.id: (r.owner_email == email or r.owner_email is None)
               for r in reports},
        q=q, owner=owner, shared=shared,
        csrf_token=_csrf(request),
        nav_items=admin_nav(NAV),
    )


@router.get("/admin/rapporten", response_class=HTMLResponse)
def reports_index(request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui)):
    view = _list_view(request, db, email)
    template = "_rp_kaarten.html" if is_fragment_request(request) \
        else "admin_rapporten.html"
    return templates.TemplateResponse(request, template, view.as_context())


@router.get("/admin/rapporten/lijst", response_class=HTMLResponse)
def reports_list_fragment(request: Request, db: Session = Depends(get_db),
                          email: str = Depends(require_admin_ui)):
    return templates.TemplateResponse(request, "_rp_kaarten.html",
                                      _list_view(request, db, email).as_context())


# ── The panel ────────────────────────────────────────────────────────────────
# The static paths come first: `/{report_id}` would otherwise swallow "nieuw".

@router.get("/admin/rapporten/nieuw", response_class=HTMLResponse,
            dependencies=[Depends(require_admin_ui)])
def report_new(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "admin_rapport_paneel.html",
        _panel(request, db, _read_state(request.query_params)).as_context())


@router.get("/admin/rapporten/paneel", response_class=HTMLResponse,
            dependencies=[Depends(require_admin_ui)])
def report_panel_fragment(request: Request, db: Session = Depends(get_db),
                          report: int | None = None):
    """The panel body after any change — add an object, set a filter, sort, page.

    One fragment for all of it, on purpose. Swapping only the result would leave
    the hidden state inputs and the screen to drift apart, and that is the bug
    class this whole design is built to avoid.
    """
    bewaard = None
    if report:
        bewaard = get_saved_report(db, report, tenant_id=_tenant(request),
                                   viewer=_viewer(request))
    return templates.TemplateResponse(
        request, "_rp_paneel.html",
        _panel(request, db, _read_state(request.query_params), report=bewaard).as_context())


@router.get("/admin/rapporten/export.ods")
def report_export(request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui), report: int | None = None):
    """The report on screen as a spreadsheet — sheet 1 the table, sheet 2 the detail."""
    tenant_id = _tenant(request)
    state = _read_state(request.query_params)
    bewaard = None
    if report:
        bewaard = get_saved_report(db, report, tenant_id=tenant_id, viewer=email)
        if not state["objects"] and bewaard is not None:
            # A bare link to a saved report's export: take its own selection.
            state = _state_from_selection(selection_of(bewaard))
    if not state["objects"]:
        # Nothing chosen is not an error worth a page of its own — send the
        # visitor back to where reports are. The panel hides the button in this
        # state, so getting here means the URL was typed.
        return RedirectResponse("/admin/rapporten", status_code=302)
    titel = bewaard.name if bewaard else "Rapport"

    try:
        # No paging in an export: you take home the report, not the page.
        selection = _selection({**state, "page": 1})
        selection = Selection(
            object_keys=selection.object_keys, filters=selection.filters,
            sort=selection.sort, limit=5000, offset=0, layout=selection.layout)
        result = run_validated(db, selection, tenant_id=tenant_id)
        content = build_report_ods(db, result, selection, title=titel,
                                   tenant_id=tenant_id)
    except SelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    log_export(db, tenant_id=tenant_id, actor=email,
               kind="report" if bewaard else "ad-hoc", subject=titel,
               row_count=len(result.rows),
               filters=selection_to_dict(selection).get("filters"),
               saved_report_id=bewaard.id if bewaard else None)
    return Response(
        content=content, media_type=ODS_MEDIA_TYPE,
        headers={"Content-Disposition":
                 f'attachment; filename="{report_filename(titel)}"'},
    )


@router.get("/admin/rapporten/dataset/{fact_key}.ods")
def dataset_export(fact_key: str, request: Request,
                   db: Session = Depends(get_db),
                   email: str = Depends(require_admin_ui)):
    """One fact, flat, as a spreadsheet (#832).

    Same route and same output as when it shipped in phase 1; it moved here so one
    module owns `/admin/rapporten/*`.
    """
    tenant_id = _tenant(request)
    try:
        dataset, content = build_dataset_ods(db, fact_key, tenant_id=tenant_id)
    except SelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    log_export(db, tenant_id=tenant_id, actor=email, kind="dataset",
               subject=dataset.fact.key, row_count=len(dataset.rows))
    return Response(
        content=content, media_type=ODS_MEDIA_TYPE,
        headers={"Content-Disposition":
                 f'attachment; filename="{dataset_filename(dataset)}"'},
    )


@router.get("/admin/rapporten/{report_id}", response_class=HTMLResponse)
def report_open(report_id: int, request: Request, db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)):
    """Open a saved report in the panel.

    A report of another tenant, or somebody else's private one, is a 404 and not a
    403: a 403 would confirm that it exists.
    """
    report = get_saved_report(db, report_id, tenant_id=_tenant(request), viewer=email)
    if report is None:
        raise HTTPException(status_code=404, detail=_("Rapport niet gevonden"))

    try:
        selection = selection_of(report)
    except SelectionError as exc:
        # A report that references an object which no longer exists says so, by
        # name, instead of rendering a table that is quietly missing a column.
        return templates.TemplateResponse(
            request, "admin_rapport_paneel.html",
            _panel(request, db, _read_state(request.query_params), report=report,
                   error=str(exc)).as_context())

    state = _read_state(request.query_params)
    if not state["objects"]:
        state = _state_from_selection(selection, page=state["page"])
    mark_run(db, report)
    return templates.TemplateResponse(
        request, "admin_rapport_paneel.html",
        _panel(request, db, state, report=report).as_context())


# ── Saving (design-system P1: stay and toast) ────────────────────────────────

@router.post("/admin/rapporten", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def report_save(request: Request, db: Session = Depends(get_db),
                      email: str = Depends(require_admin_ui)):
    form = await request.form()
    name, description = str(form.get("name") or ""), str(form.get("description") or "")
    is_shared = str(form.get("is_shared") or "")
    state = _read_state(form)
    try:
        selection = _selection(state)
        report = save_report(db, tenant_id=_tenant(request), owner=email, name=name,
                             selection=selection, description=description,
                             is_shared=is_shared == "1")
    except (SavedReportError, SelectionError) as exc:
        # A failed save shows the banner AND no toast (P1).
        return templates.TemplateResponse(
            request, "_rp_paneel.html",
            _panel(request, db, state, error=str(exc)).as_context())
    return templates.TemplateResponse(
        request, "_rp_paneel.html",
        _panel(request, db, state, report=report, toast=True).as_context())


@router.post("/admin/rapporten/{report_id}", response_class=HTMLResponse,
             dependencies=[Depends(require_csrf)])
async def report_update(report_id: int, request: Request,
                        db: Session = Depends(get_db),
                        email: str = Depends(require_admin_ui)):
    report = get_saved_report(db, report_id, tenant_id=_tenant(request), viewer=email)
    if report is None:
        raise HTTPException(status_code=404, detail=_("Rapport niet gevonden"))
    form = await request.form()
    name, description = str(form.get("name") or ""), str(form.get("description") or "")
    is_shared = str(form.get("is_shared") or "")
    state = _read_state(form)
    try:
        selection = _selection(state)
        update_report(db, report, editor=email, name=name, selection=selection,
                      description=description, is_shared=is_shared == "1")
    except (SavedReportError, SelectionError) as exc:
        return templates.TemplateResponse(
            request, "_rp_paneel.html",
            _panel(request, db, state, report=report, error=str(exc)).as_context())
    return templates.TemplateResponse(
        request, "_rp_paneel.html",
        _panel(request, db, state, report=report, toast=True).as_context())


@router.post("/admin/rapporten/{report_id}/kopieren",
             dependencies=[Depends(require_csrf)])
def report_copy(report_id: int, request: Request, db: Session = Depends(get_db),
                email: str = Depends(require_admin_ui)):
    """"Kopiëren": your own copy. The original is never touched."""
    report = get_saved_report(db, report_id, tenant_id=_tenant(request), viewer=email)
    if report is None:
        raise HTTPException(status_code=404, detail=_("Rapport niet gevonden"))
    kopie = copy_report(db, report, owner=email)
    return Response(status_code=204,
                    headers={"HX-Redirect": f"/admin/rapporten/{kopie.id}"})


@router.post("/admin/rapporten/{report_id}/verwijderen",
             dependencies=[Depends(require_csrf)])
def report_delete(report_id: int, request: Request, db: Session = Depends(get_db),
                  email: str = Depends(require_admin_ui)):
    report = get_saved_report(db, report_id, tenant_id=_tenant(request), viewer=email)
    if report is None:
        raise HTTPException(status_code=404, detail=_("Rapport niet gevonden"))
    try:
        delete_report(db, report, actor=email)
    except SavedReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=204, headers={"HX-Redirect": "/admin/rapporten"})
