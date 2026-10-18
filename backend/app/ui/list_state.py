"""The state of a list on the kit's list page, read from its address (#2123).

A list that filters in memory — a few dozen rows, no query of its own — keeps its status,
search, page and page size in the URL like the lists that query: the toolbar and the pager
mark their requests, and the route reads the state back on load. One reader, so the six
lists of #2123 (and the next) do not each spell the same four lines.

`read_state` takes the statuses the list knows and drops what is not one of them, because
anything that comes from an address is input. `page_of` cuts the rows to the page and clamps
the page to the last one, so a page that no longer exists (a filter narrowed the list) shows
the last page and not an empty one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence
from urllib.parse import urlencode

from app.ui import PER_PAGE_DEFAULT, filterparams, per_page_from


@dataclass(frozen=True)
class ListState:
    q: str
    status: str
    page: int
    per_page: int

    def query(self, **more: Any) -> str:
        """The state as a query string, only what differs from empty; `more` overrides."""
        state = {
            "status": self.status,
            "q": self.q,
            "per_page": self.per_page if self.per_page != PER_PAGE_DEFAULT else "",
            **more,
        }
        return urlencode({k: v for k, v in state.items() if v not in ("", None)})


def read_state(request: Any, statuses: Iterable[str] = ()) -> ListState:
    state = filterparams(request)
    status = (state.get("status") or "").strip()
    if status not in set(statuses):
        status = ""
    try:
        page = max(1, int(state.get("page") or 1))
    except ValueError:
        page = 1
    return ListState(
        q=(state.get("q") or "").strip(),
        status=status,
        page=page,
        per_page=per_page_from(state.get("per_page")),
    )


def page_of(rows: Sequence[Any], state: ListState) -> tuple[list[Any], int, int]:
    """`(the rows of the page, the total, the page)` — the page clamped to the last."""
    total = len(rows)
    page = min(state.page, max(1, -(-total // state.per_page)))
    return list(rows[(page - 1) * state.per_page : page * state.per_page]), total, page


def segments_of(
    options: Sequence[tuple[str, str]], counts: dict[str, int], total: int, all_label: str
) -> list[dict[str, Any]]:
    """The toolbar's segments: "Alle" first with the total, then each `(value, label)`
    with its count."""
    return [{"value": "", "label": all_label, "count": total}] + [
        {"value": value, "label": label, "count": counts.get(value, 0)} for value, label in options
    ]
