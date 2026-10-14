"""The Werkbank (#398, §20.5; on the kit since #1931): the list of tasks on the
list layout, one task on the record layout, and handling a task.

The list refreshes itself every 30 s (§20.5 — polling, no SSE). What a task is
about, who may see and handle it and what its next step is, is the service's
(`workflow.workbench`, behind `workflow.api`); this module reads the request,
words what the service found and chooses a template.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import (
    ROLE,
    SESSION_COOKIE,
    Right,
    csrf_token_for,
    get_user_roles,
    require_csrf,
    require_right,
)
from app.domains.workflow import api
from app.domains.workflow.api import TASK_CATEGORY, TASK_KIND, TASK_STATUS, TaskStatus
from app.domains.workflow.viewmodels import TaskView, WorkbenchView
from app.i18n import _
from app.kernel.codes import code_label, code_labels, code_of
from app.ui import (
    PER_PAGE_DEFAULT,
    PER_PAGE_OPTIONS,
    admin_nav,
    filterparams,
    is_fragment_request,
    list_return,
    per_page_from,
    record_frame,
    refusal_response,
    templates,
)

router = APIRouter(include_in_schema=False)

NAV = "/admin/werkbank"
#: The line both screens show a refusal on.
MESSAGE_LINE = "#werkbank-melding"
STATUSES = (TaskStatus.OPEN.value, TaskStatus.DONE.value, "all")
#: The list's orders: newest first unless asked otherwise.
SORT_DEFAULT = "-aangemaakt"
SORTS = (SORT_DEFAULT, "aangemaakt", "soort", "-soort")


def _roles(db: Session, email: str) -> list[str]:
    return sorted(get_user_roles(db, email))


def _csrf(request: Request) -> str:
    return csrf_token_for(request.cookies.get(SESSION_COOKIE) or "")


def _geld(amount) -> str:
    return "€ " + templates.env.filters["geld"](amount)


def _moment(value) -> str:
    return templates.env.filters["short_datetime"](value) if value else ""


def _kind_label(db: Session, kind) -> str:
    # §2.12: never show a raw code (#630).
    return code_label(TASK_KIND.name, kind) or _("Overige taak")


def _category(kind) -> str:
    """The part of a kind before its dot: the category, stored nowhere (§B5.3)."""
    return (code_of(kind) or "").split(".", 1)[0]


def _age(days: int | None) -> str:
    if days is None:
        return "—"
    if days == 0:
        return _("vandaag")
    return _("1 dag") if days == 1 else _("%(n)d dagen") % {"n": days}


def _subject_line(subject: dict[str, Any] | None) -> str:
    """What a task is about, on one line under its title — what the card of
    before never showed. Each subject's own domain supplied the values."""
    if not subject:
        return ""
    kind = subject["type"]
    if kind == "payment_record":
        who = (
            _("Terugbetaling aan %(name)s") if subject["refund"] else _("Betaling van %(name)s")
        ) % {"name": subject["name"] or "—"}
        return f"{who} · {_geld(subject['amount'])}"
    if kind == "form_submission":
        return _("Formulier %(form)s · inzending #%(number)s") % {
            "form": subject["form"] or "—",
            "number": subject["number"],
        }
    if kind == "email_log":
        return subject["subject"] or subject["recipient"]
    if kind == "kernel_job":
        return _("%(name)s · %(attempts)s/%(max)s pogingen") % {
            "name": subject["name"],
            "attempts": subject["attempts"],
            "max": subject["max_attempts"],
        }
    return ""


def _status_badge(db: Session, task) -> dict[str, str]:
    done = api.is_done(task)
    return {
        "label": code_label(TASK_STATUS.name, task.status),
        "tone": "green" if done else "yellow",
    }


def _handle_attrs(task_id: int) -> str:
    """The row's own "Afgehandeld": a POST without a decision. The answer is the
    list again, in the state the address bar carries."""
    return (
        f'hx-post="{NAV}/taken/{task_id}/afgehandeld" hx-target="#werkbank-lijst" '
        'hx-swap="innerHTML" data-task-handle'
    )


