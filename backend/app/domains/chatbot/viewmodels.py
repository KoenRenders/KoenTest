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
    model: str
    provider: str
    status_label: str
    status_tone: str
    duration: str
    cost: str


@dataclass(frozen=True, kw_only=True)
class AiCallListView(ViewModel):
    """`_ai_kosten_lijst.html`: the calls, newest first, one page."""

    calls: list[AiCallLine]
    page: int
    has_prev: bool
    has_next: bool


@dataclass(frozen=True, kw_only=True)
class AiCostView(AiCallListView):
    """`admin_ai_kosten.html`: the month's totals above the list."""

    month_label: str
    prev_month: str
    next_month: str
    totals: list[AiCostLine]
    nav_items: list[dict[str, Any]] = field(default_factory=list)
