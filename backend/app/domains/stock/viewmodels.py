"""View-models of the stock screens (CR-21)."""

from dataclasses import dataclass, field
from typing import Any, Optional

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class StockView(ViewModel):
    """`admin_voorraad.html` — one row per size, with its stock figures."""

    rows: list[dict[str, Any]]  # product, size, on_hand, reserved, available
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
