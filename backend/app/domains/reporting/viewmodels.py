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
    #: (niveau, naam van het niveau erboven) voor elk gekozen niveau dat omhoog
    #: kan (#899 stap 2). Zonder de weg terug is drillen eenrichtingsverkeer.
    rollup_levels: list[tuple[str, str]]
    #: Classes the user folded shut (#872). The closed set, not the open one:
    #: every class starts open, so the default state is the empty list.
    closed_classes: list[str]
    #: Per class, how many objects are chosen — what a folded class still shows.
    chosen_per_class: dict[str, int]
    #: Per hiërarchie: het niveau waarop de filterknop filtert (#912). Het diepste
    #: dat in het rapport staat — het aanbod gaat over waar je bent.
    filter_level: dict[str, str]
    filter_keys: list[str]

    # ── Selection ───────────────────────────────────────────────────────────
    chosen: list[Any]
    # Per filter object: its offered values (empty = free text) and current value.
    filter_options: dict[str, list[str]]
    # Per filter object: the relative values it may take (#847), as
    # (value, label). Empty for an object where "today" or "me" means nothing.
    filter_relative: dict[str, list[tuple[str, str]]]
    # #1445: a list per filter — the ticked values, or the one search term.
    filter_values: dict[str, list[str]]
    # #1456: the filter whose dropdown is open, so a re-render keeps it open.
    open_filter: str

    # ── Result ──────────────────────────────────────────────────────────────
    # True when `message` is a REFUSAL and not an absence. The two are drawn
    # differently on purpose: a refusal asks the user to change something, an
    # empty result does not (#877).
    refused: bool
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
    # Which population the report counts — the fact, as (name, grain). None while
    # the selection cannot say yet. The panel shows it so the difference between
    # "every household" and "households with a membership" is on the screen
    # instead of inside the name of a measure (#871).
    population: Any | None
    # "The user cleared the column axis", as opposed to "there is none yet" — the
    # panel needs the difference to keep the "geen" button pressed (#873).
    no_column: bool
    message: str | None
    # #847: a report that fills in the viewer's own identity says so, or somebody
    # shares a link and the receiver cannot explain why he sees something else.
    personal: bool
    sort: str
    direction: str
    page: int
    per_page: int
    # The rows of the whole table, not the page (#1391, CR-11 W8); 0 where
    # nothing pages (a crosstab, a chart, a refusal).
    total_rows: int

    # ── The report this panel is showing, if it was saved ───────────────────
    report_id: int | None
    name: str
    description: str
    is_shared: bool
    # #1092: may the viewer delete this report — theirs or nobody's, and not one
    # that feeds a dashboard tile. Decided in the service (`may_delete`), not here.
    is_deletable: bool
    # The label of the dashboard tile this report feeds, or None. Editing such a
    # report changes the landing page; the panel says so.
    dashboard_tile: str | None

    # The panel's own state as a query string, for the export link and paging.
    query: str

    error: str | None = None
    # P1: a successful save stays on the screen and shows a toast; a failed save
    # shows the banner AND no toast. Two fields, never both set.
    toast: bool = False
    csrf_token: str = ""
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class AssistantTriggerView(ViewModel):
    """`_assistant_trigger.html` — the one trigger in the top bar (CR-11 K8,
    #1562). `shown`: there is an Assistent for this visitor (both switches, the
    module, the role). `available`: the screen's module is one the assistant
    knows; otherwise the button is dimmed but focusable."""

    shown: bool
    available: bool


@dataclass(frozen=True, kw_only=True)
class AssistantPanelView(ViewModel):
    """`_assistant_panel.html` — what stands in the panel for one screen: its
    context (`assistant_context.AssistantContext`: the line under the title,
    where a question goes, three suggestions, or why asking is off).

    The conversation lives in the panel and not on the server: a new context
    starts a fresh one and nothing is kept between sessions (CR-07 §10)."""

    ctx: Any
    # Which speech path the microphone button uses (#917), from the config.
    stt_mode: str


@dataclass(frozen=True, kw_only=True)
class AssistantTurnView(ViewModel):
    """`_rp_raakje_antwoord.html` — one question with its answer.

    `payload` is what the provider was handed, verbatim, for the "wat zag Mistral"
    fold-out (§5.7). It is on the turn and not on the page because it belongs to
    this answer: the promise being checked is about this question, not about the
    session.
    """

    vraag: str
    antwoord: str
    error: str
    payload: str
    history: str
    # #1562 (§3.15): what the last report of this turn shows beside the words
    # — a figure, or a small table with the address of the whole list
    # (`assistant_answer`). None when the turn ran no report.
    figure: Any = None
    table: Any = None
    more_href: str = ""
