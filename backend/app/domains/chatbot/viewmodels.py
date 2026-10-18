"""View-models of the AI cost screen (#978)."""

from dataclasses import dataclass, field
from typing import Any

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class AiCostLine:
    """One line of the totals, already in words and numbers for the screen."""

    what: str
    provider: str
    calls: int
    tokens: str
    credits: str
    amount: str


@dataclass(frozen=True, kw_only=True)
class AiCallLine:
    """One call in the list. No payload: see `chatbot/costs.py`."""

    moment: str
    what: str
    actor: str
    #: The model and its provider in one column (#1925; Koen, 16 October 2026, "a").
    engine: str
    status_label: str
    status_tone: str
    duration: str
    cost: str


@dataclass(frozen=True, kw_only=True)
class AiCallListView(ViewModel):
    """`_ai_kosten_lijst.html`: the month's calls on the kit's table (#1925, #2109)."""

    columns: list[dict[str, Any]]

    calls: list[AiCallLine]
    page: int
    per_page: int
    # Every call of the month that matches the filters, counted (#1391, CR-11 W8).
    total: int
    pager_url: str
    empty_reason: str
    oob: bool = False
    sort: str = ""


@dataclass(frozen=True, kw_only=True)
class AiCostView(AiCallListView):
    """`admin_ai_kosten.html`: the toolbar and the month's totals above the list."""

    month: str
    month_label: str
    prev_month_url: str
    next_month_url: str
    totals: list[AiCostLine]
    totals_columns: list[dict[str, Any]]
    capability: str
    provider: str
    sort_options: list[tuple[str, str]]
    capability_options: list[tuple[str, str]]
    provider_options: list[tuple[str, str]]
    page_sizes: list[int]
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class AiContextListView(ViewModel):
    """`ai_context.html` and its fragment `_ai_context_lijst.html` (#2124): what
    Raakje knows on the kit's list, one segment at a time."""

    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    segment: str
    segments: list[dict[str, Any]]
    q: str
    total: int
    empty_reason: str
    oob: bool = False
    nav_items: list[Any] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class AiContextRecordView(ViewModel):
    """`ai_context_item.html` (#2124): one document, page or note, read or edited —
    what the row's disclosure showed and did, on a page of its own."""

    kind: str
    title: str
    badges: list[dict[str, str]]
    facts: list[dict[str, str]]
    primary: dict[str, str] | None
    actions: list[dict[str, Any]]
    way_back: dict[str, str]
    editing: bool
    #: The item as `context_item` gives it; `info` is its row, or None.
    item: dict[str, Any]
    info: dict[str, Any] | None
    form_url: str
    record_url: str
    csrf_token: str
    nav_items: list[Any] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class AiContextNoteNewView(ViewModel):
    """`ai_context_notitie_nieuw.html` (#2124): a new note, the form the list
    carried under its notes."""

    way_back: dict[str, str]
    csrf_token: str
    nav_items: list[Any] = field(default_factory=list)