def _row_steps(db: Session, task) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """The row's button and its `⋯` items, from the kind's own next step. A step
    to a subject that has no address (it is gone) is left out."""
    steps = api.next_step(task)
    url = api.subject_url(db, task)

    def _shaped(step: dict[str, Any]) -> dict[str, Any] | None:
        if step["do"] == "handle":
            return {"label": step["label"], "attrs": _handle_attrs(task.id)}
        return {"label": step["label"], "href": url} if url else None

    button = _shaped(steps["button"]) if steps["button"] else None
    menu = [item for item in (_shaped(step) for step in steps["menu"]) if item]
    return button, menu


def _workbench_view(request: Request, db: Session, email: str, *, oob: bool) -> WorkbenchView:
    from app.config import settings

    roles = _roles(db, email)
    state = filterparams(request)
    status = state.get("status") or STATUSES[0]
    if status not in STATUSES:
        status = STATUSES[0]
    q = (state.get("q") or "").strip()
    kind = (state.get("kind") or "").strip()
    # The role filter offers the viewer's own roles: a task of another role is
    # not on their list anyway.
    role = (state.get("rol") or "").strip()
    if role not in roles:
        role = ""
    sort = (state.get("sort") or "").strip()
    if sort not in SORTS:
        sort = SORT_DEFAULT
    per_page = per_page_from(state.get("per_page"))
    try:
        page = max(1, int(state.get("page") or 1))
    except ValueError:
        page = 1

    # #674: `api.tasks` beside `open_tasks` on purpose — the latter also feeds
    # the sweep's idempotency and the menu's counter. The role filter of the
    # viewer always holds, on handled tasks as on open ones.
    mine = api.tasks(db, roles, status="all")
    tasks = [t for t in mine if status == "all" or code_of(t.status) == status]
    # One grouped filter (#549), data-driven from the dotted kind: with a dot
    # it is one kind, without it a whole category, empty everything.
    if "." in kind:
        tasks = [t for t in tasks if code_of(t.kind) == kind]
    elif kind:
        tasks = [t for t in tasks if _category(t.kind) == kind]
    if role:
        tasks = [t for t in tasks if code_of(t.required_role) == role]
    subjects = api.subjects(db, tasks)
    lines = {t.id: _subject_line(subjects.get(t.id)) for t in tasks}
    kinds = {t.id: _kind_label(db, t.kind) for t in tasks}
    # Free search (#592) on the title, on the kind and — since #1931 — on what
    # the task is about.
    term = q.lower()
    if term:
        tasks = [
            t
            for t in tasks
            if term in (t.title or "").lower()
            or term in kinds[t.id].lower()
            or term in lines[t.id].lower()
        ]
    if sort in ("soort", "-soort"):
        tasks = sorted(tasks, key=lambda t: (kinds[t.id].lower(), t.id), reverse=sort == "-soort")
    else:
        tasks = sorted(tasks, key=lambda t: (t.created_at, t.id), reverse=sort == SORT_DEFAULT)

    total = len(tasks)
    page = min(page, max(1, -(-total // per_page)))
    shown = tasks[(page - 1) * per_page : page * per_page]

    link_state = {
        "status": status if status != STATUSES[0] else "",
        "q": q,
        "kind": kind,
        "rol": role,
    }

    def _query(**more: Any) -> str:
        merged = {**link_state, "per_page": per_page, **more}
        return urlencode({k: v for k, v in merged.items() if v != ""})

    way_back = list_return(
        NAV,
        **link_state,
        sort=sort if sort != SORT_DEFAULT else "",
        page=page if page > 1 else "",
        per_page=per_page if per_page != PER_PAGE_DEFAULT else "",
    )
    role_labels = dict(code_labels(ROLE.name))
    rows = []
    for task in shown:
        button, menu = _row_steps(db, task)
        rows.append(
            {
                "id": task.id,
                "title": task.title,
                "href": f"{NAV}/taken/{task.id}?terug={quote(way_back, safe='/')}",
                "subject": lines[task.id],
                "kind": kinds[task.id],
                "moment": _moment(task.created_at),
                "age": _age(api.age_days(task)),
                "state": _status_badge(db, task),
                "role": role_labels.get(code_of(task.required_role) or "", ""),
                "action": button,
                "menu": menu,
            }
        )

    def _head(
        key: str, label: str, cell: str, ascending: str, descending: str, **extra: Any
    ) -> dict[str, Any]:
        turned = descending if sort == ascending else ascending
        head: dict[str, Any] = {
            "key": key,
            "label": label,
            "cell": cell,
            "sort_url": f"{NAV}?{_query(sort=turned)}",
            "sort_page_url": f"{NAV}?{_query(sort=turned)}",
            **extra,
        }
        if sort in (ascending, descending):
            head["sorted"] = "asc" if sort == ascending else "desc"
        return head

    counts = api.figures(mine)
    status_labels = dict(code_labels(TASK_STATUS.name))
    # One grouped filter (#549), data-driven: the kinds of the viewer's own
    # tasks, under their category, with the whole category first.
    kind_names = dict(code_labels(TASK_KIND.name))
    groups: dict[str, list[tuple[str, str]]] = {}
    for code in sorted({code_of(t.kind) or "" for t in mine}):
        if "." in code:
            groups.setdefault(_category(code), []).append((code, kind_names.get(code, code)))
    # The categories in the code list's order; one it does not know (a workflow
    # definition is data and may bring a kind) follows, under its own code.
    known = [category for category, _label in code_labels(TASK_CATEGORY.name)]
    ordered = [c for c in known if c in groups] + sorted(c for c in groups if c not in known)
    kind_groups = []
    for category in ordered:
        label = code_label(TASK_CATEGORY.name, category)
        whole = (category, _("Alle %(category)s") % {"category": label.lower()})
        kind_groups.append((label, [whole] + groups[category]))
    if q:
        empty_reason = _("Geen taken gevonden voor “%(q)s”.") % {"q": q}
    elif kind or role:
        empty_reason = _("Geen taken met deze filters.")
    elif status == TaskStatus.DONE.value:
        empty_reason = _("Geen afgehandelde taken.")
    elif status == "all":
        empty_reason = _("Nog geen taken.")
    else:
        empty_reason = _("Geen open taken — alles is behartigd.")
    return WorkbenchView(
        rows=rows,
        columns=[
            # #1990: a title takes the room the table has to spare, so it reads
            # on one or two lines on a wide screen; the button stays at the right.
            {"key": "taak", "label": _("Taak"), "cell": "name", "width": "rest"},
            _head("soort", _("Soort"), "context", "soort", "-soort", width=176),
            _head("aangemaakt", _("Aangemaakt"), "moment", "aangemaakt", "-aangemaakt"),
            {
                "key": "open_sinds",
                "label": _("Open sinds"),
                "cell": "extra",
                "num": True,
                "priority": 1,
                "width": 100,
            },
            {"key": "status", "label": _("Status"), "cell": "status"},
            {"key": "rol", "label": _("Rol"), "cell": "extra", "priority": 2, "width": 148},
            # The widest step ("Open in de e-maillog") with its ⋯ needs 240 px.
            {"key": "acties", "label": _("Acties"), "cell": "actions", "width": 240},
        ],
        segments=[
            {"value": "open", "label": status_labels["open"], "count": counts["open"]},
            {"value": "done", "label": status_labels["done"], "count": counts["done"]},
            {"value": "all", "label": _("Alle")},
        ],
        figures=[
            {
                "value": str(counts["open"]),
                "label": _("Open"),
                "title": _("Open taken voor jouw rollen."),
            },
            {
                "value": str(counts["today"]),
                "label": _("Vandaag"),
                "title": _("Taken die vandaag aangemaakt zijn."),
            },
            {
                "value": str(counts["old"]),
                "label": _("Ouder dan een week"),
                "title": _("Open taken die langer dan zeven dagen open staan."),
                "warning": counts["old"] > 0,
            },
        ],
        status=status,
        q=q,
        kind=kind,
        kind_groups=kind_groups,
        role=role,
        roles=[(code, role_labels.get(code, code)) for code in roles],
        sort=sort,
        sort_options=[
            (SORT_DEFAULT, _("Nieuwste eerst")),
            ("aangemaakt", _("Oudste eerst")),
            ("soort", _("Soort")),
        ],
        page=page,
        per_page=per_page,
        total=total,
        page_sizes=list(PER_PAGE_OPTIONS),
        pager_url=f"{NAV}?{_query(sort=sort)}",
        empty_reason=empty_reason,
        workbench_enabled=settings.workbench_enabled,
        csrf_token=_csrf(request),
        nav_items=[] if oob else admin_nav(NAV, request),
        oob=oob,
    )


@router.get(NAV, response_class=HTMLResponse)
def werkbank(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.WORKBENCH_USE)),
):
    """The list of tasks (#1931). Its state — status, search, kind, role, sort,
    page, page size — lives in the URL; the toolbar asks this same address for
    the fragment."""
    fragment = is_fragment_request(request)
    view = _workbench_view(request, db, email, oob=fragment)
    template = "_werkbank_lijst.html" if fragment else "werkbank.html"
    return templates.TemplateResponse(request, template, view.as_context())


@router.get(f"{NAV}/lijst", response_class=HTMLResponse)
def werkbank_lijst(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.WORKBENCH_USE)),
):
    """The polling fragment: only the list, refreshed every 30 s (§20.5). The
    toolbar stands outside it; the state comes from the address the page is on
    (`filterparams`), so a refresh keeps the search, the filters and the page."""
    view = _workbench_view(request, db, email, oob=True)
    return templates.TemplateResponse(request, "_werkbank_lijst.html", view.as_context())


