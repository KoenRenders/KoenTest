"""View-models van het mdm-component (#643).

Wat het ledenscherm van zijn route krijgt, getypeerd en op één plek. Zie
`app/ui/viewmodel.py` voor het waarom.
"""

from dataclasses import dataclass, field
from typing import Any

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class LedenView(ViewModel):
    """`leden.html` and its fragment `_leden_lijst.html` (#1899: the list-page
    layout — the title row with its figures, the toolbar, the kit's table).

    The fragment is rendered on its own at a search, a filter, a sort and a page,
    so everything it needs stands here."""

    #: One per household: {id, name, address, persons, badge (label, tone)}.
    rows: list[dict[str, Any]]
    columns: list[dict[str, Any]]
    segments: list[dict[str, Any]]
    #: The three figures of the title row (`ui.figures`).
    figures: list[dict[str, Any]]
    # The list's state; the toolbar reads it back.
    status: str
    q: str
    jaar: int | None
    jaren: list[int]
    sort: str
    sort_options: list[tuple[str, str]]
    page: int
    per_page: int
    total: int
    page_sizes: list[int]
    pager_url: str
    empty_reason: str

    csrf_token: str
    #: The fragment refreshes the toolbar's count and segment counts out-of-band.
    oob: bool = False
    # Only the full page carries the navigation; the fragment does not.
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class HouseholdRecordView(ViewModel):
    """`leden_gezin.html` — the household's record (#1899; end state §5.2)."""

    family_id: int
    page_title: str
    #: `ui.record_header` and `ui.related_tabs`, as data (`mdm.household_record_head`,
    #: `mdm.gezin_tabs`), with the way back (`app.ui.record_frame`).
    record_head: dict[str, Any]
    record_tabs: list[dict[str, Any]]
    way_back: dict[str, Any]
    head_editing: bool
    #: `ui.summary_card`: {state, figures}.
    summary: dict[str, Any]
    #: The persons and the address: membership's `HouseholdGroup`, the cards of
    #: Mijn gezin.
    group: Any
    edit: bool
    #: The page answers a save: it says "Opgeslagen ✓".
    saved: bool
    #: The membership years, newest first: {id, year, active, waiting}.
    years: list[dict[str, Any]]
    board_member_id: str
    board_member_name: str
    #: (person id, name) for the select, in edit mode only.
    board_options: list[tuple[str, str]]

    csrf_token: str
    nav_items: list[dict[str, Any]] = field(default_factory=list)
