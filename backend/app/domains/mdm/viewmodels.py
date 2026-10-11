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