def _subject_rows(db: Session, task, subject: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The card Onderwerp: what the task is about, as facts. A conventional kind
    carries its icon, anything else its label (end state §2.2)."""
    from app.domains.workflow.api import SubjectType

    if task.subject_type is SubjectType.FORM_SUBMISSION:
        from app.domains.forms.api import submission_view

        # #704: `subject_id` is text since that change; `submission_view`
        # expects a number.
        answers = submission_view(db, int(task.subject_id))
        if not answers:
            return []
        (_from, name), (_mail, address), (_received, received) = answers[:3]
        rows: list[dict[str, Any]] = [
            {"icon": "user", "value": name},
            {
                "icon": "mail",
                "value": address,
                "href": f"mailto:{address}" if "@" in address else None,
            },
            {"icon": "clock", "value": _("Ontvangen %(when)s") % {"when": received}},
        ]
        return rows + [{"label": label, "value": value or "—"} for label, value in answers[3:]]
    if task.subject_type is SubjectType.KERNEL_JOB:
        # There is no screen for kernel jobs, so this IS the way to the subject
        # (#822): name, status, attempts and the last error.
        from app.kernel.jobs import job_details

        job = job_details(db, task.subject_id)
        if job is None:
            return []
        return [
            {"label": _("Job"), "value": job["name"]},
            {"label": _("Status"), "value": job["status"]},
            {"label": _("Pogingen"), "value": f"{job['attempts']}/{job['max_attempts']}"},
            {"label": _("Laatste fout"), "value": (job["last_error"] or "—")[:500]},
        ]
    if not subject:
        return []
    if task.subject_type is SubjectType.PAYMENT_RECORD:
        rows = [
            {"icon": "user", "value": subject["name"] or "—"},
            {
                "label": _("Terug te betalen") if subject["refund"] else _("Bedrag"),
                "value": _geld(subject["amount"]),
            },
            {
                "label": _("Status"),
                "value": code_label("payment_status", subject["status"]),
            },
            {
                "label": _("Wijze"),
                "value": code_label("payment_method", subject["method"]),
            },
        ]
        if subject["gateway_status"]:
            # The provider's own word: on a mismatch it says more than ours.
            rows.append({"label": _("Mollie meldt"), "value": subject["gateway_status"]})
        return rows
    if task.subject_type is SubjectType.EMAIL_LOG:
        rows = [
            {
                "icon": "mail",
                "value": subject["recipient"] or "—",
                "href": f"mailto:{subject['recipient']}" if subject["recipient"] else None,
            },
            {"label": _("Onderwerp"), "value": subject["subject"] or "—"},
        ]
        if subject["error"]:
            rows.append({"label": _("Laatste fout"), "value": subject["error"]})
        return rows
    return []


def _task_view(request: Request, db: Session, email: str, task_id: int, **extra) -> TaskView:
    roles = _roles(db, email)
    frame = record_frame(request, db, NAV)
    way_back = frame["way_back"]
    task = api.task_for(db, task_id, roles)
    nav = admin_nav(NAV, request)
    if task is None:
        return TaskView(
            task_id=None,
            record_head={"title": _("Taak niet gevonden")},
            way_back=way_back,
            head_editing=False,
            summary={},
            subject_rows=[],
            subject_link=None,
            signpost=False,
            done=False,
            decision="",
            done_by="",
            done_at="",
            here=NAV,
            error=None,
            csrf_token=_csrf(request),
            nav_items=nav,
        )
    done = api.is_done(task)
    signpost = api.is_signpost(task)
    subject = api.subjects(db, [task]).get(task.id)
    url = api.subject_url(db, task)
    keep = way_back["keep"]
    here = f"{NAV}/taken/{task.id}" + (f"?{keep}" if keep else "")
    badge = _status_badge(db, task)
    kind = _kind_label(db, task.kind)
    role_label = code_label(ROLE.name, task.required_role)
    facts: list[dict[str, Any]] = [
        {"text": kind},
        {"text": _("Aangemaakt %(when)s") % {"when": _moment(task.created_at)}},
    ]
    line = _subject_line(subject)
    if url and line:
        facts.append({"text": line, "href": url, "kind": "reference"})
    # The primary: a signpost goes to its subject (#822); a task that is handled
    # here opens its decision (the record's edit state); a done task has none.
    primary = None
    if not done:
        if signpost:
            primary = {"label": _("Ga naar het onderwerp"), "href": url} if url else None
        else:
            primary = {
                "label": _("Afhandelen"),
                "href": here + ("&" if keep else "?") + "bewerken=1",
            }
    category = code_label(TASK_CATEGORY.name, _category(task.kind)) or kind
    values: dict[str, Any] = {
        "task_id": task.id,
        "record_head": {
            "title": task.title,
            "badges": [badge],
            "facts": facts,
            "primary": primary,
        },
        "way_back": way_back,
        "head_editing": frame["head_editing"] and api.may_handle(task),
        "summary": {
            "state": badge,
            "figures": [
                {"label": _("Soort"), "value": category},
                {"label": _("Rol"), "value": role_label},
                {"label": _("Open sinds"), "value": _age(api.age_days(task))},
            ],
        },
        "subject_rows": _subject_rows(db, task, subject),
        # A signpost's way to its subject is the head's primary; anything else
        # gets it as a quiet button under the facts.
        "subject_link": url if url and not signpost else None,
        "signpost": signpost,
        "done": done,
        "decision": task.decision or "",
        "done_by": task.done_by or "",
        "done_at": _moment(task.done_at),
        "here": here,
        "error": None,
        "csrf_token": _csrf(request),
        "nav_items": nav,
    }
    values.update(extra)
    return TaskView(**values)


@router.get(NAV + "/taken/{task_id}", response_class=HTMLResponse)
def taak_detail(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.WORKBENCH_USE)),
):
    """One task on the record layout (#1931). A task of another role, like one
    that does not exist, is a page that says "Taak niet gevonden" and nothing of
    the task — a 200, as it always was: a row that went stale is opened by a
    boosted click, and htmx swaps no 404 in, so the visitor would see nothing."""
    view = _task_view(request, db, email, task_id)
    return templates.TemplateResponse(request, "werkbank_taak.html", view.as_context())


def _refused(request: Request, message: str):
    """Why a task was not ticked off, on the message line both screens carry —
    an HTML 422, which the browser swaps in (#1515)."""
    return refusal_response(request, [{"field": "", "message": message}], MESSAGE_LINE)


@router.post(
    NAV + "/taken/{task_id}/afgehandeld",
    response_class=HTMLResponse,
    dependencies=[Depends(require_csrf)],
)
def taak_afhandelen(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(require_right(Right.WORKBENCH_USE)),
    besluit: str = Form(""),
    standalone: str = Form(""),
):
    """Tick a task off; where the answer lands depends on the screen (#666).

    From the list the row's button posts without a decision and gets the list
    back, in the state its address carries. From the record (`standalone`) the
    form's save posts the decision and gets a redirect back to where the record
    was opened from. A task that is not the viewer's is "not found"; a signpost
    task is refused, on either screen: its subject's own screen closes it
    (#822).
    """
    roles = _roles(db, email)
    try:
        task = api.handle(db, task_id, roles, done_by=email, decision=besluit.strip() or None)
    except api.NotHandledHere:
        return _refused(request, _("Deze taak handel je af op het scherm van het onderwerp."))
    if task is None:
        return _refused(request, _("Taak niet gevonden."))
    if standalone:
        back = record_frame(request, db, NAV)["way_back"]["href"]
        return Response(status_code=204, headers={"HX-Redirect": back})
    view = _workbench_view(request, db, email, oob=True)
    answer = templates.TemplateResponse(request, "_werkbank_lijst.html", view.as_context())
    answer.headers["HX-Retarget"] = "#werkbank-lijst"
    answer.headers["HX-Reswap"] = "innerHTML"
    return answer
