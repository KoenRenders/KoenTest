"""View-models of the workbench (#1931): what each screen gets from its route."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class WorkbenchView(ViewModel):
    """`werkbank.html` and its fragment `_werkbank_lijst.html`: the list of
    tasks on the kit's table. The toolbar stands outside the fragment, so the
    poll and a search cannot wipe each other; the page and the fragment get the
    same model."""

    #: One dict per row: id, title, href, subject, kind, moment, age, state
    #: {label, tone}, role, action (`ui.row_actions_cell`) and menu.
    rows: list[dict[str, Any]]
    columns: list[dict[str, Any]]
    segments: list[dict[str, Any]]
    figures: list[dict[str, Any]]
    status: str
    q: str
    kind: str
    #: The kind filter's groups: [(category label, [(value, label), …]), …].
    kind_groups: list[tuple[str, list[tuple[str, str]]]]
    role: str
    roles: list[tuple[str, str]]
    sort: str
    sort_options: list[tuple[str, str]]
    page: int
    per_page: int
    total: int
    page_sizes: list[int]
    pager_url: str
    empty_reason: str
    workbench_enabled: bool
    csrf_token: str
    nav_items: list[dict[str, Any]] = field(default_factory=list)
    #: The fragment carries the toolbar's count and segment counts out-of-band.
    oob: bool = False


@dataclass(frozen=True, kw_only=True)
class TaskView(ViewModel):
    """`werkbank_taak.html`: one task on the record layout — the head, the
    summary card, the card Onderwerp and, for a task that is handled here, the
    card Besluit, in read mode or with the decision field open."""

    #: None when the task does not exist for this viewer.
    task_id: int | None
    #: `ui.record_header`: title, badges, facts, primary, secondary, actions.
    record_head: dict[str, Any]
    way_back: dict[str, Any]
    head_editing: bool
    #: `ui.summary_card`: state and figures.
    summary: dict[str, Any]
    #: The card Onderwerp: [{label, value} or {icon, value, href?}, …] and the
    #: address of the subject's own screen, where it is not the head's primary.
    subject_rows: list[dict[str, Any]]
    subject_link: str | None
    #: A subject with a screen of its own: no decision here (#822).
    signpost: bool
    done: bool
    decision: str
    done_by: str
    done_at: str
    #: Where the record's own address is, without the edit state.
    here: str
    error: str | None
    csrf_token: str
    nav_items: list[dict[str, Any]] = field(default_factory=list)
