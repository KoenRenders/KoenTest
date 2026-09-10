"""View-models of the reporting screens (#833).

What each screen gets from its route, typed, on one place — so a wrong or
forgotten key is an error in the route instead of an empty box on the screen, and
`tests/test_template_variables_gate.py` can prove statically that the templates
ask for nothing that is not promised here.
"""
from dataclasses import dataclass, field
from typing import Any

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class ReportListView(ViewModel):
    """`admin_rapporten.html` and its fragment `_rp_kaarten.html`.

    The fragment is rendered on its own when the filter bar changes, so everything
    it needs is here and not in a `{% set %}` on the page — there it would not
    exist in the fragment.
    """

    reports: list[Any]
    # Per report id: the universe classes it touches, and whether the viewer owns
    # it. Derived in the route, because a template that derives state is a second
    # place where the rule lives (design-system §8.3).
    classes_per_report: dict[int, list[str]]
    owned: dict[int, bool]
    # Per report id: the icon name of its shape, and the label behind it. Derived
    # in the route — a template that derives state is a second place where the
    # rule lives (design-system §8.3).
    shapes: dict[int, str]
    shape_labels: dict[str, str]

    # Active filter state — the bar reads it back.
    q: str
    owner: str
    shared: str

    csrf_token: str
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ReportPanelView(ViewModel):
    """`admin_rapport_paneel.html` and its result fragment `_rp_resultaat.html`.

    The panel is one screen with three regions (CR-06 §5): the objects to choose
    from, the selection with its filters, and the result. Its whole state lives in
    the query string, so every change is one htmx request and a shared link opens
    the same report.
    """

    # ── Objects pane ────────────────────────────────────────────────────────
    # [(class name, [object, …]), …] — the universe, grouped as a user thinks.
    classes: list[tuple[str, list[Any]]]
    # The same objects by key, so a filter row can name its object without the
    # template looking it up — a template that looks things up is a template that
    # holds logic (design-system §8.3).
    objects_by_key: dict[str, Any]
    # The type icon and its tooltip, per object kind. Here and not in the template
    # for the same reason: a label is copy, and copy lives in one place.
    kind_symbols: dict[str, str]
    kind_labels: dict[str, str]
    chosen_keys: list[str]
    filter_keys: list[str]

    # ── Selection ───────────────────────────────────────────────────────────
    chosen: list[Any]
    # Per filter object: its offered values (empty = free text) and current value.
    filter_options: dict[str, list[str]]
    filter_values: dict[str, str]

    # ── Result ──────────────────────────────────────────────────────────────
    # None until at least one measure is chosen; `message` says why.
    columns: list[Any]
    rows: list[dict[str, Any]]
    totals: dict[str, Any]
    drill_aliases: dict[str, str]
    drill_urls: dict[str, str]
    # The crosstab, as `ui.pivot_table()` reads it — None when the shape is a
    # table. Never both: one selection, one drawing.
    pivot: dict[str, Any] | None
    # The chart, as `ui.chart_*()` reads it — None unless the shape is a chart.
    # When it is set, `pivot` is set too: the table under a chart is its text
    # alternative and keeps rendering (#835).
    chart: dict[str, Any] | None
    layout: str
    pivot_column: str
    message: str | None
    sort: str
    direction: str
    page: int
    per_page: int
    has_prev: bool
    has_next: bool

    # ── The report this panel is showing, if it was saved ───────────────────
    report_id: int | None
    name: str
    description: str
    is_shared: bool
    is_owner: bool
    is_builtin: bool

    # The panel's own state as a query string, for the export link and paging.
    query: str

    error: str | None = None
    # P1: a successful save stays on the screen and shows a toast; a failed save
    # shows the banner AND no toast. Two fields, never both set.
    toast: bool = False
    csrf_token: str = ""
    nav_items: list[dict[str, Any]] = field(default_factory=list)
