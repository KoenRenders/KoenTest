"""View-models of the stock screens (CR-21)."""

from dataclasses import dataclass, field
from typing import Any, Optional

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class StockView(ViewModel):
    """`admin_voorraad.html` and its fragment `_voorraad_lijst.html`."""

    rows: list[dict[str, Any]]  # product, size, on_hand, reserved, available
    #: The toolbar's state: the search term and how many rows it left.
    q: str = ""
    total: int = 0
    #: What the empty state says: one sentence for a search without a hit, another
    #: for a shop with no sizes at all.
    empty_reason: str = ""
    #: True on the fragment answer, so it sends the toolbar's count out-of-band.
    oob: bool = False
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class StockReceiptView(ViewModel):
    """`admin_ontvangst.html` — book a receipt from the supplier."""

    options: list[tuple[str, str]]  # (variant id, "product · size") for the select
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class StockCorrectionView(ViewModel):
    """`admin_correctie.html` — adjust the stock by hand, up or down."""

    options: list[tuple[str, str]]
    #: The "Richting" choice (Erbij / Eraf), as (value, label) pairs.
    directions: list[tuple[str, str]]
    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class StockMovementsView(ViewModel):
    """`admin_voorraad_maat.html` — the movements of one size, newest first (AC16)."""

    product_name: str
    size: str
    #: One dict per movement: `reason` (a MovementReason), `quantity`, `note`,
    #: and `occurred` (the moment in the tenant's time zone, pre-formatted).
    movements: list[dict[str, Any]]
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)
